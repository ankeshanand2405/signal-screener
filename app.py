from flask import Flask, render_template, jsonify, request
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import requests
from io import StringIO
import time
import threading
import json
import os

try:
    from jugaad_data.nse import bhavcopy_raw
    JUGAAD_AVAILABLE = True
except ImportError:
    JUGAAD_AVAILABLE = False

app = Flask(__name__)

# In-memory fast cache for interactive candlestick charts & raw stock data
RAW_STOCK_DATA = {}
CHART_DATA_CACHE = {}

# ─── Load Cached Market Cap & Shares ──────────────────────────────────────────
MCAP_CACHE = {}
CACHE_FILE = os.path.join(os.path.dirname(__file__), "mcap_cache.json")
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
            MCAP_CACHE = cache_data.get("stocks", {})
    except Exception as e:
        print(f"Warning: Failed to load {CACHE_FILE}: {e}")

# ─── Load Cached Sectors ───────────────────────────────────────────────────────
SECTORS_CACHE = {}
SECTORS_FILE = os.path.join(os.path.dirname(__file__), "sectors.json")
if os.path.exists(SECTORS_FILE):
    try:
        with open(SECTORS_FILE, "r", encoding="utf-8") as f:
            SECTORS_CACHE = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load {SECTORS_FILE}: {e}")

def get_sector(sym):
    clean_sym = sym.replace(".NS", "")
    return SECTORS_CACHE.get(clean_sym, "Diversified & Conglomerates")

def get_cached_mcap(sym, close_price=None):
    """
    Returns market cap in ₹ Billions.
    Computes live mcap using (cached_shares * close_price) if available,
    otherwise falls back to cached mcap_b, or 0.0.
    """
    clean_sym = sym.replace(".NS", "")
    info = MCAP_CACHE.get(clean_sym)
    if not info:
        return 0.0
    shares = info.get("shares")
    if shares and close_price is not None and not np.isnan(close_price):
        return round((shares * close_price) / 1e9, 1)
    return info.get("mcap_b", 0.0)

# ─── Indicators (pure pandas/numpy — no pandas-ta) ────────────────────────────

def sma(series, n):
    return series.rolling(window=n, min_periods=1).mean()

def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

# def rsi(series, n=14):
#     delta = series.diff()
#     gain = delta.clip(lower=0)
#     loss = -delta.clip(upper=0)
#     avg_gain = gain.ewm(alpha=1.0/n, adjust=False).mean()
#     avg_loss = loss.ewm(alpha=1.0/n, adjust=False).mean()
#     rs = avg_gain / avg_loss.replace(0, np.nan)
#     return (100.0 - (100.0 / (1.0 + rs))).fillna(100.0)

# More accurate Wilder's RSI initialization
def rsi(series, n=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.copy().astype(float) * 0
    avg_loss = loss.copy().astype(float) * 0
    avg_gain.iloc[n] = gain.iloc[1:n+1].mean()
    avg_loss.iloc[n] = loss.iloc[1:n+1].mean()
    for i in range(n+1, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (n-1) + gain.iloc[i]) / n
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (n-1) + loss.iloc[i]) / n
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100.0 - (100.0 / (1.0 + rs))).fillna(100.0)

def compute_indicators(df_daily):
    df = df_daily.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    c = df["Close"]
    h = df["High"]
    v = df["Volume"]

    df["SMA10"]     = sma(c, 10)
    df["SMA20"]     = sma(c, 20)
    df["SMA50"]     = sma(c, 50)
    df["EMA10"]     = ema(c, 10)
    df["EMA20"]     = ema(c, 20)
    df["RSI14"]     = rsi(c, 14)
    # df["52W_High"]  = h.rolling(252, min_periods=1).max()
    df["52W_High"] = h.rolling("365D").max()
    # df["Avg_Vol10"] = v.rolling(10, min_periods=1).mean()
    # df["Rel_Vol"]   = v / df["Avg_Vol10"]
    df["Avg_Vol10"] = v.rolling(10, min_periods=1).mean().shift(1)
    df["Rel_Vol"]   = v / df["Avg_Vol10"]
    df["Vol_Chg"]   = v.pct_change() * 100
    df["Chg_Open"]  = ((c - df["Open"]) / df["Open"]) * 100
    df["Chg_Pct"]   = c.pct_change() * 100

    # Weekly
    weekly = df[["Open","High","Low","Close","Volume"]].resample("W-FRI").agg(
        {"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}
    ).dropna()
    wc = weekly["Close"]
    weekly["SMA10_W"]  = sma(wc, 10)
    weekly["SMA20_W"]  = sma(wc, 20)
    weekly["SMA50_W"]  = sma(wc, 50)
    weekly["EMA10_W"]  = ema(wc, 10)
    weekly["EMA20_W"]  = ema(wc, 20)
    weekly["RSI14_W"]  = rsi(wc, 14)
    weekly["Chg_Open_W"] = ((wc - weekly["Open"]) / weekly["Open"]) * 100
    weekly["Chg_Pct_W"]  = wc.pct_change() * 100

    return df, weekly

# ─── NSE Stock Universe ────────────────────────────────────────────────────────

FALLBACK_SYMBOLS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS","HINDUNILVR.NS",
    "ITC.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS","LT.NS","AXISBANK.NS",
    "ASIANPAINT.NS","MARUTI.NS","NESTLEIND.NS","ULTRACEMCO.NS","TITAN.NS",
    "WIPRO.NS","HCLTECH.NS","SUNPHARMA.NS","BAJFINANCE.NS","BAJAJFINSV.NS",
    "TECHM.NS","POWERGRID.NS","NTPC.NS","ONGC.NS","COALINDIA.NS","JSWSTEEL.NS",
    "TATASTEEL.NS","HINDALCO.NS","ADANIENT.NS","ADANIPORTS.NS","DIVISLAB.NS",
    "DRREDDY.NS","CIPLA.NS","APOLLOHOSP.NS","EICHERMOT.NS","HEROMOTOCO.NS",
    "BAJAJ-AUTO.NS","TATACONSUM.NS","BRITANNIA.NS","DABUR.NS","MARICO.NS",
    "PIDILITIND.NS","BERGEPAINT.NS","GODREJCP.NS","COLPAL.NS","HAVELLS.NS",
    "VOLTAS.NS","CROMPTON.NS","POLYCAB.NS","KEI.NS","MOTHERSON.NS",
    "BOSCHLTD.NS","EXIDEIND.NS","AMARARAJA.NS","SBILIFE.NS","HDFCLIFE.NS",
    "ICICIGI.NS","LICI.NS","CHOLAFIN.NS","MUTHOOTFIN.NS","MANAPPURAM.NS",
    "SHRIRAMFIN.NS","FEDERALBNK.NS","IDFCFIRSTB.NS","BANDHANBNK.NS","RBLBANK.NS",
    "CANBK.NS","BANKBARODA.NS","PNB.NS","UNIONBANK.NS","ZOMATO.NS","IRCTC.NS",
    "HAL.NS","BEL.NS","BHEL.NS","CONCOR.NS","GAIL.NS","IOC.NS","BPCL.NS",
    "HPCL.NS","TATAPOWER.NS","ADANIGREEN.NS","TORNTPOWER.NS","VEDL.NS","NMDC.NS",
    "NATIONALUM.NS","UPL.NS","PIIND.NS","COROMANDEL.NS","ASTRAL.NS","SUPREMEIND.NS",
    "DEEPAKNTR.NS","OFSS.NS","LTIM.NS","MPHASIS.NS","COFORGE.NS","PERSISTENT.NS",
    "TATAELXSI.NS","KPITTECH.NS","PAGEIND.NS","TRENT.NS","DMART.NS","JUBLFOOD.NS",
    "INDHOTEL.NS","TATAMOTORS.NS","M&M.NS","ASHOKLEY.NS","TVSMOTOR.NS","ESCORTS.NS",
    "CUMMINSIND.NS","THERMAX.NS","ABB.NS","SIEMENS.NS","SHREECEM.NS","AMBUJACEM.NS",
    "ACC.NS","DALBHARAT.NS","OBEROIRLTY.NS","DLF.NS","GODREJPROP.NS","PRESTIGE.NS",
    "PHOENIXLTD.NS","BRIGADE.NS","SOBHA.NS","GLENMARK.NS","ALKEM.NS","TORNTPHARM.NS",
    "IPCALAB.NS","LAURUSLABS.NS","GRANULES.NS","BIOCON.NS","ABBOTINDIA.NS",
]

def get_nse_stocks():
    # If cached NSE stocks exist, filter for stocks meeting our mcap threshold (with safety buffer)
    # This guarantees 100% coverage of all stocks > 25B (or 20B) while skipping illiquid penny stocks
    if MCAP_CACHE:
        return [f"{s}.NS" for s, v in MCAP_CACHE.items() if v.get("mcap_b", 0) >= 15]

    try:
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        df = pd.read_csv(StringIO(r.text))
        df.columns = [c.strip() for c in df.columns]
        df_eq = df[df["SERIES"].str.strip() == "EQ"]
        return [s + ".NS" for s in df_eq["SYMBOL"].tolist()]
    except Exception:
        return FALLBACK_SYMBOLS

# ─── Fast Single-Download Bhavcopy Fallback ──────────────────────────────────

BHAVCOPY_CACHE = {}

def get_latest_bhavcopy():
    """Fetch the latest available NSE daily Bhavcopy once in ~0.35s for the whole market."""
    global BHAVCOPY_CACHE
    if not JUGAAD_AVAILABLE:
        return {}

    today = date.today()
    if BHAVCOPY_CACHE.get("date") == today and BHAVCOPY_CACHE.get("data"):
        return BHAVCOPY_CACHE["data"]

    try:
        raw = None
        for delta in range(0, 5):
            d = today - timedelta(days=delta)
            try:
                text = bhavcopy_raw(d)
                if text and len(text) > 1000:
                    raw = text
                    break
            except Exception:
                continue

        if raw:
            import io, csv
            reader = csv.DictReader(io.StringIO(raw))
            data = {}
            for row in reader:
                sym = row.get("TckrSymb") or row.get("SYMBOL") or ""
                srs = row.get("SctySrs") or row.get("SERIES") or ""
                if srs.strip() in ["EQ", "BE", "SM", "BZ"] and sym:
                    try:
                        data[sym.strip()] = {
                            "Open": float(row.get("OpnPric") or row.get("OPEN")),
                            "High": float(row.get("HghPric") or row.get("HIGH")),
                            "Low": float(row.get("LwPric") or row.get("LOW")),
                            "Close": float(row.get("ClsPric") or row.get("CLOSE")),
                            "Volume": float(row.get("TtlTradgVol") or row.get("TOTTRDQTY")),
                            "Date": row.get("TradDt") or row.get("TIMESTAMP") or str(today)
                        }
                    except (ValueError, TypeError):
                        pass
            BHAVCOPY_CACHE = {"date": today, "data": data}
            return data
    except Exception as e:
        print(f"Notice: Bhavcopy fetch skipped ({e})")
    return {}

def fill_missing_from_bhavcopy(df_sym, sym, bhav_dict):
    """When yfinance has NaN OHLC for the latest row, patch from the pre-downloaded Bhavcopy."""
    if df_sym.empty:
        return df_sym

    if isinstance(df_sym.columns, pd.MultiIndex):
        df_sym.columns = df_sym.columns.get_level_values(0)

    clean_sym = sym.replace(".NS", "")
    last_row = df_sym.iloc[-1]
    if pd.notna(last_row.get("Close")):
        return df_sym

    if not bhav_dict or clean_sym not in bhav_dict:
        return df_sym.dropna(subset=["Close"])

    try:
        bhav_row = bhav_dict[clean_sym]
        df_clean = df_sym.dropna(subset=["Close"]).copy()
        row_dt = pd.to_datetime(bhav_row.get("Date", date.today())).normalize()
        new_row = pd.DataFrame([{
            "Open": bhav_row["Open"], "High": bhav_row["High"],
            "Low": bhav_row["Low"], "Close": bhav_row["Close"],
            "Volume": bhav_row["Volume"]
        }], index=[row_dt])
        df_clean = pd.concat([df_clean, new_row]).sort_index()
        return df_clean
    except Exception:
        return df_sym.dropna(subset=["Close"])

# ─── Screeners ────────────────────────────────────────────────────────────────

def screener_1(sym, daily, weekly, mcap):
    if mcap < 25: return None
    try:
        d = daily.iloc[-1]
        date_str = d.name.strftime("%d %b") if hasattr(d.name, "strftime") else ""
        # TradingView Breakout Daily: Price > SMA 10/20/50, RSI 14 > 55, RelVol >= 1.0 (with 0.98 tolerance), positive daily action
        price_up = (d.get("Chg_Pct", 0) > 0) or (d.get("Chg_Open", 0) > 0)
        rel_vol = d.get("Rel_Vol", 0)
        if (d["Close"] > d["SMA10"] and d["Close"] > d["SMA20"] and
            d["Close"] > d["SMA50"] and price_up and
            rel_vol >= 0.98 and d["RSI14"] > 55):
            chg_val = d["Chg_Pct"] if pd.notna(d.get("Chg_Pct")) else d["Chg_Open"]
            return {"symbol": sym.replace(".NS",""), "price": round(d["Close"],2),
                    "rsi": round(d["RSI14"],1), "rel_vol": round(rel_vol,2),
                    "chg_open": round(chg_val,2), "mkt_cap": round(mcap,1),
                    "sector": get_sector(sym), "date": date_str}
    except: pass

def screener_2(sym, daily, weekly, mcap):
    if mcap < 25: return None
    try:
        d = daily.iloc[-1]; w = weekly.iloc[-1]
        date_str = d.name.strftime("%d %b") if hasattr(d.name, "strftime") else ""
        # TradingView Breakout Weekly: Price > SMA 10/20/50 weekly, RSI 14 weekly > 55, Market Cap >= 25B, Positive Weekly Change
        weekly_up = (w.get("Chg_Pct_W", 0) > 0) or (w.get("Chg_Open_W", 0) > 0)
        if (d["Close"] > w["SMA10_W"] and d["Close"] > w["SMA20_W"] and
            d["Close"] > w["SMA50_W"] and w["RSI14_W"] > 55 and weekly_up):
            weekly_chg = w["Chg_Pct_W"] if pd.notna(w.get("Chg_Pct_W")) else w["Chg_Open_W"]
            return {"symbol": sym.replace(".NS",""), "price": round(d["Close"],2),
                    "rsi_w": round(w["RSI14_W"],1), "chg_open_w": round(weekly_chg,2),
                    "mkt_cap": round(mcap,1), "sector": get_sector(sym), "date": date_str}
    except: pass

def screener_3(sym, daily, weekly, mcap):
    if mcap < 20: return None
    try:
        d = daily.iloc[-1]
        date_str = d.name.strftime("%d %b") if hasattr(d.name, "strftime") else ""
        near_52w = (d["52W_High"] >= d["Close"]) and (d["Close"] >= d["52W_High"] * 0.80)
        # TradingView Trading Scanner: Day change > 2% (vs open or prev close), Vol_Chg > 0, EMA10 > EMA20, Close > EMA20, RSI > 55, Near 52W High
        price_surge = (d.get("Chg_Pct", 0) > 2.0) or (d.get("Chg_Open", 0) > 2.0)
        if (d["Close"] > d["EMA20"] and price_surge and d["Vol_Chg"] > 0 and
            d["EMA10"] > d["EMA20"] and d["RSI14"] > 55 and near_52w):
            chg_val = d["Chg_Pct"] if pd.notna(d.get("Chg_Pct")) else d["Chg_Open"]
            return {"symbol": sym.replace(".NS",""), "price": round(d["Close"],2),
                    "rsi": round(d["RSI14"],1), "chg_open": round(chg_val,2),
                    "vol_chg": round(d["Vol_Chg"],1), "high_52w": round(d["52W_High"],2),
                    "mkt_cap": round(mcap,1), "sector": get_sector(sym), "date": date_str}
    except: pass

def screener_4(sym, daily, weekly, mcap):
    if mcap < 20: return None
    try:
        d = daily.iloc[-1]; w = weekly.iloc[-1]
        date_str = d.name.strftime("%d %b") if hasattr(d.name, "strftime") else ""
        near_52w = (d["52W_High"] >= d["Close"]) and (d["Close"] >= d["52W_High"] * 0.80)
        # TradingView MT Investing: Weekly surge > 2%, EMA10_W > EMA20_W, Close > EMA10_W, RSI14_W > 50, Near 52W High
        weekly_surge = (w.get("Chg_Pct_W", 0) > 2.0) or (w.get("Chg_Open_W", 0) > 2.0)
        if (d["Close"] > w["EMA10_W"] and w["EMA10_W"] > w["EMA20_W"] and
            w["RSI14_W"] > 50 and weekly_surge and near_52w):
            weekly_chg = w["Chg_Pct_W"] if pd.notna(w.get("Chg_Pct_W")) else w["Chg_Open_W"]
            return {"symbol": sym.replace(".NS",""), "price": round(d["Close"],2),
                    "rsi_w": round(w["RSI14_W"],1), "chg_open_w": round(weekly_chg,2),
                    "high_52w": round(d["52W_High"],2), "mkt_cap": round(mcap,1),
                    "sector": get_sector(sym), "date": date_str}
    except: pass

# ─── Scan ────────────────────────────────────────────────────────────────────

progress_data = {"status": "idle", "done": 0, "total": 0, "message": "", "elapsed": 0.0, "results": None}

def run_scan():
    global progress_data
    scan_start = time.time()
    stocks = get_nse_stocks()
    results = {"s1":[], "s2":[], "s3":[], "s4":[],
               "timestamp": datetime.now().strftime("%d %b %Y, %I:%M %p"),
               "elapsed_seconds": 0.0}

    progress_data = {
        "status": "running",
        "done": 0,
        "total": len(stocks),
        "message": "Fetching stock universe & latest Bhavcopy...",
        "elapsed": 0.0,
        "results": results
    }

    # Fetch Bhavcopy once in 0.35s for the whole market
    bhav_dict = get_latest_bhavcopy()

    BATCH = 50
    for i in range(0, len(stocks), BATCH):
        batch = stocks[i:i+BATCH]
        elapsed = round(time.time() - scan_start, 1)
        progress_data["message"] = f"Scanning {i+1}–{min(i+BATCH, len(stocks))} of {len(stocks)}..."
        progress_data["elapsed"] = elapsed
        try:
            raw = yf.download(batch, period="2y", interval="1d",
                              group_by="ticker", auto_adjust=True,
                              progress=False, threads=True)
        except Exception:
            progress_data["done"] += len(batch)
            continue

        for sym in batch:
            try:
                df_sym = raw[sym].copy() if len(batch) > 1 else raw.copy()
                if df_sym.empty or len(df_sym) < 60: continue
                # Strip timezone if present so resample and index behave consistently
                if df_sym.index.tz is not None:
                    df_sym.index = df_sym.index.tz_localize(None)
                # Fill missing latest-day data from pre-downloaded Bhavcopy (0ms)
                df_sym = fill_missing_from_bhavcopy(df_sym, sym, bhav_dict)
                df_sym = df_sym.dropna(subset=["Close"])
                RAW_STOCK_DATA[sym.replace(".NS", "")] = df_sym
                latest_close = df_sym["Close"].iloc[-1]
                mcap = get_cached_mcap(sym, latest_close)
                daily, weekly = compute_indicators(df_sym)
                for fn, key in [(screener_1,"s1"),(screener_2,"s2"),(screener_3,"s3"),(screener_4,"s4")]:
                    r = fn(sym, daily, weekly, mcap)
                    if r: results[key].append(r)
            except: pass
            finally: progress_data["done"] += 1

        # Real-time streaming update to frontend on every batch:
        progress_data["results"] = results
        progress_data["elapsed"] = round(time.time() - scan_start, 1)

    total_time = round(time.time() - scan_start, 1)
    results["elapsed_seconds"] = total_time
    progress_data.update({
        "status": "done",
        "results": results,
        "elapsed": total_time,
        "message": f"Scan complete in {total_time}s."
    })

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start-scan", methods=["POST"])
def start_scan():
    if progress_data.get("status") == "running":
        return jsonify({"error": "Scan already running"}), 400
    threading.Thread(target=run_scan, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/progress")
def progress():
    return jsonify(progress_data)

def get_stock_chart_payload(clean_sym, timeframe="D"):
    clean_sym = clean_sym.replace(".NS", "").strip().upper()
    timeframe = timeframe.upper()
    cache_key = f"{clean_sym}_{timeframe}"
    if cache_key in CHART_DATA_CACHE:
        return CHART_DATA_CACHE[cache_key]

    df_sym = RAW_STOCK_DATA.get(clean_sym)
    if df_sym is None or df_sym.empty:
        yf_sym = f"{clean_sym}.NS"
        raw = yf.download(yf_sym, period="2y", interval="1d", auto_adjust=True, progress=False)
        if raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        if raw.index.tz is not None:
            raw.index = raw.index.tz_localize(None)
        bhav = get_latest_bhavcopy()
        df_sym = fill_missing_from_bhavcopy(raw, yf_sym, bhav).dropna(subset=["Close"])
        if df_sym.empty:
            return None
        RAW_STOCK_DATA[clean_sym] = df_sym

    daily, weekly = compute_indicators(df_sym)

    if timeframe == "W":
        target_df = weekly
        s10_col, s20_col, s50_col, rsi_col = "SMA10_W", "SMA20_W", "SMA50_W", "RSI14_W"
    elif timeframe == "M":
        target_df = df_sym[["Open","High","Low","Close","Volume"]].resample("ME").agg(
            {"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}
        ).dropna()
        target_df["SMA10"] = target_df["Close"].rolling(10, min_periods=1).mean()
        target_df["SMA20"] = target_df["Close"].rolling(20, min_periods=1).mean()
        target_df["SMA50"] = target_df["Close"].rolling(50, min_periods=1).mean()
        delta = target_df["Close"].diff()
        # gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
        # loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
        # target_df["RSI14"] = (100 - (100 / (1 + gain / loss.replace(0, float("nan"))))).fillna(100.0)
        delta = target_df["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.copy().astype(float) * 0
        avg_loss = loss.copy().astype(float) * 0
        if len(gain) > 14:
            avg_gain.iloc[14] = gain.iloc[1:15].mean()
            avg_loss.iloc[14] = loss.iloc[1:15].mean()
            for i in range(15, len(gain)):
                avg_gain.iloc[i] = (avg_gain.iloc[i-1] * 13 + gain.iloc[i]) / 14
                avg_loss.iloc[i] = (avg_loss.iloc[i-1] * 13 + loss.iloc[i]) / 14
        target_df["RSI14"] = (100 - (100 / (1 + avg_gain / avg_loss.replace(0, float("nan"))))).fillna(100.0)
        s10_col, s20_col, s50_col, rsi_col = "SMA10", "SMA20", "SMA50", "RSI14"
    else:
        target_df = daily
        s10_col, s20_col, s50_col, rsi_col = "SMA10", "SMA20", "SMA50", "RSI14"

    candles = []
    volumes = []
    s10, s20, s50, rsi_data = [], [], [], []
    for dt, r in target_df.iterrows():
        t = dt.strftime("%Y-%m-%d")
        c = round(float(r["Close"]), 2)
        o = round(float(r["Open"]), 2)
        candles.append({
            "time": t,
            "open": o,
            "high": round(float(r["High"]), 2),
            "low": round(float(r["Low"]), 2),
            "close": c
        })
        is_up = c >= o
        volumes.append({
            "time": t,
            "value": float(r["Volume"]),
            "color": "rgba(16, 185, 129, 0.45)" if is_up else "rgba(239, 68, 68, 0.45)"
        })
        if pd.notna(r.get(s10_col)):
            s10.append({"time": t, "value": round(float(r[s10_col]), 2)})
        if pd.notna(r.get(s20_col)):
            s20.append({"time": t, "value": round(float(r[s20_col]), 2)})
        if pd.notna(r.get(s50_col)):
            s50.append({"time": t, "value": round(float(r[s50_col]), 2)})
        if pd.notna(r.get(rsi_col)):
            rsi_data.append({"time": t, "value": round(float(r[rsi_col]), 2)})

    last_candle = candles[-1] if candles else {}
    last_close = last_candle.get("close", 0)
    prev_close = candles[-2]["close"] if len(candles) > 1 else last_close
    chg_pct = round(((last_close - prev_close) / prev_close) * 100, 2) if prev_close else 0.0

    payload = {
        "symbol": clean_sym,
        "sector": get_sector(clean_sym),
        "timeframe": timeframe,
        "last_price": last_close,
        "chg_pct": chg_pct,
        "last_rsi": rsi_data[-1]["value"] if rsi_data else None,
        "candles": candles,
        "volumes": volumes,
        "sma10": s10,
        "sma20": s20,
        "sma50": s50,
        "rsi": rsi_data
    }
    CHART_DATA_CACHE[cache_key] = payload
    return payload

@app.route("/api/chart/<symbol>")
def chart_data(symbol):
    tf = request.args.get("tf", "D").upper()
    if tf not in ["D", "W", "M"]:
        tf = "D"
    try:
        data = get_stock_chart_payload(symbol, tf)
        if not data:
            return jsonify({"error": f"No market data available for {symbol}"}), 404
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)

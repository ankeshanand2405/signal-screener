from flask import Flask, render_template, jsonify
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import requests
from io import StringIO
import time
import threading

app = Flask(__name__)

# ─── NSE Stock Universe ────────────────────────────────────────────────────────

def get_nse_stocks():
    """Fetch NSE stock list from NSE website."""
    try:
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        df = pd.read_csv(StringIO(r.text))
        symbols = df["SYMBOL"].tolist()
        return [s + ".NS" for s in symbols]
    except Exception:
        # Fallback: Nifty 500 approximation using a known list
        return FALLBACK_SYMBOLS

# Fallback Nifty 200 symbols if NSE fetch fails
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
    "VOLTAS.NS","WHIRLPOOL.NS","CROMPTON.NS","POLYCAB.NS","KEI.NS",
    "MOTHERSON.NS","BOSCHLTD.NS","EXIDEIND.NS","AMARARAJA.NS","MFSL.NS",
    "SBILIFE.NS","HDFCLIFE.NS","ICICIGI.NS","LICI.NS","CHOLAFIN.NS",
    "MUTHOOTFIN.NS","MANAPPURAM.NS","SHRIRAMFIN.NS","PNBHOUSING.NS","LICHSGFIN.NS",
    "FEDERALBNK.NS","IDFCFIRSTB.NS","BANDHANBNK.NS","RBLBANK.NS","INDIANB.NS",
    "CANBK.NS","BANKBARODA.NS","PNB.NS","UNIONBANK.NS","UCOBANK.NS",
    "ZOMATO.NS","NYKAA.NS","PAYTM.NS","POLICYBZR.NS","DELHIVERY.NS",
    "IRCTC.NS","HAL.NS","BEL.NS","BHEL.NS","CONCOR.NS",
    "GAIL.NS","IOC.NS","BPCL.NS","HPCL.NS","MGL.NS",
    "TATAPOWER.NS","ADANIGREEN.NS","ADANITRANS.NS","TORNTPOWER.NS","CESC.NS",
    "VEDL.NS","NMDC.NS","MOIL.NS","NATIONALUM.NS","HINDCOPPER.NS",
    "UPL.NS","PIIND.NS","COROMANDEL.NS","CHAMBLFERT.NS","GNFC.NS",
    "ASTRAL.NS","SUPREMEIND.NS","AARTIIND.NS","DEEPAKNTR.NS","ATUL.NS",
    "OFSS.NS","LTIM.NS","MPHASIS.NS","COFORGE.NS","PERSISTENT.NS",
    "ZENSARTECH.NS","TATAELXSI.NS","KPITTECH.NS","ROUTE.NS","BSOFT.NS",
    "PAGEIND.NS","ABFRL.NS","TRENT.NS","SHOPERSTOP.NS","DMART.NS",
    "JUBLFOOD.NS","DEVYANI.NS","SAPPHIRE.NS","WESTLIFE.NS","BARBEQUE.NS",
    "INDHOTEL.NS","EIHOTEL.NS","LEMONTRE.NS","CHALET.NS","MAHINDRA.NS",
    "TATAMOTORS.NS","M&M.NS","ASHOKLEY.NS","TVSMOTOR.NS","ESCORTS.NS",
    "CUMMINSIND.NS","THERMAX.NS","ABB.NS","SIEMENS.NS","GRINDWELL.NS",
    "RAMCOCEM.NS","JKCEMENT.NS","HEIDELBERG.NS","SHREECEM.NS","AMBUJACEM.NS",
    "ACC.NS","DALBHARAT.NS","ORIENTCEM.NS","PRISMJOINTS.NS","NUVOCO.NS",
    "OBEROIRLTY.NS","DLF.NS","GODREJPROP.NS","PRESTIGE.NS","PHOENIXLTD.NS",
    "BRIGADE.NS","SOBHA.NS","MAHLIFE.NS","KOLTEPATIL.NS","SUNTECK.NS",
    "GLENMARK.NS","ALKEM.NS","TORNTPHARM.NS","IPCALAB.NS","AJANTPHARM.NS",
    "LAURUSLABS.NS","GRANULES.NS","SUVEN.NS","NATCOPHARM.NS","ABBOTINDIA.NS",
    "PFIZER.NS","GLAXO.NS","SANOFI.NS","ASTRAZEN.NS","BIOCON.NS",
]


# ─── Indicators ───────────────────────────────────────────────────────────────

def compute_indicators(df_daily):
    """Compute all required technical indicators on daily OHLCV data."""
    df = df_daily.copy()
    close = df["Close"]
    high = df["High"]
    volume = df["Volume"]

    # Daily indicators
    df["SMA10"] = ta.sma(close, length=10)
    df["SMA20"] = ta.sma(close, length=20)
    df["SMA50"] = ta.sma(close, length=50)
    df["EMA10"] = ta.ema(close, length=10)
    df["EMA20"] = ta.ema(close, length=20)
    df["RSI14"] = ta.rsi(close, length=14)
    df["52W_High"] = high.rolling(window=252).max()
    df["Avg_Vol_20"] = volume.rolling(window=20).mean()
    df["Rel_Vol"] = volume / df["Avg_Vol_20"]
    df["Vol_Chg"] = volume.pct_change() * 100
    df["Chg_From_Open"] = ((close - df["Open"]) / df["Open"]) * 100
    df["Mkt_Cap_Approx"] = close  # placeholder; real mkt cap fetched separately

    # Weekly indicators (resample)
    weekly = df[["Open", "High", "Low", "Close", "Volume"]].resample("W").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()
    weekly["SMA10_W"] = ta.sma(weekly["Close"], length=10)
    weekly["SMA20_W"] = ta.sma(weekly["Close"], length=20)
    weekly["SMA50_W"] = ta.sma(weekly["Close"], length=50)
    weekly["EMA10_W"] = ta.ema(weekly["Close"], length=10)
    weekly["EMA20_W"] = ta.ema(weekly["Close"], length=20)
    weekly["RSI14_W"] = ta.rsi(weekly["Close"], length=14)
    weekly["Chg_From_Open_W"] = ((weekly["Close"] - weekly["Open"]) / weekly["Open"]) * 100

    return df, weekly


# ─── Screeners ────────────────────────────────────────────────────────────────

def run_screener_1(symbol, daily, weekly, mkt_cap_b):
    """Breakout QT ST (1D): Price > SMA10/20/50, MktCap > 25B, Chg from open > 0%, RelVol > 1, RSI > 55"""
    d = daily.iloc[-1]
    if mkt_cap_b < 25: return None
    try:
        if (d["Close"] > d["SMA10"] and
            d["Close"] > d["SMA20"] and
            d["Close"] > d["SMA50"] and
            d["Chg_From_Open"] > 0 and
            d["Rel_Vol"] > 1 and
            d["RSI14"] > 55):
            return {
                "symbol": symbol.replace(".NS", ""),
                "price": round(d["Close"], 2),
                "rsi": round(d["RSI14"], 1),
                "rel_vol": round(d["Rel_Vol"], 2),
                "chg_open": round(d["Chg_From_Open"], 2),
                "mkt_cap": round(mkt_cap_b, 1),
            }
    except: pass
    return None

def run_screener_2(symbol, daily, weekly, mkt_cap_b):
    """Breakout MT LT (1W/1M): Weekly Price > SMA10/20/50, MktCap > 25B, Weekly Chg > 0%, Weekly RSI > 55"""
    if mkt_cap_b < 25: return None
    try:
        w = weekly.iloc[-1]
        d = daily.iloc[-1]
        if (d["Close"] > w["SMA10_W"] and
            d["Close"] > w["SMA20_W"] and
            d["Close"] > w["SMA50_W"] and
            w["Chg_From_Open_W"] > 0 and
            w["RSI14_W"] > 55):
            return {
                "symbol": symbol.replace(".NS", ""),
                "price": round(d["Close"], 2),
                "rsi_w": round(w["RSI14_W"], 1),
                "chg_open_w": round(w["Chg_From_Open_W"], 2),
                "mkt_cap": round(mkt_cap_b, 1),
            }
    except: pass
    return None

def run_screener_3(symbol, daily, weekly, mkt_cap_b):
    """Trading Scanner: Price > EMA20, MktCap > 20B, Chg from open > 2%, Vol chg > 0%, EMA10 > EMA20, RSI > 55, 52W High 0-20% above price"""
    if mkt_cap_b < 20: return None
    try:
        d = daily.iloc[-1]
        near_52w = (d["52W_High"] >= d["Close"]) and (d["52W_High"] <= d["Close"] * 1.20)
        if (d["Close"] > d["EMA20"] and
            d["Chg_From_Open"] > 2 and
            d["Vol_Chg"] > 0 and
            d["EMA10"] > d["EMA20"] and
            d["RSI14"] > 55 and
            near_52w):
            return {
                "symbol": symbol.replace(".NS", ""),
                "price": round(d["Close"], 2),
                "rsi": round(d["RSI14"], 1),
                "chg_open": round(d["Chg_From_Open"], 2),
                "vol_chg": round(d["Vol_Chg"], 1),
                "high_52w": round(d["52W_High"], 2),
                "mkt_cap": round(mkt_cap_b, 1),
            }
    except: pass
    return None

def run_screener_4(symbol, daily, weekly, mkt_cap_b):
    """MT Investing: Weekly Price > EMA10W, EMA10W > EMA20W, MktCap > 20B, Weekly RSI > 50, Weekly Chg > 2%, 52W High 0-20% above price"""
    if mkt_cap_b < 20: return None
    try:
        d = daily.iloc[-1]
        w = weekly.iloc[-1]
        near_52w = (d["52W_High"] >= d["Close"]) and (d["52W_High"] <= d["Close"] * 1.20)
        if (d["Close"] > w["EMA10_W"] and
            w["EMA10_W"] > w["EMA20_W"] and
            w["RSI14_W"] > 50 and
            w["Chg_From_Open_W"] > 2 and
            near_52w):
            return {
                "symbol": symbol.replace(".NS", ""),
                "price": round(d["Close"], 2),
                "rsi_w": round(w["RSI14_W"], 1),
                "chg_open_w": round(w["Chg_From_Open_W"], 2),
                "high_52w": round(d["52W_High"], 2),
                "mkt_cap": round(mkt_cap_b, 1),
            }
    except: pass
    return None


# ─── Main scan logic ──────────────────────────────────────────────────────────

progress_data = {"status": "idle", "done": 0, "total": 0, "message": ""}

def run_scan():
    global progress_data
    progress_data = {"status": "running", "done": 0, "total": 0, "message": "Fetching stock universe..."}

    stocks = get_nse_stocks()
    # Limit to first 500 for speed on free tier; remove slice for full scan
    stocks = stocks[:500]
    total = len(stocks)
    progress_data["total"] = total

    results = {
        "s1": [], "s2": [], "s3": [], "s4": [],
        "timestamp": datetime.now().strftime("%d %b %Y, %I:%M %p")
    }

    BATCH = 50
    for i in range(0, total, BATCH):
        batch = stocks[i:i+BATCH]
        progress_data["message"] = f"Scanning {i+1}–{min(i+BATCH, total)} of {total} stocks..."
        try:
            raw = yf.download(
                batch, period="2y", interval="1d",
                group_by="ticker", auto_adjust=True,
                progress=False, threads=True
            )
        except Exception:
            progress_data["done"] += len(batch)
            continue

        for sym in batch:
            try:
                if len(batch) == 1:
                    df_sym = raw.copy()
                else:
                    df_sym = raw[sym].copy() if sym in raw.columns.get_level_values(0) else pd.DataFrame()

                if df_sym.empty or len(df_sym) < 60:
                    continue

                df_sym.index = pd.to_datetime(df_sym.index)
                df_sym = df_sym.dropna(subset=["Close"])

                # Get market cap
                try:
                    info = yf.Ticker(sym).fast_info
                    mkt_cap_b = (info.market_cap or 0) / 1e9
                except:
                    mkt_cap_b = 0

                daily, weekly = compute_indicators(df_sym)

                r1 = run_screener_1(sym, daily, weekly, mkt_cap_b)
                r2 = run_screener_2(sym, daily, weekly, mkt_cap_b)
                r3 = run_screener_3(sym, daily, weekly, mkt_cap_b)
                r4 = run_screener_4(sym, daily, weekly, mkt_cap_b)

                if r1: results["s1"].append(r1)
                if r2: results["s2"].append(r2)
                if r3: results["s3"].append(r3)
                if r4: results["s4"].append(r4)

            except Exception:
                pass
            finally:
                progress_data["done"] += 1

        time.sleep(0.5)  # polite rate limiting

    progress_data["status"] = "done"
    progress_data["results"] = results
    progress_data["message"] = "Scan complete."


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start-scan", methods=["POST"])
def start_scan():
    if progress_data.get("status") == "running":
        return jsonify({"error": "Scan already running"}), 400
    thread = threading.Thread(target=run_scan, daemon=True)
    thread.start()
    return jsonify({"ok": True})

@app.route("/progress")
def progress():
    return jsonify(progress_data)

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)

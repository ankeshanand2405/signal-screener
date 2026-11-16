from flask import Flask, render_template, jsonify
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import requests
from io import StringIO
import time
import threading

app = Flask(__name__)

# ─── Indicators (pure pandas/numpy — no pandas-ta) ────────────────────────────

def sma(series, n):
    return series.rolling(window=n).mean()

def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def rsi(series, n=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=n).mean()
    loss = (-delta.clip(upper=0)).rolling(window=n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def compute_indicators(df_daily):
    df = df_daily.copy()
    # if isinstance(df.columns, pd.MultiIndex):
    #     df.columns = df.columns.get_level_values(0)
    c = df["Close"]
    h = df["High"]
    v = df["Volume"]

    df["SMA10"]     = sma(c, 10)
    df["SMA20"]     = sma(c, 20)
    df["SMA50"]     = sma(c, 50)
    df["EMA10"]     = ema(c, 10)
    df["EMA20"]     = ema(c, 20)
    df["RSI14"]     = rsi(c, 14)
    df["52W_High"]  = h.rolling(252).max()
    df["Avg_Vol10"] = v.rolling(10).mean()
    df["Rel_Vol"]   = v / df["Avg_Vol10"]
    df["Vol_Chg"]   = v.pct_change() * 100
    df["Chg_Open"]  = ((c - df["Open"]) / df["Open"]) * 100

    # Weekly
    weekly = df[["Open","High","Low","Close","Volume"]].resample("W").agg(
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
    try:
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        df = pd.read_csv(StringIO(r.text))
        return [s + ".NS" for s in df["SYMBOL"].tolist()]
    except Exception:
        return FALLBACK_SYMBOLS

# ─── Screeners ────────────────────────────────────────────────────────────────

def screener_1(sym, daily, weekly, mcap):
    if mcap < 25: return None
    try:
        d = daily.iloc[-1]
        if (d["Close"] > d["SMA10"] and d["Close"] > d["SMA20"] and
            d["Close"] > d["SMA50"] and d["Chg_Open"] > 0 and
            d["Rel_Vol"] > 1 and d["RSI14"] > 55):
            return {"symbol": sym.replace(".NS",""), "price": round(d["Close"],2),
                    "rsi": round(d["RSI14"],1), "rel_vol": round(d["Rel_Vol"],2),
                    "chg_open": round(d["Chg_Open"],2), "mkt_cap": round(mcap,1)}
    except: pass

def screener_2(sym, daily, weekly, mcap):
    if mcap < 25: return None
    try:
        d = daily.iloc[-1]; w = weekly.iloc[-1]
        if (d["Close"] > w["SMA10_W"] and d["Close"] > w["SMA20_W"] and
            d["Close"] > w["SMA50_W"] and w["Chg_Open_W"] > 0 and w["RSI14_W"] > 55):
            return {"symbol": sym.replace(".NS",""), "price": round(d["Close"],2),
                    "rsi_w": round(w["RSI14_W"],1), "chg_open_w": round(w["Chg_Open_W"],2),
                    "mkt_cap": round(mcap,1)}
    except: pass

def screener_3(sym, daily, weekly, mcap):
    if mcap < 20: return None
    try:
        d = daily.iloc[-1]
        near_52w = d["52W_High"] >= d["Close"] and d["52W_High"] <= d["Close"] * 1.20
        if (d["Close"] > d["EMA20"] and d["Chg_Open"] > 2 and d["Vol_Chg"] > 0 and
            d["EMA10"] > d["EMA20"] and d["RSI14"] > 55 and near_52w):
            return {"symbol": sym.replace(".NS",""), "price": round(d["Close"],2),
                    "rsi": round(d["RSI14"],1), "chg_open": round(d["Chg_Open"],2),
                    "vol_chg": round(d["Vol_Chg"],1), "high_52w": round(d["52W_High"],2),
                    "mkt_cap": round(mcap,1)}
    except: pass

def screener_4(sym, daily, weekly, mcap):
    if mcap < 20: return None
    try:
        d = daily.iloc[-1]; w = weekly.iloc[-1]
        near_52w = d["52W_High"] >= d["Close"] and d["52W_High"] <= d["Close"] * 1.20
        if (d["Close"] > w["EMA10_W"] and w["EMA10_W"] > w["EMA20_W"] and
            w["RSI14_W"] > 50 and w["Chg_Open_W"] > 2 and near_52w):
            return {"symbol": sym.replace(".NS",""), "price": round(d["Close"],2),
                    "rsi_w": round(w["RSI14_W"],1), "chg_open_w": round(w["Chg_Open_W"],2),
                    "high_52w": round(d["52W_High"],2), "mkt_cap": round(mcap,1)}
    except: pass

# ─── Scan ────────────────────────────────────────────────────────────────────

progress_data = {"status": "idle", "done": 0, "total": 0, "message": ""}

def run_scan():
    global progress_data
    progress_data = {"status": "running", "done": 0, "total": 0, "message": "Fetching stock universe..."}

    stocks = get_nse_stocks()[:800]
    progress_data["total"] = len(stocks)
    results = {"s1":[], "s2":[], "s3":[], "s4":[],
               "timestamp": datetime.now().strftime("%d %b %Y, %I:%M %p")}

    BATCH = 50
    for i in range(0, len(stocks), BATCH):
        batch = stocks[i:i+BATCH]
        progress_data["message"] = f"Scanning {i+1}–{min(i+BATCH, len(stocks))} of {len(stocks)}..."
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
                df_sym.index = pd.to_datetime(df_sym.index)
                df_sym = df_sym.dropna(subset=["Close"])
                try:
                    mcap = (yf.Ticker(sym).fast_info.market_cap or 0) / 1e9
                except:
                    mcap = 0
                daily, weekly = compute_indicators(df_sym)
                for fn, key in [(screener_1,"s1"),(screener_2,"s2"),(screener_3,"s3"),(screener_4,"s4")]:
                    r = fn(sym, daily, weekly, mcap)
                    if r: results[key].append(r)
            except: pass
            finally: progress_data["done"] += 1
        time.sleep(0.5)

    progress_data.update({"status": "done", "results": results, "message": "Scan complete."})

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

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)

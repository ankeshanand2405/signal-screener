"""
build_cache.py - Pre-compute and cache strictly NSE market cap and shares data.
Primary source: Official NSE daily PR Bhavcopy archive (`mcapDDMMYYYY.csv`) via jugaad_data (fast, complete, no rate limits).
Fallback source: NSE EQUITY_L.csv + yfinance `fast_info`.
Run `python build_cache.py` (or `python build_cache.py --refresh`) to update `mcap_cache.json`.
"""

import argparse
import io
import json
import os
import time
import zipfile
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd
import yfinance as yf

try:
    from jugaad_data.nse import NSEDailyReports
    JUGAAD_AVAILABLE = True
except ImportError:
    JUGAAD_AVAILABLE = False

CACHE_FILE = "mcap_cache.json"
NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NIFTY_TOTAL_MARKET_URL = "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
VALID_SERIES = {"EQ", "BE", "SM", "BZ", "RR", "IV"}


def fetch_nse_official_mcap():
    """Fetch official daily NSE Market Cap CSV (`mcapDDMMYYYY.csv`) in one download."""
    if not JUGAAD_AVAILABLE:
        return None, None

    print("Fetching official NSE daily Market Cap report (CM-BHAVCOPY-PR-ZIP)...")
    reports = NSEDailyReports()
    zip_bytes = reports.download_file("CM-BHAVCOPY-PR-ZIP")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        mcap_files = [n for n in zf.namelist() if os.path.basename(n).lower().startswith("mcap") and n.lower().endswith(".csv")]
        if not mcap_files:
            raise ValueError("No mcap CSV found inside CM-BHAVCOPY-PR-ZIP")
        csv_name = mcap_files[0]
        df = pd.read_csv(zf.open(csv_name))

    df.columns = [c.strip() for c in df.columns]
    df["Symbol"] = df["Symbol"].astype(str).str.strip()
    df["Series"] = df["Series"].fillna("").astype(str).str.strip()
    df = df[df["Series"].isin(VALID_SERIES) & (df["Symbol"] != "")].copy()

    df["shares"] = pd.to_numeric(df["Issue Size"], errors="coerce")
    df["price"] = pd.to_numeric(df["Close Price/Paid up value(Rs.)"], errors="coerce")
    df["mcap_rs"] = pd.to_numeric(df["Market Cap(Rs.)"], errors="coerce")

    cache = {}
    for _, row in df.iterrows():
        sym = row["Symbol"]
        shares = int(row["shares"]) if pd.notna(row["shares"]) and row["shares"] > 0 else None
        price = round(float(row["price"]), 2) if pd.notna(row["price"]) and row["price"] > 0 else None
        if pd.notna(row["mcap_rs"]) and row["mcap_rs"] > 0:
            mcap_b = round(float(row["mcap_rs"]) / 1e9, 2)
        elif shares and price:
            mcap_b = round((shares * price) / 1e9, 2)
        else:
            mcap_b = 0.0
        cache[sym] = {
            "shares": shares,
            "mcap_b": mcap_b,
            "price": price,
        }

    trade_date = str(df["Trade Date"].iloc[0]).strip() if not df.empty and "Trade Date" in df.columns else ""
    return cache, f"{csv_name} ({trade_date})" if trade_date else csv_name

def get_nse_symbols():
    """Fetch pure NSE symbols, prioritizing Nifty Total Market (top liquid stocks)."""
    print("Fetching official NSE equity list...")
    symbols = []
    priority_symbols = set()

    # Try getting Nifty Total Market first (top 750 liquid companies)
    try:
        r_tm = requests.get(NIFTY_TOTAL_MARKET_URL, headers=HEADERS, timeout=10)
        if r_tm.status_code == 200:
            df_tm = pd.read_csv(StringIO(r_tm.text))
            priority_symbols = set(df_tm["Symbol"].str.strip().tolist())
            print(f"Loaded {len(priority_symbols)} priority symbols from Nifty Total Market.")
    except Exception as e:
        print(f"Notice: Could not fetch Nifty Total Market list ({e}). Continuing with main list.")

    # Fetch master NSE list
    try:
        r = requests.get(NSE_EQUITY_URL, headers=HEADERS, timeout=15)
        df = pd.read_csv(StringIO(r.text))
        df.columns = [c.strip() for c in df.columns]
        # Only take EQ series (main-board standard equity)
        df_eq = df[df["SERIES"].str.strip() == "EQ"]
        all_symbols = df_eq["SYMBOL"].str.strip().tolist()
        print(f"Loaded {len(all_symbols)} EQ symbols from NSE master list.")
    except Exception as e:
        print(f"Error fetching NSE master list: {e}")
        return []

    # Prioritize: Nifty Total Market first, followed by remaining NSE EQ stocks
    p_list = [s for s in all_symbols if s in priority_symbols]
    rem_list = [s for s in all_symbols if s not in priority_symbols]
    symbols = p_list + rem_list
    return symbols

def fetch_stock_info(sym):
    """Fetch total shares, market cap, and last price for an NSE ticker."""
    ticker_str = f"{sym}.NS"
    try:
        t = yf.Ticker(ticker_str)
        fast = t.fast_info
        shares = getattr(fast, "shares", None)
        mcap = getattr(fast, "market_cap", None)
        price = getattr(fast, "last_price", None)

        if mcap is not None:
            mcap_b = round(mcap / 1e9, 2)
        elif shares and price:
            mcap_b = round((shares * price) / 1e9, 2)
        else:
            mcap_b = 0.0

        return sym, {
            "shares": int(shares) if shares else None,
            "mcap_b": mcap_b,
            "price": round(price, 2) if price else None
        }
    except Exception:
        return sym, None

def save_cache(cache):
    """Sort cache by market cap descending and save to CACHE_FILE."""
    sorted_stocks = dict(sorted(cache.items(), key=lambda x: x[1].get("mcap_b", 0), reverse=True))
    final_data = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_stocks": len(sorted_stocks),
        "stocks": sorted_stocks
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=2)

    above_15b = sum(1 for v in sorted_stocks.values() if v.get("mcap_b", 0) >= 15)
    print(f"\nSuccessfully built '{CACHE_FILE}' with {len(sorted_stocks)} strictly NSE stocks ({above_15b} >= ₹15B)!")
    print("Top 5 stocks by Market Cap:")
    for sym, val in list(sorted_stocks.items())[:5]:
        shares_str = f"{val.get('shares'):,}" if val.get("shares") else "N/A"
        print(f"  • {sym:12}: ₹{val.get('mcap_b', 0):,.1f}B (Shares: {shares_str})")


def build_cache(target_count=None, max_workers=4, refresh=False):
    # 1. Try instant official NSE Market Cap report first (zero rate limits)
    try:
        cache, source_label = fetch_nse_official_mcap()
        if cache:
            print(f"Loaded {len(cache)} securities from {source_label}.")
            if target_count:
                ordered = dict(sorted(cache.items(), key=lambda x: x[1].get("mcap_b", 0), reverse=True)[:target_count])
                cache = ordered
            save_cache(cache)
            return
    except Exception as e:
        print(f"Notice: Official NSE MCAP report unavailable ({e}). Falling back to yfinance...")

    # 2. Fallback: NSE EQUITY_L.csv + yfinance fast_info
    symbols = get_nse_symbols()
    if not symbols:
        print("No symbols found.")
        return

    selected_symbols = symbols[:target_count] if target_count else symbols
    print(f"\nStarting cache build for {len(selected_symbols)} strictly NSE stocks...")
    print(f"Using {max_workers} parallel workers.\n")

    cache = {}
    if not refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cache = data.get("stocks", {})
                print(f"Found existing cache with {len(cache)} symbols. Updating/filling remaining...")
        except Exception:
            cache = {}

    to_fetch = [s for s in selected_symbols if s not in cache]
    print(f"{len(cache)} already cached. Fetching {len(to_fetch)} symbols...\n")

    completed = 0
    total = len(to_fetch)
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(fetch_stock_info, sym): sym for sym in to_fetch}
        for future in as_completed(future_map):
            sym, info = future.result()
            if info:
                cache[sym] = info
            completed += 1
            if completed % 50 == 0 or completed == total:
                elapsed = time.time() - start_time
                pct = (completed / total) * 100
                print(f"[{completed}/{total}] ({pct:.1f}%) processed in {elapsed:.1f}s...")
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "total_stocks": len(cache),
                        "stocks": cache
                    }, f, indent=2)

    save_cache(cache)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build/refresh NSE market cap cache.")
    parser.add_argument("--refresh", action="store_true", help="Force full refresh even when resuming fallback mode.")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers for yfinance fallback.")
    args = parser.parse_args()
    build_cache(target_count=None, max_workers=args.workers, refresh=args.refresh)

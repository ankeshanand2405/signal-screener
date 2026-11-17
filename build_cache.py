"""
build_cache.py - Pre-compute and cache strictly NSE market cap and shares data.
Run this script locally once to generate `mcap_cache.json`.
"""

import json
import os
import time
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd
import yfinance as yf

CACHE_FILE = "mcap_cache.json"
NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NIFTY_TOTAL_MARKET_URL = "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

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

def build_cache(target_count=None, max_workers=20):
    symbols = get_nse_symbols()
    if not symbols:
        print("No symbols found.")
        return

    # Select the target count (None = all NSE EQ stocks)
    if target_count:
        selected_symbols = symbols[:target_count]
    else:
        selected_symbols = symbols
    print(f"\nStarting cache build for {len(selected_symbols)} strictly NSE stocks...")
    print(f"Using {max_workers} parallel workers.\n")

    # Load existing cache if any, to allow resuming
    cache = {}
    if os.path.exists(CACHE_FILE):
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
                # Incremental save
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "total_stocks": len(cache),
                        "stocks": cache
                    }, f, indent=2)

    # Sort cache by mcap_b descending
    sorted_stocks = dict(sorted(cache.items(), key=lambda x: x[1].get("mcap_b", 0), reverse=True))

    final_data = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_stocks": len(sorted_stocks),
        "stocks": sorted_stocks
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=2)

    print(f"\nSuccessfully built '{CACHE_FILE}' with {len(sorted_stocks)} strictly NSE stocks!")
    print(f"Top 5 stocks by Market Cap:")
    for sym, val in list(sorted_stocks.items())[:5]:
        print(f"  • {sym:12}: ₹{val.get('mcap_b', 0):,.1f}B (Shares: {val.get('shares'):,})")

if __name__ == "__main__":
    build_cache(target_count=None, max_workers=20)

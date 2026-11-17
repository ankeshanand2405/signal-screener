# PINAKA — NSE Stock Screener

4 technical screeners for NSE-listed stocks. Run after market close (3:30 PM IST). Click any result to open it on TradingView.

## Screeners

| # | Name | Timeframe | Key Filters |
|---|------|-----------|-------------|
| 1 | Breakout Daily | 1D | Price > SMA 10/20/50, RelVol > 1, RSI > 55 |
| 2 | Breakout Weekly | 1W | Price > SMA 10/20/50 (weekly), RSI > 55 |
| 3 | Trading Scanner | 1D | Price > EMA 20, Chg > 2%, Near 52W High |
| 4 | MT Investing | 1W | EMA 10W > EMA 20W, RSI > 50, Near 52W High |

---

## Deploy to Render (free, runs 24/7)

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
```

Create a new repo on github.com, then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/signal-screener.git
git branch -M main
git push -u origin main
```

### Step 2 — Deploy on Render

1. Go to [render.com](https://render.com) and sign up (free)
2. Click **New → Web Service**
3. Connect your GitHub account and select `signal-screener`
4. Render will auto-detect the `render.yaml` — click **Deploy**
5. Wait ~3 minutes for the first deploy
6. Your app is live at `https://signal-screener.onrender.com`

> **Note:** Free tier sleeps after 15 min of inactivity. First load after sleep takes ~30 seconds.

---

## Run locally (optional)

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in your browser.

---

## Notes

- Scans top liquid NSE stocks ranked by market capitalization.
- Market cap is computed in real-time (`cached_shares * today_close`) using the pre-computed `mcap_cache.json`.
- Runs on EOD data — best used after 4:00 PM IST.
- To refresh the NSE market cap cache once every few months:
  ```bash
  python build_cache.py
  ```

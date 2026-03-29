# Triple Confirmation Pattern — Backtester

**Stan Weinstein Stage Analysis | NSE Stock Universe | Browser-Based | No Installation Required**

This project lets you backtest the **Weinstein Triple Confirmation Pattern** across ~500 NSE-listed stocks for the last 5+ years — entirely in your browser using **GitHub Codespaces**. You do not need to install Python, Jupyter, or any other software on your computer.

---

## What is the Triple Confirmation Pattern?

Based on Stan Weinstein's book *"Secrets for Profiting in Bull and Bear Markets"*, a Triple Confirmation signal fires when a stock satisfies **all six conditions simultaneously** on a weekly chart:

| # | Condition | What it means |
|---|---|---|
| 1 | New 50-week High | Stock breaks above the highest price of the past 50 weeks |
| 2 | Wide Range Week | The week's price range is at least 2× the 26-week average true range |
| 3 | Strong Close | The stock closes in the upper half of the week's range |
| 4 | Volume Spike | Volume is at least 2× the 4-week average volume |
| 5 | Positive RS | Mansfield Relative Strength vs CNX500 is above zero |
| 6 | Above 30W SMA | The stock is trading above its 30-week moving average |

---

## How to Run the Backtest (Step-by-Step)

### Step 1 — Open GitHub Codespaces
1. Go to this repository on GitHub
2. Click the green **`< > Code`** button
3. Click the **Codespaces** tab
4. Click **"Create codespace on main"** (or the branch name)

> The first time, Codespaces takes about **60–90 seconds** to set up. You will see a progress bar at the bottom of the screen. Wait for it to finish.

---

### Step 2 — Open the Notebook
Once the Codespace is ready, look at the **left panel (file explorer)** and click on:
```
backtest.ipynb
```

---

### Step 3 — Run a Quick Test First (Recommended)
Before running the full scan, do a quick 2-minute test on 20 stocks:

1. The notebook opens with `QUICK_TEST = True` already set in **Section 2**
2. Click **Run → Run All Cells** from the top menu
3. Wait for the progress bar to finish (~2 minutes)
4. Check the results table at the bottom — you should see signals listed

---

### Step 4 — Run the Full Scan (500 Stocks)
If the quick test worked:

1. Scroll to **Section 2** in the notebook
2. Change `QUICK_TEST = True` to `QUICK_TEST = False`
3. Click **Run → Run All Cells** again
4. Wait for completion (~12–18 minutes depending on internet speed)

---

### Step 5 — Download Your Results
When the scan finishes, your results are in the **`results/`** folder:

1. Look in the left panel for the `results/` folder
2. Click the arrow to expand it
3. Right-click on `signals_2019_2024.csv`
4. Select **Download**
5. Open the file in **Microsoft Excel** or **Google Sheets**

---

### Step 6 — Understand the Results File

The CSV file has one row per signal. Here is what each column means:

| Column | Meaning |
|---|---|
| `symbol` | NSE ticker (e.g. `RELIANCE.NS`) |
| `signal_date` | The week the Triple Confirmation fired |
| `signal_price` | Closing price on signal week (in rupees) |
| `stage` | Weinstein Stage at time of signal (2 = ideal) |
| `mansfield_rs` | Relative Strength vs CNX500 (positive = outperforming) |
| `ret_1m` | % return approximately 1 month after the signal |
| `ret_3m` | % return approximately 3 months after the signal |
| `ret_6m` | % return approximately 6 months after the signal |
| `ret_1y` | % return approximately 1 year after the signal |

---

### Step 7 — Verify a Signal on TradingView
To double-check a signal against the Pine Script indicator:

1. Open TradingView and search for the stock (remove `.NS`, e.g. search `RELIANCE`)
2. Switch the chart to the **Weekly** timeframe
3. Add the Pine Script indicator to the chart
4. Navigate to the signal date shown in the CSV
5. Confirm the **green triangle** appears on the same weekly bar

---

## Project Files

```
Triple-Confirmation-Pattern/
├── .devcontainer/
│   └── devcontainer.json      <- Codespaces setup (auto-installs everything)
├── data/
│   └── nifty500_symbols.csv   <- ~500 NSE stock tickers to scan
├── results/                   <- Your output files appear here after running
├── triple_confirmation.py     <- Core logic (Python translation of the Pine Script)
├── backtest.ipynb             <- Main notebook -- this is what you run
└── requirements.txt           <- Python libraries (auto-installed by Codespaces)
```

---

## Frequently Asked Questions

**Q: Do I need to pay for anything?**
A: No. GitHub Codespaces offers free monthly usage (60 core-hours/month for free accounts). Yahoo Finance data via yfinance is also free with no API key needed.

**Q: How long does the full scan take?**
A: About 12-18 minutes for all ~500 stocks. The notebook shows a live progress bar.

**Q: What if a stock shows an error or is missing?**
A: Some older or smaller stocks may not have complete data on Yahoo Finance. These are automatically skipped, and their names are saved to results/failed_downloads.txt.

**Q: The results show NaN for 1-year return on some signals. Why?**
A: If a signal fired within the last 52 weeks of your selected end date, there is not yet enough future data to calculate the 1-year return. This is expected and correct.

**Q: Can I change the date range?**
A: Yes. In Section 2 of the notebook, change START_DATE and END_DATE to any dates you want, then click Run All Cells again.

**Q: Can I add more stocks?**
A: Yes. Open data/nifty500_symbols.csv, add a new row in the format TICKER.NS,Company Name,Sector, save, and re-run the notebook.

---

## Important Disclaimer

This backtest is for **research and educational purposes only**. It does not account for brokerage commissions, taxes, bid-ask spread, or liquidity constraints. Historical performance of a pattern does not guarantee future results. Always conduct your own due diligence before making investment decisions.

"""
triple_confirmation.py
======================
Core Python implementation of Stan Weinstein's Triple Confirmation Pattern.

This module translates the Pine Script indicator logic into Python so that
it can be run on historical weekly data for hundreds of NSE stocks at once.

Functions
---------
download_weekly_data   : Fetch weekly OHLCV data from Yahoo Finance
compute_indicators     : Calculate all moving averages, ATR, Mansfield RS, etc.
detect_signals         : Identify bars where the Triple Confirmation fires
compute_forward_returns: Measure price performance after each signal
run_backtest           : Orchestrate the full backtest pipeline
"""

import time
import warnings
import os

import numpy as np
import pandas as pd
import yfinance as yf
from tqdm.notebook import tqdm

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# Constants (match Pine Script defaults)
# ─────────────────────────────────────────────
BENCHMARK_TICKER = "^CNX500"        # Nifty 500 index for Mansfield RS
FALLBACK_BENCHMARK = "^NSEI"        # Nifty 50 as fallback

SMA_LEN   = 30    # 30-week SMA
EMA10_LEN = 10    # 10-week EMA
EMA40_LEN = 40    # 40-week EMA
ATR_LEN   = 26    # ATR window for range filter
HIGH_LEN  = 50    # Lookback for "new 50-week high"
RS_LEN    = 52    # Mansfield RS smoothing
VOL_LEN   = 4     # Volume MA window
VOL_MULT  = 2.0   # Volume spike multiplier
ANOMALY   = 2.5   # Smart volume anomaly threshold
RANGE_MULT = 2.0  # Range must be >= this * ATR


# ─────────────────────────────────────────────
# Helper: Smart Volume MA (anomaly-filtered)
# ─────────────────────────────────────────────
def _smart_vol_avg(vals: np.ndarray, thresh: float = ANOMALY) -> float:
    """
    Rolling window function used inside pandas .apply().

    Returns the standard mean of the window, UNLESS the single highest
    bar's volume is more than `thresh` times the average of all other bars.
    In that case the spike is excluded and the remaining average is returned.
    This prevents a single volume-spike week from inflating the baseline,
    which would suppress legitimate volume breakouts in subsequent weeks.
    """
    if len(vals) < 2:
        return float(vals.mean())
    max_v = vals.max()
    sum_without = vals.sum() - max_v
    n_without = len(vals) - 1
    avg_without = sum_without / n_without
    if avg_without > 0 and max_v > thresh * avg_without:
        return float(avg_without)
    return float(vals.mean())


def smart_vol_sma(volume: pd.Series,
                  window: int = VOL_LEN,
                  thresh: float = ANOMALY) -> pd.Series:
    """Vectorised smart volume moving average over a rolling window."""
    return volume.rolling(window, min_periods=window).apply(
        lambda x: _smart_vol_avg(x, thresh), raw=True
    )


# ─────────────────────────────────────────────
# Step 1: Download Weekly Data
# ─────────────────────────────────────────────
def download_weekly_data(symbols: list,
                         start: str,
                         end: str,
                         batch_size: int = 50,
                         sleep_sec: float = 2.0) -> dict:
    """
    Download weekly OHLCV data for a list of NSE symbols plus the benchmark.

    Parameters
    ----------
    symbols    : list of Yahoo Finance tickers (e.g. ['RELIANCE.NS', 'TCS.NS'])
    start      : start date string  'YYYY-MM-DD'
    end        : end date string    'YYYY-MM-DD'
    batch_size : how many tickers to fetch per yfinance call
    sleep_sec  : pause between batches (avoids rate-limiting)

    Returns
    -------
    dict  {symbol: DataFrame(Open, High, Low, Close, Volume)  weekly-resampled}
    Also stores benchmark_df in returned dict under key '__benchmark__'
    """
    result = {}
    failed = []

    # --- Download benchmark first ---
    print("Downloading benchmark index data...")
    bench_df = _fetch_single(BENCHMARK_TICKER, start, end)
    if bench_df is None or bench_df.empty:
        print(f"  Warning: {BENCHMARK_TICKER} not available, trying {FALLBACK_BENCHMARK}")
        bench_df = _fetch_single(FALLBACK_BENCHMARK, start, end)
    if bench_df is None or bench_df.empty:
        raise RuntimeError("Could not download benchmark index data. Check internet connection.")
    result["__benchmark__"] = bench_df
    print(f"  Benchmark loaded: {len(bench_df)} weekly bars\n")

    # --- Download stocks in batches ---
    batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    print(f"Downloading {len(symbols)} stocks in {len(batches)} batches of up to {batch_size}...")

    for batch_num, batch in enumerate(tqdm(batches, desc="Downloading batches"), 1):
        try:
            raw = yf.download(
                batch,
                start=start,
                end=end,
                interval="1wk",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            for sym in batch:
                try:
                    if len(batch) == 1:
                        df = raw.copy()
                    else:
                        df = raw.xs(sym, axis=1, level=1).copy()
                    df = _clean_weekly(df)
                    if df is not None and len(df) >= 60:
                        result[sym] = df
                    else:
                        failed.append(sym)
                except Exception:
                    failed.append(sym)
        except Exception as e:
            print(f"  Batch {batch_num} error: {e}")
            for sym in batch:
                failed.append(sym)

        if batch_num < len(batches):
            time.sleep(sleep_sec)

    # Log failures
    if failed:
        os.makedirs("results", exist_ok=True)
        with open("results/failed_downloads.txt", "w") as f:
            for s in failed:
                f.write(s + "\n")
        print(f"\n  {len(failed)} symbols failed (saved to results/failed_downloads.txt)")

    print(f"\nSuccessfully loaded {len(result) - 1} stocks.\n")
    return result


def _fetch_single(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Download a single ticker as weekly data. Returns None on failure."""
    try:
        df = yf.download(ticker, start=start, end=end,
                         interval="1wk", auto_adjust=True, progress=False)
        return _clean_weekly(df)
    except Exception:
        return None


def _clean_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardise a yfinance weekly DataFrame.
    - Keep only OHLCV columns
    - Drop rows where Close is NaN
    - Drop rows where Volume is 0 (market halts / data gaps)
    - Flatten MultiIndex columns if present
    """
    if df is None or df.empty:
        return None
    # Flatten MultiIndex (happens with single-ticker downloads in some yfinance versions)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # Keep standard columns
    needed = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        return None
    df = df[needed].copy()
    df = df[df["Close"].notna()]
    df = df[df["Volume"] > 0]
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df


# ─────────────────────────────────────────────
# Step 2: Compute Indicators
# ─────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame,
                       benchmark_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add all technical indicator columns to a weekly stock DataFrame.

    Columns added
    -------------
    sma30       : 30-week SMA of Close
    ema10       : 10-week EMA
    ema40       : 40-week EMA
    sma_slope   : sma30 - sma30.shift(1)  (positive = trending up)
    stage       : Weinstein stage (1, 2, 3, or 4)
    tr          : True Range
    atr26       : 26-week Average True Range
    high50      : Highest High of the PREVIOUS 50 weeks (shift(1).rolling(50).max())
    vol_sma4    : Smart volume moving average (4-week, anomaly filtered)
    raw_rs      : Close / benchmark_close
    rs_sma52    : 52-week SMA of raw_rs
    mansfield_rs: ((raw_rs / rs_sma52) - 1) * 10
    """
    c = df.copy()

    # --- Moving averages ---
    c["sma30"]  = c["Close"].rolling(SMA_LEN, min_periods=SMA_LEN).mean()
    c["ema10"]  = c["Close"].ewm(span=EMA10_LEN, adjust=False).mean()
    c["ema40"]  = c["Close"].ewm(span=EMA40_LEN, adjust=False).mean()
    c["sma_slope"] = c["sma30"] - c["sma30"].shift(1)

    # --- Weinstein Stage ---
    #   Stage 2: Close > sma30  AND  sma trending up
    #   Stage 4: Close < sma30  AND  sma trending down
    #   Stage 3: Close < sma30  AND  sma trending up   (topping)
    #   Stage 1: Close > sma30  AND  sma trending down (basing)
    above = c["Close"] > c["sma30"]
    up    = c["sma_slope"] > 0
    c["stage"] = np.select(
        [above & up, ~above & ~up, above & ~up, ~above & up],
        [2, 4, 1, 3],
        default=np.nan
    )

    # --- True Range ---
    hl  = c["High"] - c["Low"]
    hpc = (c["High"] - c["Close"].shift(1)).abs()
    lpc = (c["Low"]  - c["Close"].shift(1)).abs()
    c["tr"]    = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    c["atr26"] = c["tr"].rolling(ATR_LEN, min_periods=ATR_LEN).mean()

    # --- New 50-week High ---
    # Pine Script: ta.highest(high, 50)[1]  → highest of the PREVIOUS 50 bars
    # The shift(1) means we do NOT include the current bar in the lookback.
    c["high50"] = c["High"].shift(1).rolling(HIGH_LEN, min_periods=HIGH_LEN).max()

    # --- Smart Volume MA ---
    c["vol_sma4"] = smart_vol_sma(c["Volume"])

    # --- Mansfield Relative Strength ---
    # Align benchmark to stock's date index (forward-fill up to 5 trading days)
    bench_aligned = benchmark_df["Close"].reindex(c.index, method="ffill", limit=5)
    c["raw_rs"]      = c["Close"] / bench_aligned
    c["rs_sma52"]    = c["raw_rs"].rolling(RS_LEN, min_periods=RS_LEN).mean()
    c["mansfield_rs"] = ((c["raw_rs"] / c["rs_sma52"]) - 1) * 10

    return c


# ─────────────────────────────────────────────
# Step 3: Detect Triple Confirmation Signals
# ─────────────────────────────────────────────
def detect_signals(df: pd.DataFrame,
                   vol_mult: float = VOL_MULT,
                   range_mult: float = RANGE_MULT) -> pd.DataFrame:
    """
    Apply all six Triple Confirmation conditions to the indicator DataFrame.

    Conditions (ALL must be True on the same weekly bar)
    ----------------------------------------------------
    1. new_high  : Weekly High > highest High of previous 50 weeks
    2. big_range : Week's range (High - Low) >= range_mult × ATR26
    3. close_pos : Close is in the upper 50% of the week's range
    4. vol_spike : Volume >= vol_mult × smart 4-week volume average
    5. rs_strong : Mansfield RS > 0  (outperforming benchmark)
    6. above_sma : Close > 30-week SMA

    Adds a boolean column 'signal' to the DataFrame.
    """
    wrange = df["High"] - df["Low"]

    new_high  = df["High"] > df["high50"]
    big_range = wrange >= (range_mult * df["atr26"])
    # Guard against zero-range weeks (market holiday / bad data)
    close_pos = np.where(
        wrange > 0,
        (df["Close"] - df["Low"]) / wrange >= 0.5,
        False
    )
    vol_spike  = df["Volume"] >= (vol_mult * df["vol_sma4"])
    rs_strong  = df["mansfield_rs"] > 0
    above_sma  = df["Close"] > df["sma30"]

    df = df.copy()
    df["signal"] = (
        new_high & big_range & pd.Series(close_pos, index=df.index) &
        vol_spike & rs_strong & above_sma
    )
    return df


# ─────────────────────────────────────────────
# Step 4: Compute Forward Returns
# ─────────────────────────────────────────────
def compute_forward_returns(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    For every bar where signal == True, look up the Close price and
    calculate how the stock performed over the next 4, 13, 26, and 52 weeks.

    Returns a DataFrame with one row per signal.
    """
    signal_rows = df[df["signal"] == True].copy()
    if signal_rows.empty:
        return pd.DataFrame()

    records = []
    closes = df["Close"]
    idx    = df.index

    for sig_date, row in signal_rows.iterrows():
        sig_price = row["Close"]
        sig_pos   = idx.get_loc(sig_date)

        def _fwd(weeks):
            pos = sig_pos + weeks
            if pos < len(idx):
                future_price = closes.iloc[pos]
                if pd.notna(future_price) and sig_price > 0:
                    return (future_price - sig_price) / sig_price
            return np.nan

        records.append({
            "symbol"      : symbol,
            "signal_date" : sig_date.strftime("%Y-%m-%d"),
            "signal_price": round(sig_price, 2),
            "stage"       : int(row["stage"]) if pd.notna(row["stage"]) else np.nan,
            "mansfield_rs": round(row["mansfield_rs"], 2) if pd.notna(row["mansfield_rs"]) else np.nan,
            "ret_1m"      : _fwd(4),
            "ret_3m"      : _fwd(13),
            "ret_6m"      : _fwd(26),
            "ret_1y"      : _fwd(52),
        })

    return pd.DataFrame(records)


# ─────────────────────────────────────────────
# Step 5: Run Full Backtest
# ─────────────────────────────────────────────
def run_backtest(data: dict,
                 vol_mult: float = VOL_MULT,
                 range_mult: float = RANGE_MULT) -> pd.DataFrame:
    """
    Orchestrate the full backtest pipeline over all downloaded stocks.

    Parameters
    ----------
    data       : dict returned by download_weekly_data()
    vol_mult   : volume spike multiplier (default 2.0)
    range_mult : range filter multiplier (default 2.0)

    Returns
    -------
    DataFrame with all signals found, including forward returns.
    """
    if "__benchmark__" not in data:
        raise ValueError("data dict must contain '__benchmark__' key. "
                         "Run download_weekly_data() first.")

    benchmark_df = data["__benchmark__"]
    symbols = [k for k in data.keys() if k != "__benchmark__"]

    all_results = []

    print(f"Running signal detection on {len(symbols)} stocks...\n")
    for sym in tqdm(symbols, desc="Scanning stocks"):
        try:
            df = data[sym]
            df = compute_indicators(df, benchmark_df)
            df = detect_signals(df, vol_mult=vol_mult, range_mult=range_mult)
            signals = compute_forward_returns(df, sym)
            if not signals.empty:
                all_results.append(signals)
        except Exception as e:
            # Skip broken stocks silently; don't crash the whole run
            pass

    if not all_results:
        print("No signals found. Try widening the date range or parameters.")
        return pd.DataFrame()

    master = pd.concat(all_results, ignore_index=True)
    master = master.sort_values("signal_date").reset_index(drop=True)

    # Format return columns as percentages for readability
    for col in ["ret_1m", "ret_3m", "ret_6m", "ret_1y"]:
        master[col] = (master[col] * 100).round(2)

    print(f"\nDone!  Found {len(master)} Triple Confirmation signals "
          f"across {master['symbol'].nunique()} stocks.")
    return master


# ─────────────────────────────────────────────
# Convenience: Summary Statistics
# ─────────────────────────────────────────────
def print_summary(results: pd.DataFrame) -> None:
    """Print a plain-English performance summary table to the console."""
    if results.empty:
        print("No results to summarise.")
        return

    print("\n" + "=" * 60)
    print("TRIPLE CONFIRMATION PATTERN — BACKTEST SUMMARY")
    print("=" * 60)
    print(f"Total signals found : {len(results)}")
    print(f"Unique stocks       : {results['symbol'].nunique()}")
    print(f"Date range          : {results['signal_date'].min()} → {results['signal_date'].max()}")
    print()

    horizons = [
        ("1 Month  (~4 weeks)", "ret_1m"),
        ("3 Months (~13 weeks)", "ret_3m"),
        ("6 Months (~26 weeks)", "ret_6m"),
        ("1 Year   (~52 weeks)", "ret_1y"),
    ]

    print(f"{'Horizon':<25} {'Signals':>8} {'Winners':>8} {'Win %':>8} {'Avg Ret':>10} {'Median':>10}")
    print("-" * 72)
    for label, col in horizons:
        clean = results[col].dropna()
        if len(clean) == 0:
            continue
        winners = (clean > 0).sum()
        win_pct = winners / len(clean) * 100
        avg_ret = clean.mean()
        med_ret = clean.median()
        print(f"{label:<25} {len(clean):>8} {winners:>8} {win_pct:>7.1f}%"
              f" {avg_ret:>+9.1f}%  {med_ret:>+9.1f}%")

    print("=" * 60)
    print("Note: Returns are % change from signal close price.")
    print("NaN values = signal occurred too close to end of data period.\n")

"""
data_fetcher.py
Fetch OHLCV data using yfinance and cache it based on config parameters.
"""

import os
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

import config

def _cache_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("=", "").replace("-", "_")
    return Path(config.CACHE_DIR) / f"{safe}_{config.DATA_PERIOD}.parquet"

def _is_stale(path: Path) -> bool:
    if not path.exists():
        return True
    age_hours = (time.time() - os.path.getmtime(path)) / 3600.0
    return age_hours > config.CACHE_MAX_AGE_HOURS

def fetch_symbol(symbol: str) -> pd.DataFrame:
    """
    Returns OHLCV DataFrame for a single symbol.
    Uses parquet cache if available and not stale.
    """
    cache_dir = Path(config.CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(symbol)

    if not _is_stale(path):
        return pd.read_parquet(path)

    print(f"  Downloading {symbol} ...")
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=config.DATA_PERIOD, interval=config.DATA_INTERVAL, auto_adjust=True)

    if df.empty:
        raise ValueError(f"No data returned for {symbol}")

    # Handle MultiIndex if any
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Remove timezone
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Keep only target columns
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[cols].copy()

    df.to_parquet(path)
    return df

def fetch_all() -> dict:
    """
    Returns dict of {symbol: DataFrame} for all configured symbols.
    """
    data = {}
    for symbol in config.ALL_SYMBOLS:
        try:
            data[symbol] = fetch_symbol(symbol)
        except Exception as e:
            print(f"  WARNING: Failed to fetch {symbol}: {e}")
    return data

"""
data_fetcher.py
Yahoo Finance에서 2년치 OHLCV 데이터를 다운로드하고 parquet으로 캐시.
"""

import os
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

SYMBOLS = ["SPY", "^VIX", "DX-Y.NYB", "CL=F", "^TNX", "GC=F", "BTC-USD", "^KS11"]

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
CACHE_TTL = 86400  # 1일 (초)


def _cache_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("=", "").replace("-", "_")
    return CACHE_DIR / f"{safe}_2y.parquet"


def _is_stale(path: Path) -> bool:
    if not path.exists():
        return True
    age = time.time() - os.path.getmtime(path)
    return age > CACHE_TTL


def fetch_symbol(symbol: str, period: str = "2y") -> pd.DataFrame:
    """
    단일 심볼의 OHLCV DataFrame 반환.
    캐시가 있고 1일 이내이면 캐시에서 로드, 아니면 yfinance에서 다운로드.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(symbol)

    if not _is_stale(path):
        df = pd.read_parquet(path)
        return df

    print(f"  Downloading {symbol} ...")
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, auto_adjust=True)

    if df.empty:
        raise ValueError(f"No data returned for {symbol}")

    # MultiIndex 컬럼 처리
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # timezone 제거 (통일)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # 필요한 컬럼만 유지
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[cols].copy()

    df.to_parquet(path)
    return df


def fetch_all(period: str = "2y") -> dict:
    """
    모든 심볼 데이터를 {symbol: DataFrame} 딕셔너리로 반환.
    실패한 심볼은 건너뜀.
    """
    data = {}
    for symbol in SYMBOLS:
        try:
            data[symbol] = fetch_symbol(symbol, period=period)
        except Exception as e:
            print(f"  WARNING: Failed to fetch {symbol}: {e}")
    return data

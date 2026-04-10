"""
data_fetcher.py
Yahoo Finance에서 장기 OHLCV 데이터를 다운로드하고 parquet으로 캐시.
기본 20년+ (max period) 데이터를 가져와 2008 금융위기 등 주요 이벤트 포함.
"""

import os
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

# ── 기본 심볼 목록 (멀티팩터 레짐에 필요한 핵심 지표) ──────────────────
CORE_SYMBOLS = [
    "SPY",        # S&P 500 ETF
    "^VIX",       # 변동성지수
    "TLT",        # 20년+ 장기국채 ETF
    "^TNX",       # 미국 10년물 국채 금리
    "^IRX",       # 미국 3개월 국채 금리 (수익률곡선 inversion용)
    "DX-Y.NYB",   # 달러 인덱스
    "CL=F",       # WTI 원유 선물
    "GC=F",       # 금 선물
]

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
CACHE_TTL = 86400  # 1일 (초)


def _cache_path(symbol: str, period: str) -> Path:
    safe = symbol.replace("^", "").replace("=", "").replace("-", "_").replace(".", "_")
    return CACHE_DIR / f"{safe}_{period}.parquet"


def _is_stale(path: Path) -> bool:
    if not path.exists():
        return True
    age = time.time() - os.path.getmtime(path)
    return age > CACHE_TTL


def fetch_symbol(symbol: str, period: str = "max") -> pd.DataFrame:
    """
    단일 심볼의 OHLCV DataFrame 반환.
    캐시가 있고 1일 이내이면 캐시에서 로드, 아니면 yfinance에서 다운로드.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(symbol, period)

    if not _is_stale(path):
        df = pd.read_parquet(path)
        return df

    print(f"  Downloading {symbol} (period={period}) ...")
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


def fetch_all(period: str = "max", extra_symbols: list = None) -> dict:
    """
    모든 심볼 데이터를 {symbol: DataFrame} 딕셔너리로 반환.
    extra_symbols로 추가 심볼(개별 종목 등)을 지정 가능.
    실패한 심볼은 건너뜀.
    """
    symbols = list(CORE_SYMBOLS)
    if extra_symbols:
        for s in extra_symbols:
            if s not in symbols:
                symbols.append(s)

    data = {}
    for symbol in symbols:
        try:
            data[symbol] = fetch_symbol(symbol, period=period)
        except Exception as e:
            print(f"  WARNING: Failed to fetch {symbol}: {e}")
    return data

import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta

def fetch_all(period="5y") -> dict[str, pd.DataFrame]:
    symbols = {
        "SPY": "SPY",
        "^VIX": "^VIX",
        "DX-Y.NYB": "DX-Y.NYB",
        "CL=F": "CL=F",
        "^TNX": "^TNX",
        "GC=F": "GC=F",
        "TLT": "TLT",
        "SCHD": "SCHD"
    }
    
    cache_dir = os.path.expanduser("~/georisk/data/cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    data = {}
    for sym_name, sym_ticker in symbols.items():
        cache_file = os.path.join(cache_dir, f"{sym_name}_{period}.parquet")
        
        need_fetch = True
        if os.path.exists(cache_file):
            mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
            if datetime.now() - mtime < timedelta(hours=24):
                print(f"Skipping fetch for {sym_name}. Cache is fresh.")
                need_fetch = False
        
        if not need_fetch:
            try:
                df = pd.read_parquet(cache_file)
                data[sym_name] = df
                continue
            except Exception as e:
                print(f"Failed to read cache for {sym_name}: {e}")
                need_fetch = True
                
        if need_fetch:
            print(f"Fetching {sym_name} for {period}...")
            try:
                ticker = yf.Ticker(sym_ticker)
                df = ticker.history(period=period)
                if df.empty:
                    print(f"Warning: No data for {sym_name}. Skipping.")
                    continue
                # Strip timezone
                df.index = df.index.tz_localize(None)
                # Keep OHLCV
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                df.to_parquet(cache_file)
                data[sym_name] = df
            except Exception as e:
                print(f"Warning: Failed to fetch {sym_name}: {e}")
                
    return data

import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta
import config

def fetch_all(period: str = None) -> dict[str, pd.DataFrame]:
    if period is None:
        period = config.DATA_PERIOD
        
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    
    data = {}
    downloaded = 0
    cached = 0
    failed = 0
    
    for symbol in config.ALL_SYMBOLS:
        cache_file = os.path.join(config.CACHE_DIR, f"{symbol}_{period}.parquet")
        
        need_fetch = True
        if os.path.exists(cache_file):
            mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
            if datetime.now() - mtime < timedelta(hours=config.CACHE_MAX_AGE_HOURS):
                need_fetch = False
        
        if not need_fetch:
            try:
                df = pd.read_parquet(cache_file)
                data[symbol] = df
                cached += 1
                continue
            except Exception as e:
                need_fetch = True
                
        if need_fetch:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=period)
                if df.empty:
                    failed += 1
                    continue
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                df.to_parquet(cache_file)
                data[symbol] = df
                downloaded += 1
            except Exception as e:
                failed += 1
                
    print(f"Downloaded {downloaded} symbols, cached {cached}, failed {failed}")
    return data

if __name__ == "__main__":
    fetch_all()

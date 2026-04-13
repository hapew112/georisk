import pandas as pd
import numpy as np

def _base_signals(spy_df):
    df = pd.DataFrame(index=spy_df.index)
    df['date'] = df.index
    df['regime'] = "CALM"
    df['stress_score'] = 0
    df['action'] = "HOLD"
    return df

def alt_a_vix_meanreversion(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = _base_signals(data["SPY"]).copy()
    if "^VIX" not in data: return df
    
    import config
    vix = data["^VIX"]['Close']
    vix_sma = vix.rolling(window=config.VIX_SMA_PERIOD).mean()
    vix_std = vix.rolling(window=config.VIX_SMA_PERIOD).std()
    
    # Avoid zero division
    vix_zscore = (vix - vix_sma) / vix_std.replace(0, np.nan)
    
    # DEFENSIVE if > ZSCORE_DEFENSIVE
    defensive_mask = vix_zscore > config.VIX_ZSCORE_DEFENSIVE
    
    df.loc[defensive_mask, 'action'] = "DEFENSIVE"
    df.loc[defensive_mask, 'regime'] = "CRISIS"
    return df

def alt_b_cross_asset(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = _base_signals(data["SPY"]).copy()
    
    count_series = pd.Series(0, index=df.index)
    
    def add_condition(symbol):
        if symbol in data:
            price = data[symbol]['Close']
            sma = price.rolling(window=20).mean()
            return price < sma
        return pd.Series(False, index=df.index)
        
    c1 = add_condition("SPY")
    c2 = add_condition("TLT")
    c3 = add_condition("GC=F")
    c4 = add_condition("BTC-USD")
    
    count_series = c1.astype(int) + c2.astype(int) + c3.astype(int) + c4.astype(int)
    
    defensive_mask = count_series >= 3
    df.loc[defensive_mask, 'action'] = "DEFENSIVE"
    df.loc[defensive_mask, 'regime'] = "CRISIS"
    df['stress_score'] = count_series
    
    return df

def alt_c_yield_vix(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = _base_signals(data["SPY"]).copy()
    
    # proxy: TLT 20d return - SPY 20d return
    if "TLT" in data and "SPY" in data and "^VIX" in data:
        tlt_ret = data["TLT"]['Close'].pct_change(20)
        spy_ret = data["SPY"]['Close'].pct_change(20)
        spread_proxy = tlt_ret - spy_ret
        
        vix = data["^VIX"]['Close']
        
        defensive_mask = (spread_proxy > 0.03) & (vix > 20)
        
        df.loc[defensive_mask, 'action'] = "DEFENSIVE"
        df.loc[defensive_mask, 'regime'] = "CRISIS"
        
    return df

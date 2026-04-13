import pandas as pd
import numpy as np
import config

def compute_signals(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if "SPY" not in data or "^VIX" not in data:
        return pd.DataFrame()
        
    df = pd.DataFrame(index=data["SPY"].index)
    df['spy_close'] = data["SPY"]['Close']
    df['vix_close'] = data["^VIX"]['Close']
    
    # VIX Z-Score Calculation
    vix = df['vix_close']
    vix_sma20 = vix.rolling(window=config.VIX_SMA_PERIOD).mean()
    vix_std20 = vix.rolling(window=config.VIX_SMA_PERIOD).std()
    
    # Avoid div by zero
    vix_zscore = (vix - vix_sma20) / vix_std20.replace(0, np.nan)
    
    df['vix_sma20'] = vix_sma20
    df['vix_std20'] = vix_std20
    df['vix_zscore'] = vix_zscore
    df['stress_score'] = vix_zscore
    
    # Regime (Strictly VIX level based)
    def get_regime(vix_val):
        if pd.isna(vix_val): return "CALM"
        if vix_val < 15: return "CALM"
        if 15 <= vix_val < 20: return "NORMAL"
        if 20 <= vix_val < 28: return "ELEVATED"
        return "CRISIS"
        
    df['regime'] = df['vix_close'].apply(get_regime)
    
    # Actions (Strictly z-score based, plus CRISIS override)
    df['action'] = "HOLD"
    df.loc[df['vix_zscore'] > config.VIX_ZSCORE_DEFENSIVE, 'action'] = "DEFENSIVE"
    
    # Force DEFENSIVE if CRISIS regime
    df.loc[df['regime'] == "CRISIS", 'action'] = "DEFENSIVE"
    
    df.reset_index(inplace=True)
    if 'Date' in df.columns:
        df.rename(columns={'Date': 'date'}, inplace=True)
    
    return df

def compute_signals_legacy(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if "SPY" not in data or "^VIX" not in data:
        return pd.DataFrame()
        
    df = pd.DataFrame(index=data["SPY"].index)
    df['spy_close'] = data["SPY"]['Close']
    df['vix_close'] = data["^VIX"]['Close']
    
    def safe_pct_change(symbol):
        if symbol in data:
            return data[symbol]['Close'].pct_change()
        return pd.Series(0, index=df.index)

    vix_pct = safe_pct_change("^VIX")
    dollar_pct = safe_pct_change("DX-Y.NYB")
    oil_pct = safe_pct_change("CL=F")
    yield_pct = safe_pct_change("^TNX")
    gold_pct = safe_pct_change("GC=F")
    
    df['vix_spike'] = vix_pct > config.STRESS_THRESHOLDS["vix_spike"] / 100
    df['dollar_surge'] = dollar_pct > config.STRESS_THRESHOLDS["dollar_surge"] / 100
    df['oil_spike'] = oil_pct > config.STRESS_THRESHOLDS["oil_spike"] / 100
    df['yield_jump'] = yield_pct > config.STRESS_THRESHOLDS["yield_jump"] / 100
    df['gold_rush'] = gold_pct > config.STRESS_THRESHOLDS["gold_rush"] / 100
    
    df['stress_score'] = df[['vix_spike', 'dollar_surge', 'oil_spike', 'yield_jump', 'gold_rush']].sum(axis=1)
    
    def get_regime(vix):
        if pd.isna(vix): return "CALM"
        if vix < 15: return "CALM"
        if 15 <= vix < 20: return "NORMAL"
        if 20 <= vix < 28: return "ELEVATED"
        return "CRISIS"
        
    df['regime'] = df['vix_close'].apply(get_regime)
    
    def get_action(row):
        score = row['stress_score']
        reg = row['regime']
        if score >= config.SIGNAL_MIN_STRESS:
            return "DEFENSIVE"
        if reg == "CRISIS":
            return "DEFENSIVE"
        if score >= config.SIGNAL_MIN_STRESS - 1 and reg in ["ELEVATED", "CRISIS"]:
            return "DEFENSIVE"
        return "HOLD"
        
    df['action'] = df.apply(get_action, axis=1)
    df.reset_index(inplace=True)
    if 'Date' in df.columns:
        df.rename(columns={'Date': 'date'}, inplace=True)
    return df

if __name__ == "__main__":
    from data_fetcher import fetch_all
    data = fetch_all()
    signals = compute_signals(data)
    print(signals.head())
    print("Action counts:\n", signals['action'].value_counts())
    print("Regime counts:\n", signals['regime'].value_counts())

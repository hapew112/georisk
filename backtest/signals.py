import pandas as pd
import numpy as np

def compute_signals(data: dict) -> pd.DataFrame:
    # Need SPY index to align everything
    if 'SPY' not in data:
        raise ValueError("SPY data missing")
    
    spy = data['SPY']
    dates = spy.index
    
    # Extract series for calculations
    def get_close(sym):
        return data[sym]['Close'].reindex(dates).ffill()
    
    vix = get_close('^VIX')
    dxy = get_close('DX-Y.NYB')
    wti = get_close('CL=F')
    tnx = get_close('^TNX')
    gold = get_close('GC=F')
    
    # 1d change
    vix_pct = vix.pct_change()
    dxy_pct = dxy.pct_change()
    wti_pct = wti.pct_change()
    tnx_pct = tnx.pct_change()
    gold_pct = gold.pct_change()
    
    stress_score = (
        (vix_pct > 0.15).astype(int) +
        (dxy_pct > 0.008).astype(int) +
        (wti_pct > 0.05).astype(int) +
        (tnx_pct > 0.03).astype(int) +
        (gold_pct > 0.02).astype(int)
    )
    
    # VIX regime
    vix_regime = pd.Series('CALM', index=dates)
    vix_regime.loc[(vix >= 15) & (vix < 20)] = 'NORMAL'
    vix_regime.loc[(vix >= 20) & (vix <= 28)] = 'ELEVATED'
    vix_regime.loc[vix > 28] = 'CRISIS'
    
    # Signal
    signal = pd.Series('HOLD', index=dates)
    is_defensive = (vix_regime.isin(['ELEVATED', 'CRISIS'])) | (stress_score >= 2)
    signal.loc[is_defensive] = 'DEFENSIVE'
    
    return pd.DataFrame({
        'date': dates,
        'stress_score': stress_score,
        'vix_regime': vix_regime,
        'signal': signal
    }).reset_index(drop=True)

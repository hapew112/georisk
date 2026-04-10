"""
signals.py
Calculate daily composite stress_score and VIX regime based on config.
"""

import pandas as pd
import config

def get_vix_regime(vix_val: float) -> str:
    for regime, (low, high) in config.VIX_REGIMES.items():
        if low <= vix_val < high:
            return regime
    return "CRISIS"  # fallback

def compute_signals(data: dict) -> pd.DataFrame:
    """
    Computes daily stress signal logic from config thresholds.
    """
    spy = data.get(config.SYMBOLS["equity"][0])
    if spy is None:
        raise ValueError("Equity benchmark (SPY) data is required to build the signal index")

    idx = spy.index

    def close_series(symbol: str) -> pd.Series:
        df = data.get(symbol)
        if df is None or df.empty:
            return pd.Series(dtype=float, index=idx)
        return df["Close"].reindex(idx).ffill()

    vix  = close_series(config.SYMBOLS["vix"][0])
    dxy  = close_series(config.SYMBOLS["dollar"][0])
    wti  = close_series(config.SYMBOLS["oil"][0])
    tnx  = close_series(config.SYMBOLS["yield"][0])
    gold = close_series(config.SYMBOLS["gold"][0])

    # Calculate 1-day percentage change (0.01 = 1%)
    # And convert to percentage points to match config's 15.0 format
    vix_chg  = vix.pct_change() * 100.0
    dxy_chg  = dxy.pct_change() * 100.0
    wti_chg  = wti.pct_change() * 100.0
    tnx_chg  = tnx.pct_change() * 100.0
    gold_chg = gold.pct_change() * 100.0

    t_vix = config.STRESS_THRESHOLDS["vix_spike"]
    t_dxy = config.STRESS_THRESHOLDS["dollar_surge"]
    t_wti = config.STRESS_THRESHOLDS["oil_spike"]
    t_tnx = config.STRESS_THRESHOLDS["yield_jump"]
    t_gld = config.STRESS_THRESHOLDS["gold_rush"]

    vix_spike    = vix_chg > t_vix
    dollar_surge = dxy_chg > t_dxy
    oil_spike    = wti_chg > t_wti
    yield_jump   = tnx_chg > t_tnx
    gold_rush    = gold_chg > t_gld

    stress_score = (
        vix_spike.astype(int) +
        dollar_surge.astype(int) +
        oil_spike.astype(int) +
        yield_jump.astype(int) +
        gold_rush.astype(int)
    )

    result = pd.DataFrame({
        "date":         idx,
        "vix_close":    vix,
        "vix_spike":    vix_spike,
        "dollar_surge": dollar_surge,
        "oil_spike":    oil_spike,
        "yield_jump":   yield_jump,
        "gold_rush":    gold_rush,
        "stress_score": stress_score,
    }).set_index("date")

    result["vix_regime"] = result["vix_close"].apply(get_vix_regime)

    # First row is NaN due to pct_change
    result = result.dropna(subset=["stress_score"])

    # Define Signal Fire Boolean (based on README "Combined Signal")
    # if stress >= 3: DEFENSIVE
    # if stress >= SIGNAL_MIN_STRESS and regime >= SIGNAL_MIN_REGIME: DEFENSIVE
    # if regime == CRISIS: DEFENSIVE
    
    # We need a numeric hierarchy for regimes
    regimes = list(config.VIX_REGIMES.keys())
    # ["CALM", "NORMAL", "ELEVATED", "CRISIS"]

    def is_signal_fired(row):
        stress = row["stress_score"]
        reg = row["vix_regime"]
        if stress >= 3:
            return True
        if reg == "CRISIS":
            return True
        
        # dynamic from config
        if reg in regimes and config.SIGNAL_MIN_REGIME in regimes:
            if regimes.index(reg) >= regimes.index(config.SIGNAL_MIN_REGIME):
                if stress >= config.SIGNAL_MIN_STRESS:
                    return True
                    
        return False
        
    result["signal_fired"] = result.apply(is_signal_fired, axis=1)

    return result

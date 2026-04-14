import numpy as np
import pandas as pd

def risk_parity_weights(asset_prices, lookback=20):
    """
    Compute risk parity weights across multiple assets based on trailing volatility.
    asset_prices: dict {symbol: price_series}
    """
    vols = {}
    for sym, prices in asset_prices.items():
        if prices is None or len(prices) < lookback + 1:
            continue
        rets = prices.pct_change().dropna()
        vol = rets.tail(lookback).std()
        if vol > 0:
            vols[sym] = vol
            
    if not vols:
        # Fallback: equal weight if no valid vol
        symbols = list(asset_prices.keys())
        return {s: 1.0/len(symbols) for s in symbols}
        
    inv_vols = {s: 1.0/v for s, v in vols.items()}
    total_inv = sum(inv_vols.values())
    return {s: inv/total_inv for s, inv in inv_vols.items()}

def get_allocation(spy_prices, tlt_prices, regime, config, gld_prices=None):
    """
    Returns allocation dict: {"SPY": x, "TLT": y, "GLD": z, "SGOV": w}
    All values sum to 1.0.
    """
    hybrid_caps = getattr(config, 'HYBRID_CAPS', {})
    rp_regimes = getattr(config, 'HYBRID_RP_REGIMES', ["ELEVATED", "CRISIS"])
    lookback = getattr(config, 'RP_LOOKBACK', 20)
    
    # 1. CALM / NORMAL: Return fixed weights directly
    if regime not in rp_regimes:
        return hybrid_caps.get(regime, {"SPY": 1.0, "TLT": 0.0, "GLD": 0.0, "SGOV": 0.0})
        
    # 2. ELEVATED / CRISIS: Compute Risk Parity
    rp_assets = {"SPY": spy_prices, "TLT": tlt_prices}
    if gld_prices is not None and len(gld_prices) > lookback:
        rp_assets["GLD"] = gld_prices
        
    rp_w = risk_parity_weights(rp_assets, lookback=lookback)
    
    # Initialize with RP results
    spy_w = rp_w.get("SPY", 0.0)
    tlt_w = rp_w.get("TLT", 0.0)
    gld_w = rp_w.get("GLD", 0.0)
    sgov_w = 0.0
    
    caps = hybrid_caps.get(regime, {})
    spy_max = caps.get("SPY_MAX", 1.0)
    gld_max = caps.get("GLD_MAX", 1.0)
    sgov_min = caps.get("SGOV_MIN", 0.0)
    
    # Apply SGOV minimum (cash buffer)
    if sgov_min > 0:
        sgov_w = sgov_min
        remaining = 1.0 - sgov_w
        # Scale RP weights to fit remaining space
        total_rp = spy_w + tlt_w + gld_w
        if total_rp > 0:
            spy_w = (spy_w / total_rp) * remaining
            tlt_w = (tlt_w / total_rp) * remaining
            gld_w = (gld_w / total_rp) * remaining
            
    # Apply SPY cap: reduce SPY, move excess to TLT
    if spy_w > spy_max:
        excess = spy_w - spy_max
        spy_w = spy_max
        tlt_w += excess
        
    # Apply GLD cap: reduce GLD, move excess to TLT
    if gld_w > gld_max:
        excess = gld_w - gld_max
        gld_w = gld_max
        tlt_w += excess
        
    # Final normalization
    total = spy_w + tlt_w + gld_w + sgov_w
    return {
        "SPY": spy_w / total,
        "TLT": tlt_w / total,
        "GLD": gld_w / total,
        "SGOV": sgov_w / total
    }

if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    from data_fetcher import fetch_all
    import config as cfg
    
    data = fetch_all("1y")
    spy = data["SPY"]["Close"]
    tlt = data["TLT"]["Close"]
    gld = data.get("GLD", {}).get("Close")
    if gld is None:
        # Mock GLD for testing if not cached
        gld = spy * 0.3
    
    print("Regime-Aware Hybrid Allocation Validation")
    print("═════════════════════════════════════════")
    
    for regime in ["CALM", "NORMAL", "ELEVATED", "CRISIS"]:
        w = get_allocation(spy, tlt, regime, cfg, gld_prices=gld)
        print(f"{regime:<10}: SPY {w['SPY']:>4.1%}, TLT {w['TLT']:>4.1%}, GLD {w['GLD']:>4.1%}, SGOV {w['SGOV']:>4.1%}")

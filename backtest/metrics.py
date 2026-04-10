"""
metrics.py
Pure functions to calculate signal quality, portfolio metrics, and success criteria.
"""

import math
import numpy as np
import pandas as pd
import config

def compute_forward_returns(spy: pd.Series, signal_dates: list) -> pd.DataFrame:
    spy_vals = spy.values
    spy_idx = spy.index
    n = len(spy_vals)

    idx_map = {d: i for i, d in enumerate(spy_idx)}

    rows = []
    for entry in signal_dates:
        date = entry["date"]
        score = entry["score"]

        pos = idx_map.get(date)
        if pos is None: continue

        base = spy_vals[pos]
        if base == 0 or math.isnan(base): continue

        def ret_at(offset):
            target = pos + offset
            if target >= n: return float("nan")
            v = spy_vals[target]
            if math.isnan(v): return float("nan")
            return (v - base) / base * 100.0

        end5 = min(pos + 6, n)
        window = spy_vals[pos:end5]
        valid = window[~np.isnan(window)]
        if len(valid) > 1:
            dd = (min(valid) - base) / base * 100.0
        else:
            dd = float("nan")

        rows.append({
            "date":        date,
            "score":       score,
            "ret_1d":      ret_at(1),
            "ret_3d":      ret_at(3),
            "ret_5d":      ret_at(5),
            "ret_10d":     ret_at(10),
            "drawdown_5d": dd,
        })

    return pd.DataFrame(rows)

def compute_baseline(spy: pd.Series) -> dict:
    vals = spy.values
    n = len(vals)
    rets_3d, rets_5d, rets_10d = [], [], []

    for i in range(n):
        base = vals[i]
        if base == 0 or math.isnan(base): continue

        def r(offset):
            t = i + offset
            if t >= n: return float("nan")
            v = vals[t]
            return (v - base) / base * 100.0

        rets_3d.append(r(3))
        rets_5d.append(r(5))
        rets_10d.append(r(10))

    def safe_mean(lst):
        valid = [x for x in lst if not math.isnan(x)]
        return float(np.mean(valid)) if valid else float("nan")

    return {
        "baseline_avg_3d":  safe_mean(rets_3d),
        "baseline_avg_5d":  safe_mean(rets_5d),
        "baseline_avg_10d": safe_mean(rets_10d),
    }

def calculate_mdd(cum_returns: pd.Series) -> float:
    roll_max = cum_returns.cummax()
    drawdown = cum_returns / roll_max - 1.0
    return float(drawdown.min() * 100.0)

def compute_portfolio_performance(data: dict, signals_df: pd.DataFrame) -> dict:
    """Simulates Buy&Hold vs GeoRisk Portfolio."""
    spy = data[config.SYMBOLS["equity"][0]]["Close"]
    tlt = data[config.SYMBOLS["bond"][0]]["Close"] if config.SYMBOLS["bond"][0] in data else spy * 0 + 1 # fallback cash

    df = pd.DataFrame({"SPY": spy, "TLT": tlt}).dropna()
    # Join signals
    df = df.join(signals_df[["vix_regime", "stress_score", "signal_fired"]]).ffill()
    df = df.dropna()

    spy_ret = df["SPY"].pct_change().fillna(0)
    tlt_ret = df["TLT"].pct_change().fillna(0)
    cash_ret = 0.0

    # Buy and hold SPY
    bh_cum = (1 + spy_ret).cumprod()
    
    # GeoRisk allocation logic
    geo_ret = []
    
    # Shift regime by 1 day to simulate buying at today's close for tomorrow's return
    alloc_regime = df["vix_regime"].shift(1).fillna("NORMAL")
    alloc_score = df["stress_score"].shift(1).fillna(0)

    for i in range(len(df)):
        regime = alloc_regime.iloc[i]
        score = alloc_score.iloc[i]
        
        # Override to crisis allocation if stress is high
        if score >= 3:
            regime = "CRISIS"
            
        alloc = config.PORTFOLIO_ALLOCATIONS.get(regime, config.PORTFOLIO_ALLOCATIONS["NORMAL"])
        w_spy = alloc.get("SPY", 1.0)
        w_tlt = alloc.get("TLT", 0.0)
        w_cash = alloc.get("cash", 0.0)
        
        r = w_spy * spy_ret.iloc[i] + w_tlt * tlt_ret.iloc[i] + w_cash * cash_ret
        geo_ret.append(r)
        
    geo_ret_series = pd.Series(geo_ret, index=df.index)
    geo_cum = (1 + geo_ret_series).cumprod()

    days = len(df)
    years = days / 252.0 if days > 0 else 1.0

    bh_cagr = (bh_cum.iloc[-1] ** (1/years) - 1) * 100 if years > 0 and len(bh_cum) > 0 else 0
    geo_cagr = (geo_cum.iloc[-1] ** (1/years) - 1) * 100 if years > 0 and len(geo_cum) > 0 else 0

    bh_mdd = calculate_mdd(bh_cum)
    geo_mdd = calculate_mdd(geo_cum)

    bh_sharpe = (bh_cagr / (spy_ret.std() * math.sqrt(252) * 100)) if spy_ret.std() > 0 else 0
    geo_sharpe = (geo_cagr / (geo_ret_series.std() * math.sqrt(252) * 100)) if geo_ret_series.std() > 0 else 0

    return {
        "bh_cagr": float(bh_cagr),
        "bh_sharpe": float(bh_sharpe),
        "bh_mdd": float(bh_mdd),
        "geo_cagr": float(geo_cagr),
        "geo_sharpe": float(geo_sharpe),
        "geo_mdd": float(geo_mdd),
    }

def compute_metrics(forward_df: pd.DataFrame, spy: pd.Series, data: dict, signals_df: pd.DataFrame) -> dict:
    if forward_df.empty:
        return {"total_signals": 0}

    total = len(forward_df)

    def mean_col(col):
        vals = forward_df[col].dropna()
        return float(vals.mean()) if len(vals) > 0 else float("nan")

    def hit_rate(col):
        vals = forward_df[col].dropna()
        if len(vals) == 0: return float("nan")
        return float((vals < 0).sum() / len(vals))

    avg_ret_3d  = mean_col("ret_3d")
    avg_ret_5d  = mean_col("ret_5d")
    avg_ret_10d = mean_col("ret_10d")
    hr_3d       = hit_rate("ret_3d")
    hr_5d       = hit_rate("ret_5d")

    ret3_vals = forward_df["ret_3d"].dropna()
    false_alarm_rate = float((ret3_vals >= 0).sum() / len(ret3_vals)) if len(ret3_vals) > 0 else float("nan")
    avg_dd      = mean_col("drawdown_5d")
    worst_case  = float(forward_df["ret_5d"].dropna().min()) if 'ret_5d' in forward_df and len(forward_df["ret_5d"].dropna()) > 0 else float("nan")

    baseline = compute_baseline(spy)

    def diff(signal_val, baseline_val):
        if math.isnan(signal_val) or math.isnan(baseline_val): return float("nan")
        return signal_val - baseline_val

    edge = diff(avg_ret_3d, baseline["baseline_avg_3d"])
    
    # Kelly
    win_rate = hr_3d
    winners = forward_df["ret_3d"][forward_df["ret_3d"] < 0] # "Win" means SPY dropped
    losers = forward_df["ret_3d"][forward_df["ret_3d"] >= 0]
    avg_win = abs(winners.mean()) if len(winners) > 0 else 0.0001
    avg_loss = abs(losers.mean()) if len(losers) > 0 else 0.0001
    
    if not math.isnan(win_rate) and avg_win > 0:
        kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    else:
        kelly = 0.0
        
    if kelly > config.KELLY_MAX_FRACTION: kelly = config.KELLY_MAX_FRACTION
    if kelly < 0: kelly = 0.0

    portfolio = compute_portfolio_performance(data, signals_df)

    # Regime Breakdown
    regime_breakdown = {}
    for r in config.VIX_REGIMES.keys():
        r_sigs = signals_df[signals_df["vix_regime"] == r]
        # compute 3d return for all days in regime
        r_fwd = compute_forward_returns(spy, [{"date": d, "score": 0} for d in r_sigs.index])
        avg_3d = r_fwd["ret_3d"].mean() if not r_fwd.empty else float("nan")
        regime_breakdown[r] = {
            "days": len(r_sigs),
            "avg_ret_3d": float(avg_3d) if not math.isnan(avg_3d) else None
        }
    regime_breakdown["CRISIS"] = {
            "days": len(signals_df[signals_df["vix_regime"] == "CRISIS"]),
            "avg_ret_3d": float(compute_forward_returns(spy, [{"date": d, "score": 0} for d in signals_df[signals_df["vix_regime"] == "CRISIS"].index])["ret_3d"].mean()) if not signals_df[signals_df["vix_regime"] == "CRISIS"].empty else None
    }

    return {
        "total_signals":          total,
        "avg_return_3d":          avg_ret_3d,
        "avg_return_5d":          avg_ret_5d,
        "avg_return_10d":         avg_ret_10d,
        "hit_rate_3d":            hr_3d,
        "hit_rate_5d":            hr_5d,
        "false_alarm_rate":       false_alarm_rate,
        "avg_drawdown_5d":        avg_dd,
        "worst_case":             worst_case,
        "baseline_avg_3d":        baseline["baseline_avg_3d"],
        "baseline_avg_5d":        baseline["baseline_avg_5d"],
        "baseline_avg_10d":       baseline["baseline_avg_10d"],
        "signal_vs_baseline_3d":  edge,
        "kelly_f":                float(kelly),
        "kelly_win_rate":         float(win_rate),
        "kelly_avg_win":          float(avg_win),
        "kelly_avg_loss":         float(avg_loss),
        "portfolio":              portfolio,
        "regime_breakdown":       regime_breakdown
    }

def verdict(metrics: dict) -> str:
    hr3 = metrics.get("hit_rate_3d", 0)
    edge = metrics.get("signal_vs_baseline_3d", 0)
    p = metrics.get("portfolio", {})
    bh_mdd = p.get("bh_mdd", 0)
    geo_mdd = p.get("geo_mdd", 0)

    if math.isnan(hr3) or math.isnan(edge) or bh_mdd == 0:
        return "Insufficient data for verdict."
        
    pass_hr = hr3 >= config.SUCCESS_HIT_RATE_3D
    pass_edge = edge <= config.SUCCESS_EDGE_VS_BASELINE
    pass_mdd = abs(geo_mdd) <= abs(bh_mdd) * config.SUCCESS_MDD_RATIO

    passes = sum([pass_hr, pass_edge, pass_mdd])
    if passes == 3:
        return "SUCCESS! Signal has strong predictive edge."
    return f"Needs adjustment (Passed {passes}/3 criteria)."

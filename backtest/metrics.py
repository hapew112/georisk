import pandas as pd
import numpy as np
import config
from allocation import get_allocation

def signal_quality(signals_df: pd.DataFrame, spy_df: pd.DataFrame) -> dict:
    total_signals = 0
    hits = {1: 0, 3: 0, 5: 0, 10: 0}
    returns = {1: [], 3: [], 5: [], 10: []}
    drawdowns_5d = []
    
    individual_signals = []
    
    spy_df = spy_df.copy()
    spy_df['ret_3d'] = spy_df['Close'].pct_change(3).shift(-3)
    baseline_avg_3d = spy_df['ret_3d'].mean() * 100
    
    def_days = signals_df[signals_df['action'] == "DEFENSIVE"]
    total_signals = len(def_days)
    spy_closes = spy_df['Close'].tolist()
    
    for _, row in def_days.iterrows():
        signal_date = row['date']
        try:
            idx = spy_df.index.get_loc(signal_date)
            spy_price = spy_closes[idx]
        except KeyError:
            continue
            
        target_indices = {1: idx+1, 3: idx+3, 5: idx+5, 10: idx+10}
        max_len = len(spy_closes)
        signal_data = {"date": str(signal_date), "score": int(row['stress_score']), "regime": row['regime'], "spy_price": float(spy_price)}
        
        for w, target_idx in target_indices.items():
            if target_idx < max_len:
                fwd_price = spy_closes[target_idx]
                pct_ret = (fwd_price / spy_price) - 1
                returns[w].append(pct_ret)
                if pct_ret < 0:
                    hits[w] += 1
                signal_data[f"ret_{w}d"] = float(pct_ret)
                
        if idx+5 < max_len:
            window_prices = spy_closes[idx:idx+6]
            max_p = np.maximum.accumulate(window_prices)
            dd = (window_prices / max_p) - 1
            mdd = float(dd.min())
            drawdowns_5d.append(mdd)
            signal_data["dd_5d"] = mdd
            
        individual_signals.append(signal_data)

    res = {
        "total_signals": total_signals,
        "baseline_avg_3d": baseline_avg_3d,
    }
    for w in [1, 3, 5, 10]:
        hits_count = hits[w]
        count = len(returns[w])
        res[f"hit_rate_{w}d"] = (hits_count / count) if count > 0 else 0
        res[f"avg_return_{w}d"] = np.mean(returns[w]) * 100 if count > 0 else 0
        
    res["avg_drawdown_5d"] = (np.mean(drawdowns_5d) * 100) if drawdowns_5d else 0
    res["worst_case_5d"] = (np.min(drawdowns_5d) * 100) if drawdowns_5d else 0
    res["false_alarm_rate"] = 1 - res.get("hit_rate_5d", 0)
    res["edge"] = res.get("avg_return_3d", 0) - res.get("baseline_avg_3d", 0)
    res["individual_signals"] = individual_signals
    
    return res

def portfolio_comparison(signals_df, spy_df, tlt_df, allocations, method="rp", gld_df=None, sgov_df=None) -> dict:
    if "Close" not in tlt_df:
        tlt_df = pd.DataFrame(index=spy_df.index)
        tlt_df['Close'] = spy_df['Close'] * 0
        
    df = pd.DataFrame(index=spy_df.index)
    df['spy_ret'] = spy_df['Close'].pct_change()
    df['tlt_ret'] = tlt_df['Close'].pct_change().reindex(df.index, fill_value=0)
    df['gld_ret'] = gld_df['Close'].pct_change().reindex(df.index, fill_value=0) if gld_df is not None else 0
    df['sgov_ret'] = sgov_df['Close'].pct_change().reindex(df.index, fill_value=0) if sgov_df is not None else 0
    
    bh_ret = df['spy_ret']
    
    # Use both regime and action for allocation decisions
    sig_data = signals_df.set_index('date')[['regime', 'action']].reindex(df.index)
    sig_data['regime'] = sig_data['regime'].fillna("CALM")
    sig_data['action'] = sig_data['action'].fillna("HOLD")
    
    gr_ret = pd.Series(0.0, index=df.index)
    
    for date, row in sig_data.iterrows():
        regime = row['regime']
        action = row['action']
        
        # If action is DEFENSIVE, use CRISIS allocation (tactical override)
        # Otherwise use the market regime allocation
        alloc_regime = "CRISIS" if action == "DEFENSIVE" else regime
        
        idx = df.index.get_loc(date)
        if isinstance(idx, slice):
            continue
            
        if method == "fixed":
            # Use fixed weights from config (v7)
            fixed = allocations.get(alloc_regime, {"SPY": 1.0, "TLT": 0.0, "cash": 0.0})
            w_spy, w_tlt, w_gld, w_sgov = fixed.get("SPY", 1.0), fixed.get("TLT", 0.0), fixed.get("GLD", 0.0), fixed.get("SGOV", 0.0)
        else:
            # Use dynamic Hybrid Risk Parity (v8)
            spy_prices = spy_df['Close'].iloc[:idx+1]
            tlt_prices = tlt_df['Close'].iloc[:idx+1]
            gld_prices = gld_df['Close'].iloc[:idx+1] if gld_df is not None else None
            alloc = get_allocation(spy_prices, tlt_prices, alloc_regime, config, gld_prices=gld_prices)
            w_spy = alloc.get("SPY", 1.0)
            w_tlt = alloc.get("TLT", 0.0)
            w_gld = alloc.get("GLD", 0.0)
            w_sgov = alloc.get("SGOV", 0.0)
            
        spy_c = df.iloc[idx]['spy_ret']
        tlt_c = df.iloc[idx]['tlt_ret']
        gld_c = df.iloc[idx]['gld_ret']
        sgov_c = df.iloc[idx]['sgov_ret']
        
        gr_ret.iloc[idx] = (
            w_spy * (spy_c if not pd.isna(spy_c) else 0) +
            w_tlt * (tlt_c if not pd.isna(tlt_c) else 0) +
            w_gld * (gld_c if not pd.isna(gld_c) else 0) +
            w_sgov * (sgov_c if not pd.isna(sgov_c) else 0)
        )
        
    bh_eq = (1 + bh_ret.fillna(0)).cumprod()
    gr_eq = (1 + gr_ret.fillna(0)).cumprod()
    
    years = len(bh_eq) / 252
    bh_cagr = calc_cagr(bh_eq, years)
    gr_cagr = calc_cagr(gr_eq, years)
    
    bh_mdd = calc_mdd(bh_eq)
    gr_mdd = calc_mdd(gr_eq)
    
    bh_sharpe = calc_sharpe(bh_ret.fillna(0))
    gr_sharpe = calc_sharpe(gr_ret.fillna(0))
    
    return {
        "bh_cagr": bh_cagr * 100,
        "bh_mdd": bh_mdd * 100,
        "bh_sharpe": bh_sharpe,
        "bh_calmar": abs(bh_cagr / bh_mdd) if bh_mdd != 0 else 0,
        "bh_var95": calc_var(bh_ret.fillna(0)),
        "bh_cvar95": calc_cvar(bh_ret.fillna(0)),
        "gr_cagr": gr_cagr * 100,
        "gr_mdd": gr_mdd * 100,
        "gr_sharpe": gr_sharpe,
        "gr_calmar": abs(gr_cagr / gr_mdd) if gr_mdd != 0 else 0,
        "gr_var95": calc_var(gr_ret.fillna(0)),
        "gr_cvar95": calc_cvar(gr_ret.fillna(0)),
        "cagr_delta": (gr_cagr - bh_cagr) * 100,
        "mdd_delta": (abs(bh_mdd) - abs(gr_mdd)) * 100,
        "sharpe_delta": gr_sharpe - bh_sharpe,
        "bh_ret": bh_ret,
        "gr_ret": gr_ret
    }

def kelly_criterion(hit_rate, avg_win, avg_loss) -> float:
    if hit_rate <= 0:
        return -1.0
    avg_win = abs(avg_win)
    avg_loss = abs(avg_loss)
    if avg_loss == 0: return config.KELLY_MAX_FRACTION
    b = avg_win / avg_loss
    if b == 0: return -1.0
    p = hit_rate
    q = 1.0 - p
    f = (p * b - q) / b
    if f <= 0: return -1.0
    return min(f, config.KELLY_MAX_FRACTION)

def calc_sharpe(returns_series, risk_free_rate=0.045) -> float:
    if len(returns_series) == 0: return 0.0
    mean = returns_series.mean()
    std = returns_series.std()
    if std == 0: return 0.0
    rf_daily = (1 + risk_free_rate)**(1/252) - 1
    ann_mean = (mean - rf_daily) * 252
    ann_std = std * np.sqrt(252)
    return float(ann_mean / ann_std)

def calc_mdd(equity_curve) -> float:
    if len(equity_curve) == 0: return 0.0
    max_p = np.maximum.accumulate(equity_curve)
    dd = (equity_curve / max_p) - 1
    return float(dd.min())

def calc_cagr(equity_curve, years) -> float:
    if len(equity_curve) == 0 or years <= 0: return 0.0
    end_val = equity_curve.iloc[-1]
    start_val = equity_curve.iloc[0]
    if start_val == 0: return 0.0
    return float((end_val / start_val)**(1/years) - 1)

def calc_var(returns_series, confidence=0.95) -> float:
    """Historical VaR at given confidence level (returned as positive loss %)."""
    if len(returns_series) == 0: return 0.0
    return float(-np.percentile(returns_series.dropna(), (1 - confidence) * 100) * 100)

def calc_cvar(returns_series, confidence=0.95) -> float:
    """Expected Shortfall (CVaR) — mean of losses beyond VaR threshold."""
    if len(returns_series) == 0: return 0.0
    clean = returns_series.dropna()
    threshold = np.percentile(clean, (1 - confidence) * 100)
    tail = clean[clean <= threshold]
    if len(tail) == 0: return 0.0
    return float(-tail.mean() * 100)

import argparse
import sys
import json
import os
import math
from datetime import datetime
from data_fetcher import fetch_all
from signals import compute_signals
from metrics import signal_quality, portfolio_comparison, kelly_criterion
import config

def run_backtest(periods):
    for period in periods:
        data = fetch_all(period)
        if "SPY" not in data or "TLT" not in data:
            print("Missing core symbols. Skipping.")
            continue
            
        signals = compute_signals(data)
        if signals.empty:
            print("Failed to compute signals.")
            continue
            
        spy_df = data["SPY"]
        tlt_df = data["TLT"]
        gld_df = data.get("GLD")
        sgov_df = data.get("SGOV")
        
        quality = signal_quality(signals, spy_df)
        
        # Calculate v7: Fixed Allocations (PORTFOLIO_ALLOCATIONS has correct SPY/TLT/cash keys)
        port_v7 = portfolio_comparison(signals, spy_df, tlt_df, config.PORTFOLIO_ALLOCATIONS, method="fixed", gld_df=gld_df, sgov_df=sgov_df)
        # Calculate v8: Hybrid Risk Parity
        port_v8 = portfolio_comparison(signals, spy_df, tlt_df, config.HYBRID_CAPS, method="rp", gld_df=gld_df, sgov_df=sgov_df)
        
        # Use v8 as the primary for the main report
        portfolio = port_v8
        
        gr_r = portfolio.get("gr_ret")
        bh_r = portfolio.get("bh_ret")
        active = gr_r != bh_r
        
        if active.sum() > 0:
            edge_ret = gr_r[active] - bh_r[active]
            wins = edge_ret[edge_ret > 0]
            losses = edge_ret[edge_ret <= 0]
            avg_win = wins.mean() if len(wins) > 0 else 0
            avg_loss = losses.mean() if len(losses) > 0 else 0
            hit_rate = len(wins) / len(edge_ret)
        else:
            avg_win = 0; avg_loss = 0; hit_rate = 0

        kelly_f = kelly_criterion(hit_rate, avg_win, abs(avg_loss))
        kelly_pct = kelly_f * 100 if kelly_f > 0 else 0
        
        worst_case_date = "N/A"
        worst_dd = 0
        for s in quality["individual_signals"]:
            if "dd_5d" in s and s["dd_5d"] < worst_dd:
                worst_dd = s["dd_5d"]
                worst_case_date = s["date"]
                
        calm_days = signals[signals['regime'] == "CALM"]
        norm_days = signals[signals['regime'] == "NORMAL"]
        elev_days = signals[signals['regime'] == "ELEVATED"]
        cris_days = signals[signals['regime'] == "CRISIS"]
        
        def regime_ret(days_df):
            if len(days_df) == 0: return 0.0
            rets = []
            spy_closes = spy_df['Close'].tolist()
            spy_dates = spy_df.index
            for d in days_df['date']:
                try:
                    idx = spy_dates.get_loc(d)
                    if idx + 3 < len(spy_closes):
                        rets.append((spy_closes[idx+3] / spy_closes[idx]) - 1)
                except KeyError:
                    pass
            return sum(rets)/len(rets)*100 if rets else 0.0

        n_calm = len(calm_days)
        n_norm = len(norm_days)
        n_elev = len(elev_days)
        n_cris = len(cris_days)
        
        calm_ret = regime_ret(calm_days)
        norm_ret = regime_ret(norm_days)
        elev_ret = regime_ret(elev_days)
        cris_ret = regime_ret(cris_days)
        
        start_date = data["SPY"].index[0].strftime("%Y-%m-%d")
        end_date = data["SPY"].index[-1].strftime("%Y-%m-%d")
        
        hit_rate_3d = quality.get("hit_rate_3d", 0) * 100
        hit_rate_5d = quality.get("hit_rate_5d", 0) * 100
        n_hits_3d = int(quality["total_signals"] * quality.get("hit_rate_3d", 0))
        
        report = f"""
GeoRisk Stress Backtest ({start_date} → {end_date}, {period})
═══════════════════════════════════════════════════════

Signal Summary (stress>={config.SIGNAL_MIN_STRESS} OR regime>={config.SIGNAL_MIN_REGIME})
  Signals fired:    {quality['total_signals']} times
  Hit rate (3d):    {hit_rate_3d:.1f}%  ({n_hits_3d}/{quality['total_signals']} → SPY dropped)
  Hit rate (5d):    {hit_rate_5d:.1f}%
  Avg return 3d:    {quality.get('avg_return_3d', 0):.2f}%  (baseline: {quality.get('baseline_avg_3d', 0):.2f}%)
  Avg drawdown 5d:  {quality.get('avg_drawdown_5d', 0):.2f}%
  Worst case:       {quality.get('worst_case_5d', 0):.2f}%  ({worst_case_date})
  False alarms:     {quality.get('false_alarm_rate', 0)*100:.1f}%
  Edge vs baseline: {quality.get('edge', 0):.2f}%

VIX Regime Breakdown
  CALM (VIX<15):     {n_calm} days, avg 3d ret: {calm_ret:.2f}%
  NORMAL (15-20):    {n_norm} days, avg 3d ret: {norm_ret:.2f}%
  ELEVATED (20-28):  {n_elev} days, avg 3d ret: {elev_ret:.2f}%
  CRISIS (28+):      {n_cris} days, avg 3d ret: {cris_ret:.2f}%

Portfolio Comparison ({period})
  Buy & Hold:    CAGR {portfolio['bh_cagr']:.1f}%, Sharpe {portfolio['bh_sharpe']:.2f}, MDD {portfolio['bh_mdd']:.1f}%
  GeoRisk:       CAGR {portfolio['gr_cagr']:.1f}%, Sharpe {portfolio['gr_sharpe']:.2f}, MDD {portfolio['gr_mdd']:.1f}%
  MDD delta:     {portfolio['mdd_delta']:.1f}% (improvement)
  Sharpe delta:  {portfolio['sharpe_delta']:.2f}

V7 (Fixed) vs V8 (Risk Parity) Comparison
  Method         CAGR      MDD       Sharpe
  v7 Fixed       {port_v7['gr_cagr']:>4.1f}%     {port_v7['gr_mdd']:>5.1f}%     {port_v7['gr_sharpe']:.2f}
  v8 RP          {port_v8['gr_cagr']:>4.1f}%     {port_v8['gr_mdd']:>5.1f}%     {port_v8['gr_sharpe']:.2f}

Kelly Criterion (Portfolio basis)
  Hit Rate: {hit_rate*100:.1f}%, Avg Win: {avg_win*100:.4f}%, Avg Loss: {abs(avg_loss)*100:.4f}%
  kelly_f: {kelly_f:.3f} → recommended max position: {kelly_pct:.1f}%
"""
        print(report.strip())
        print()
        
        today = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(config.RESULTS_DIR, exist_ok=True)
        json_path = os.path.join(config.RESULTS_DIR, f"{today}_{period}_backtest.json")
        
        def sanitize(obj):
            if isinstance(obj, float) and math.isnan(obj): return None
            return obj
            
        out_data = {
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "quality": {k: sanitize(v) for k, v in quality.items()},
            "portfolio": {k: sanitize(v) for k, v in portfolio.items() if k not in ["bh_ret", "gr_ret"]},
            "kelly": sanitize(kelly_f),
            "regimes": {
                "calm": {"days": n_calm, "ret": sanitize(calm_ret)},
                "normal": {"days": n_norm, "ret": sanitize(norm_ret)},
                "elevated": {"days": n_elev, "ret": sanitize(elev_ret)},
                "crisis": {"days": n_cris, "ret": sanitize(cris_ret)}
            }
        }
        with open(json_path, "w") as f:
            json.dump(out_data, f, indent=2)

def run_breakdown(periods):
    for period in periods:
        data = fetch_all(period)
        if "SPY" not in data or "TLT" not in data: continue
        signals = compute_signals(data)
        spy_df, tlt_df = data["SPY"], data["TLT"]
        
        print(f"Breakdown Analysis for {period}\n")
        
        port_b = portfolio_comparison(signals, spy_df, tlt_df, config.PORTFOLIO_ALLOCATIONS)
        signals_c = signals.copy()
        mask_c = (signals_c['stress_score'] >= 2) & (signals_c['regime'].isin(["NORMAL", "ELEVATED", "CRISIS"]))
        signals_c.loc[mask_c, 'regime'] = "CRISIS"
        port_c = portfolio_comparison(signals_c, spy_df, tlt_df, config.PORTFOLIO_ALLOCATIONS)
        
        print("Portfolio Breakdown")
        print("═══════════════════════════════════════")
        print(f"            {'CAGR':<8}{'MDD':<9}{'Sharpe'}")
        print(f"{'Buy&Hold':<12}{port_b['bh_cagr']:>4.1f}%   {port_b['bh_mdd']:>5.1f}%   {port_b['bh_sharpe']:.2f}")
        print(f"{'Regime Only':<12}{port_b['gr_cagr']:>4.1f}%   {port_b['gr_mdd']:>5.1f}%   {port_b['gr_sharpe']:.2f}")
        print(f"{'Regime+Str':<12}{port_c['gr_cagr']:>4.1f}%   {port_c['gr_mdd']:>5.1f}%   {port_c['gr_sharpe']:.2f}")
        
        adds_value = "YES" if abs(port_c['gr_mdd']) <= abs(port_b['gr_mdd']) - 1.0 else "NO"
        print(f"\nStress signal adds value: {adds_value}\n")
        
        print("Threshold Breakdown")
        print("═══════════════════════════════════════")
        print(f"{'Score':<7}{'Signals':<9}{'HitRate3d':<11}{'AvgRet3d':<10}{'Edge'}")
        
        def get_thr_stats(mask):
            if mask.sum() == 0: return 0, 0.0, 0.0, 0.0
            temp_signals = signals.copy()
            temp_signals['action'] = "HOLD"
            temp_signals.loc[mask, 'action'] = "DEFENSIVE"
            sq = signal_quality(temp_signals, spy_df)
            return len(temp_signals[mask]), sq.get("hit_rate_3d",0)*100, sq.get("avg_return_3d",0), sq.get("edge",0)

        for thr in [1, 2, 3, "4+"]:
            mask = (signals['stress_score'] >= 4) if thr == "4+" else (signals['stress_score'] == thr)
            n_sig, hr3, avg3, edge = get_thr_stats(mask)
            print(f"{str(thr):<7}{n_sig:<9}{hr3:>4.1f}%      {avg3:>5.2f}%     {edge:>+5.2f}%")
        print()
        
        print("Regime Breakdown")
        print("═══════════════════════════════════════")
        print(f"{'Regime':<11}{'Days':<7}{'AvgRet3d':<10}{'AvgRet5d':<10}{'MDD'}")
        for state in ["CALM", "NORMAL", "ELEVATED", "CRISIS"]:
            mask = signals['regime'] == state
            n_days = mask.sum()
            if n_days > 0:
                temp_signals = signals.copy()
                temp_signals['action'] = "HOLD"
                temp_signals.loc[mask, 'action'] = "DEFENSIVE"
                sq = signal_quality(temp_signals, spy_df)
                avg3 = sq.get("avg_return_3d", 0)
                avg5 = sq.get("avg_return_5d", 0)
                mdd = sq.get("worst_case_5d", 0)
            else:
                avg3 = avg5 = mdd = 0
            print(f"{state:<11}{n_days:<7}{avg3:>+5.2f}%     {avg5:>+5.2f}%     {mdd:>5.1f}%")
        print()
        
        import pandas as pd
        print("Recency Check")
        print("═══════════════════════════════════════")
        print(f"            {'CAGR':<8}{'MDD':<9}{'Sharpe'}")
        
        recent_date = spy_df.index[-1] - pd.DateOffset(years=1)
        spy_rec = spy_df[spy_df.index >= recent_date]
        if len(spy_rec) > 0:
            rec_start_date_str = spy_rec.index[0].strftime("%Y-%m-%d")
            sig_rec = signals[signals['date'] >= rec_start_date_str]
            tlt_rec = tlt_df[tlt_df.index >= recent_date]
            port_r = portfolio_comparison(sig_rec, spy_rec, tlt_rec, config.PORTFOLIO_ALLOCATIONS)
            c3y = port_b['gr_cagr']
            m3y = port_b['gr_mdd']
            s3y = port_b['gr_sharpe']
            cr = port_r['gr_cagr']
            mr = port_r['gr_mdd']
            sr = port_r['gr_sharpe']
            
            per_str = f"Full {period}"
            print(f"{per_str:<12}{c3y:>4.1f}%   {m3y:>5.1f}%   {s3y:.2f}")
            print(f"{'Recent 1y':<12}{cr:>4.1f}%   {mr:>5.1f}%   {sr:.2f}")
            is_stable = "YES" if sr >= 0.8 * s3y else "NO"
            print(f"\nRecent performance stable: {is_stable}\n")
            
        today = datetime.now().strftime("%Y-%m-%d")
        jp = os.path.join(config.RESULTS_DIR, f"{today}_{period}_breakdown.json")
        with open(jp, "w") as f:
            json.dump({"period": period}, f)
            
        import alt_signals
        print("Alternative Signal Comparison")
        print("═══════════════════════════════════════════════════")
        print(f"{' '*18}{'CAGR':<7}{'MDD':<8}{'Sharpe':<8}{'HitRate':<9}{'Kelly':<7}{'FalseAlarm'}")
        
        print(f"{'Regime Only':<18}{port_b['gr_cagr']:>4.1f}%   {port_b['gr_mdd']:>5.1f}%   {port_b['gr_sharpe']:<8.2f}{'N/A':<9}{'N/A':<7}{'N/A'}")
        
        def get_kelly(port, sq):
            gr_r = port.get("gr_ret")
            bh_r = port.get("bh_ret")
            if gr_r is None or bh_r is None: return -1.0, 0.0, 0.0, 0.0
            
            active = gr_r != bh_r
            if active.sum() == 0: return -1.0, 0.0, 0.0, sq.get("false_alarm_rate", 0)
            
            edge_ret = gr_r[active] - bh_r[active]
            wins = edge_ret[edge_ret > 0]
            losses = edge_ret[edge_ret <= 0]
            
            w = wins.mean() if len(wins) > 0 else 0
            l = losses.mean() if len(losses) > 0 else 0
            hr = len(wins) / len(edge_ret)
            
            k = kelly_criterion(hr, w, abs(l))
            return k, hr, w, sq.get("false_alarm_rate",0)
            
        sq_curr = signal_quality(signals, spy_df)
        curr_k, curr_hr, curr_w, curr_fa = get_kelly(port_c, sq_curr)
        print(f"{'Current Stress':<18}{port_c['gr_cagr']:>4.1f}%   {port_c['gr_mdd']:>5.1f}%   {port_c['gr_sharpe']:<8.2f}{curr_hr*100:>4.1f}%    {curr_k:>5.2f}  {curr_fa*100:>4.1f}%")
        
        alts = {
            "Alt A: VIX MR": alt_signals.alt_a_vix_meanreversion(data),
            "Alt B: Cross-Ast": alt_signals.alt_b_cross_asset(data),
            "Alt C: Yield+VIX": alt_signals.alt_c_yield_vix(data)
        }
        
        best_name = "None"
        best_sharpe = -999.0
        
        for name, alt_sig in alts.items():
            sq_alt = signal_quality(alt_sig, spy_df)
            port_alt = portfolio_comparison(alt_sig, spy_df, tlt_df, config.PORTFOLIO_ALLOCATIONS)
            k, hr, w, fa = get_kelly(port_alt, sq_alt)
            cagr = port_alt['gr_cagr']
            mdd = port_alt['gr_mdd']
            sharpe = port_alt['gr_sharpe']
            
            if sharpe > best_sharpe and k > 0:
                best_sharpe = sharpe
                best_name = name
                
            print(f"{name:<18}{cagr:>4.1f}%   {mdd:>5.1f}%   {sharpe:<8.2f}{hr*100:>4.1f}%    {k:>5.2f}  {fa*100:>4.1f}%")
            
        print(f"\nBest signal: {best_name}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", nargs="+", default=["3y"])
    parser.add_argument("--breakdown", action="store_true")
    args = parser.parse_args()
    
    if args.breakdown:
        run_breakdown(args.period)
    else:
        run_backtest(args.period)

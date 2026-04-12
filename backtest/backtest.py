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
        
        quality = signal_quality(signals, spy_df)
        portfolio = portfolio_comparison(signals, spy_df, tlt_df, config.PORTFOLIO_ALLOCATIONS)
        
        returns_3d = []
        for s in quality["individual_signals"]:
            if "ret_3d" in s:
                returns_3d.append(s["ret_3d"])
        
        wins = [-r for r in returns_3d if r < 0]
        losses = [r for r in returns_3d if r >= 0]
        avg_win_3d = math.fsum(wins)/len(wins) if wins else 0
        avg_loss_3d = math.fsum(losses)/len(losses) if losses else 0
        
        kelly_f = kelly_criterion(quality.get("hit_rate_3d", 0), avg_win_3d, avg_loss_3d)
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

Kelly Criterion
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
            "portfolio": {k: sanitize(v) for k, v in portfolio.items()},
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", nargs="+", default=["3y"])
    args = parser.parse_args()
    
    run_backtest(args.period)

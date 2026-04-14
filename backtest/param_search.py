import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
import config
from data_fetcher import fetch_all
from alt_signals import alt_a_vix_meanreversion
from metrics import portfolio_comparison, signal_quality, kelly_criterion

def run_param_search():
    print("Fetching 5y data for grid search...")
    data_5y = fetch_all("5y")
    if "SPY" not in data_5y or "TLT" not in data_5y or "^VIX" not in data_5y:
        print("Missing required data (SPY, TLT, ^VIX).")
        return

    spy_5y = data_5y["SPY"]
    tlt_5y = data_5y["TLT"]
    last_date = spy_5y.index[-1]
    
    # Pre-slice data for efficiency
    data_periods = {
        "5y": data_5y,
        "3y": {k: v[v.index >= (last_date - pd.DateOffset(years=3))] for k, v in data_5y.items()},
        "2y": {k: v[v.index >= (last_date - pd.DateOffset(years=2))] for k, v in data_5y.items()}
    }

    VIX_SMA_PERIODS = [10, 15, 20, 30, 40, 50]
    VIX_ZSCORE_DEFENSIVES = [1.5, 2.0, 2.5, 3.0]
    
    results = []
    total_combos = len(VIX_SMA_PERIODS) * len(VIX_ZSCORE_DEFENSIVES)
    count = 0

    print(f"Starting grid search over {total_combos} combinations...")
    
    for sma in VIX_SMA_PERIODS:
        for zscore in VIX_ZSCORE_DEFENSIVES:
            count += 1
            print(f"Testing SMA={sma}, ZScore={zscore}... ({count}/{total_combos})")
            
            # Temporarily override config
            config.VIX_SMA_PERIOD = sma
            config.VIX_ZSCORE_DEFENSIVE = zscore
            
            period_metrics = {}
            for period_name, p_data in data_periods.items():
                signals = alt_a_vix_meanreversion(p_data)
                spy_df = p_data["SPY"]
                tlt_df = p_data["TLT"]
                
                # Signal quality for hit rate and false alarm
                sq = signal_quality(signals, spy_df)
                # Portfolio comparison for CAGR, MDD, Sharpe
                pc = portfolio_comparison(signals, spy_df, tlt_df, config.PORTFOLIO_ALLOCATIONS)
                
                # Calculate Kelly
                gr_r = pc["gr_ret"]
                bh_r = pc["bh_ret"]
                active = gr_r != bh_r
                if active.sum() > 0:
                    edge_ret = gr_r[active] - bh_r[active]
                    wins = edge_ret[edge_ret > 0]
                    losses = edge_ret[edge_ret <= 0]
                    w = wins.mean() if len(wins) > 0 else 0
                    l = losses.mean() if len(losses) > 0 else 0
                    hr = len(wins) / len(edge_ret)
                    k = kelly_criterion(hr, w, abs(l))
                else:
                    k = -1.0
                    hr = 0.0

                period_metrics[period_name] = {
                    "CAGR": pc["gr_cagr"],
                    "MDD": pc["gr_mdd"],
                    "Sharpe": pc["gr_sharpe"],
                    "HitRate": hr * 100,
                    "Kelly": k,
                    "FalseAlarm": sq.get("false_alarm_rate", 0) * 100
                }
            
            # Stability check
            m5y = period_metrics["5y"]
            m3y = period_metrics["3y"]
            m2y = period_metrics["2y"]
            
            sharpes = [m2y["Sharpe"], m3y["Sharpe"], m5y["Sharpe"]]
            sharpe_spread = max(sharpes) - min(sharpes)
            
            stable = (
                m5y["Sharpe"] > 1.0 and
                m5y["MDD"] > -15.0 and
                m5y["Kelly"] > 0 and
                sharpe_spread < 0.5
            )
            
            results.append({
                "sma": sma,
                "zscore": zscore,
                "metrics": period_metrics,
                "sharpe_spread": sharpe_spread,
                "stable": "YES" if stable else "NO"
            })

    # Output Format
    print("\nParameter Sensitivity (5y baseline)")
    print("═══════════════════════════════════════════════════════════════")
    print(f"{'SMA':<6}{'ZScore':<9}{'CAGR':<8}{'MDD':<9}{'Sharpe':<9}{'HitRate':<8}{'Kelly':<8}{'Stable'}")
    
    for r in results:
        m = r["metrics"]["5y"]
        print(f"{r['sma']:<6}{r['zscore']:<9}{m['CAGR']:>4.1f}%   {m['MDD']:>5.1f}%   {m['Sharpe']:<9.2f}{m['HitRate']:>4.1f}%   {m['Kelly']:>5.2f}   {r['stable']}")

    # Find Top 3 Stable
    stable_results = [r for r in results if r["stable"] == "YES"]
    top_3 = sorted(stable_results, key=lambda x: x["metrics"]["5y"]["Sharpe"], reverse=True)[:3]
    
    if not top_3:
        # If no stable found, find best compromise (highest 5y Sharpe)
        best_compromise = sorted(results, key=lambda x: x["metrics"]["5y"]["Sharpe"], reverse=True)[0]
        m5y = best_compromise["metrics"]["5y"]
        print("\nNo stable combination found.")
        print(f"Best compromise: SMA={best_compromise['sma']}, ZScore={best_compromise['zscore']}")
        print(f"  5y Sharpe: {m5y['Sharpe']:.2f}")
        
        reasons = []
        if m5y["Sharpe"] <= 1.0: reasons.append("5y Sharpe <= 1.0 target")
        if m5y["MDD"] <= -15.0: reasons.append(f"5y MDD {m5y['MDD']:.1f}% exceeds -15% limit")
        if m5y["Kelly"] <= 0: reasons.append("Negative or zero Kelly")
        if best_compromise["sharpe_spread"] >= 0.5: reasons.append(f"Sharpe spread {best_compromise['sharpe_spread']:.2f} exceeds 0.5 limit")
        
        print(f"  Issue: {', '.join(reasons)}")
        print("\nRecommendation: Strategy may need structural change,")
        print("not just parameter tuning.")
    else:
        print("\nTop 3 Stable Combinations (sorted by 5y Sharpe):")
        print("═══════════════════════════════════════════════════")
        print(f"{'Rank':<6}{'SMA':<5}{'ZScore':<8}{'5y-Sharpe':<11}{'5y-MDD':<9}{'5y-CAGR':<10}{'Spread'}")
        for i, r in enumerate(top_3):
            m = r["metrics"]["5y"]
            print(f"{i+1:<6}{r['sma']:<5}{r['zscore']:<8}{m['Sharpe']:<11.2f}{m['MDD']:>5.1f}%   {m['CAGR']:>5.1f}%    {r['sharpe_spread']:.2f}")
        
        winner = top_3[0]
        print(f"\nRecommended: SMA={winner['sma']}, ZScore={winner['zscore']}")
        
        # Cross-Period Consistency Table for Top 3
        for i, r in enumerate(top_3):
            print(f"\nBest Combo: SMA={r['sma']}, ZScore={r['zscore']}")
            print("═══════════════════════════════════════")
            print(f"{'Period':<9}{'CAGR':<8}{'MDD':<9}{'Sharpe':<9}{'Kelly'}")
            for p in ["2y", "3y", "5y"]:
                m = r["metrics"][p]
                print(f"{p:<9}{m['CAGR']:>4.1f}%   {m['MDD']:>5.1f}%   {m['Sharpe']:<9.2f}{m['Kelly']:.2f}")
            
            cagrs = [r["metrics"][p]["CAGR"] for p in ["2y", "3y", "5y"]]
            mdds = [r["metrics"][p]["MDD"] for p in ["2y", "3y", "5y"]]
            sharpes = [r["metrics"][p]["Sharpe"] for p in ["2y", "3y", "5y"]]
            print(f"Spread:  {max(cagrs)-min(cagrs):>4.1f}%   {max(mdds)-min(mdds):>5.1f}%   {max(sharpes)-min(sharpes):.2f}")

        # Update config.py if winner found
        update_config(winner['sma'], winner['zscore'])

    # Save results
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    json_path = os.path.join(config.RESULTS_DIR, f"{today}_param_search.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {json_path}")

def update_config(sma, zscore):
    print(f"\nUpdating config.py with SMA={sma}, ZScore={zscore}...")
    config_path = "config.py"
    with open(config_path, "r") as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if line.startswith("VIX_SMA_PERIOD ="):
            new_lines.append(f"VIX_SMA_PERIOD = {sma}\n")
        elif line.startswith("VIX_ZSCORE_DEFENSIVE ="):
            new_lines.append(f"VIX_ZSCORE_DEFENSIVE = {zscore}\n")
        else:
            new_lines.append(line)
            
    with open(config_path, "w") as f:
        f.writelines(new_lines)

if __name__ == "__main__":
    run_param_search()

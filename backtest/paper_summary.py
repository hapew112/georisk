import os
import json
from datetime import datetime

LOG_PATH = os.path.expanduser("~/georisk/paper_log.json")

def main():
    if not os.path.exists(LOG_PATH):
        print("No paper trading history found.")
        return

    with open(LOG_PATH, 'r') as f:
        history = json.load(f)

    if not history:
        print("Paper trading history is empty.")
        return

    start_date = history[0]['date']
    end_date = history[-1]['date']
    num_days = len(history)
    
    initial_value = 10000.0
    current_value = history[-1]['portfolio_value']
    bench_value = history[-1]['benchmark_value']
    
    portfolio_ret = (current_value / initial_value) - 1
    bench_ret = (bench_value / initial_value) - 1
    
    # Regime counts
    regime_counts = {}
    total_fees = 0.0
    rebalances = 0
    
    for entry in history:
        r = entry['regime']
        regime_counts[r] = regime_counts.get(r, 0) + 1
        total_fees += entry.get('fee_applied', 0.0)
        if entry.get('rebalanced', False):
            rebalances += 1

    print("  GeoRisk Paper Trading Summary")
    print("  ════════════════════════════════════")
    print(f"  Period:     {start_date} to {end_date} ({num_days} trading days)")
    print("")
    print(f"  Portfolio:  ${current_value:,.2f}  ({portfolio_ret:+.2f}%)")
    print(f"  Benchmark:  ${bench_value:,.2f}  ({bench_ret:+.2f}%)")
    print("")
    print("  Days by regime:")
    for r in ["CALM", "NORMAL", "ELEVATED", "CRISIS"]:
        if r in regime_counts:
            print(f"    {r:10}: {regime_counts[r]} days")
    
    print("")
    print(f"  Rebalances: {rebalances} times, total fees: ${total_fees:,.2f}")
    print("")
    
    # vs Backtest expectation
    # Expected monthly: ~+1.7% (from 3y CAGR 25.9% / 12)
    expected_monthly = 0.017
    # Adjust expected to the number of trading days (approx 21 per month)
    adjusted_expected = expected_monthly * (num_days / 21.0)
    
    status = "ON TRACK"
    if portfolio_ret > adjusted_expected * 1.1:
        status = "AHEAD"
    elif portfolio_ret < adjusted_expected * 0.9:
        status = "BEHIND"
        
    print("  vs Backtest expectation:")
    print(f"    Expected (adj): {adjusted_expected*100:+.2f}%")
    print(f"    Actual:         {portfolio_ret*100:+.2f}%")
    print(f"    Status:         {status}")
    print("  ════════════════════════════════════")

if __name__ == "__main__":
    main()

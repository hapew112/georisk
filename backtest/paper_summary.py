import os
import json
import argparse
import pandas as pd
from datetime import datetime, timedelta

# Import telegram notifier if available
try:
    import telegram_notify
except ImportError:
    telegram_notify = None

LOG_PATH = os.path.expanduser("~/georisk/paper_log.json")

def calculate_status(history):
    if not history:
        return "N/A", 0.0, 0.0
    
    num_days = len(history)
    # Assume initial value is 10000.0 as per existing script
    initial_value = 10000.0
    current_value = history[-1]['portfolio_value']
    portfolio_ret = (current_value / initial_value) - 1
    
    # vs Backtest expectation: ~+1.7% monthly
    expected_monthly = 0.017
    adjusted_expected = expected_monthly * (num_days / 21.0)
    
    status = "ON TRACK"
    if portfolio_ret > adjusted_expected * 1.1:
        status = "AHEAD"
    elif portfolio_ret < adjusted_expected * 0.9:
        status = "BEHIND"
    return status, adjusted_expected, portfolio_ret

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--telegram", action="store_true", help="Send weekly summary to Telegram")
    args = parser.parse_args()

    if not os.path.exists(LOG_PATH):
        print("No paper trading history found.")
        return

    with open(LOG_PATH, 'r') as f:
        history = json.load(f)

    if not history:
        print("Paper trading history is empty.")
        return

    # Sort history by date
    history.sort(key=lambda x: x['date'])
    
    # Calculate overall status based on full history
    status, total_adj_expected, total_actual_ret = calculate_status(history)

    # Filter for the last 7 calendar days of entries
    df = pd.DataFrame(history)
    df['date_dt'] = pd.to_datetime(df['date'])
    latest_date = df['date_dt'].max()
    window_start = latest_date - timedelta(days=6)
    weekly_df = df[df['date_dt'] >= window_start].copy()

    # Fallback to print mode if token is missing
    if args.telegram and not os.environ.get("TELEGRAM_BOT_TOKEN"):
        args.telegram = False

    if args.telegram:
        if len(weekly_df) < 3:
            print(f"Warning: Only {len(weekly_df)} entries in the last 7 days. Skipping Telegram summary.")
            # Fall back to print mode
            args.telegram = False
        elif telegram_notify:
            start_date = weekly_df['date'].iloc[0]
            end_date = weekly_df['date'].iloc[-1]
            
            last_entry = weekly_df.iloc[-1]
            first_entry = weekly_df.iloc[0]
            
            # Calculate weekly returns
            # For Portfolio: Value_before = (Value_after + Fee) / (1 + Ret/100)
            p_val_start = (first_entry['portfolio_value'] + first_entry.get('fee_applied', 0)) / (1 + first_entry['portfolio_return_pct']/100)
            p_val_end = last_entry['portfolio_value']
            weekly_p_ret = (p_val_end / p_val_start - 1) * 100
            
            # For Benchmark: Value_before = Value_after / (1 + Ret/100)
            b_val_start = first_entry['benchmark_value'] / (1 + first_entry['spy_return_pct']/100)
            b_val_end = last_entry['benchmark_value']
            weekly_b_ret = (b_val_end / b_val_start - 1) * 100
            
            alpha = weekly_p_ret - weekly_b_ret
            
            # Regime distribution
            regime_counts = weekly_df['regime'].value_counts().to_dict()
            regime_parts = []
            for r, emoji in [("CALM", "🟢"), ("NORMAL", "🟡"), ("ELEVATED", "🟠"), ("CRISIS", "🔴")]:
                count = regime_counts.get(r, 0)
                regime_parts.append(f"{emoji} {r}: {count}일")
            regime_line = "  " + "  ".join(regime_parts)
            
            rebalances = int(weekly_df['rebalanced'].sum())
            total_fees = weekly_df['fee_applied'].sum()
            
            msg = (
                f"📈 <b>GeoRisk 주간 리포트 | {start_date} ~ {end_date}</b>\n\n"
                f"포트폴리오: ${p_val_end:,.0f} ({weekly_p_ret:+.2f}%)\n"
                f"벤치마크:   ${b_val_end:,.0f} ({weekly_b_ret:+.2f}%)\n"
                f"초과수익:   {alpha:+.2f}%\n\n"
                f"이번 주 레짐 분포:\n{regime_line}\n\n"
                f"리밸런싱: {rebalances}회, 누적 수수료: ${total_fees:,.2f}\n"
                f"상태: {status}"
            )
            
            if telegram_notify.send(msg):
                return # Exit after sending if successful
            else:
                print("Failed to send Telegram message. Falling back to print mode.")
                args.telegram = False

    # Default print mode
    start_date = history[0]['date']
    end_date = history[-1]['date']
    num_days = len(history)
    
    current_value = history[-1]['portfolio_value']
    bench_value = history[-1]['benchmark_value']
    
    # Original script's summary view
    initial_value = 10000.0
    portfolio_ret = (current_value / initial_value) - 1
    bench_ret = (bench_value / initial_value) - 1
    
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
    
    print("  vs Backtest expectation:")
    print(f"    Expected (adj): {total_adj_expected*100:+.2f}%")
    print(f"    Actual:         {total_actual_ret*100:+.2f}%")
    print(f"    Status:         {status}")
    print("  ════════════════════════════════════")

if __name__ == "__main__":
    main()

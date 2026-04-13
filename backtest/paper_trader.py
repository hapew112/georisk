import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import sys

# Ensure we can import from the current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from data_fetcher import fetch_all
from signals import compute_signals

LOG_PATH = os.path.expanduser("~/georisk/paper_log.json")

def get_us_date():
    """
    9:00 AM KST is 8:00 PM EDT (previous day).
    We want to process the market day that just finished.
    If it's Monday 9:00 AM KST, it's Sunday 8:00 PM EDT (market closed).
    If it's Tuesday 9:00 AM KST, it's Monday 8:00 PM EDT (market closed, data available).
    """
    # Allow override for testing/backfilling
    force_date = os.environ.get("FORCE_DATE")
    if force_date:
        return pd.to_datetime(force_date).date()
        
    # Use a 7-hour offset from UTC to get a date that works for 9:00 AM KST run
    # 00:00 UTC - 7h = 17:00 (5 PM) of previous day.
    return (datetime.now(timezone.utc) - timedelta(hours=7)).date()

def main():
    today = get_us_date()
    
    # Fetch data
    try:
        # User requested 3y period
        data = fetch_all(period="3y")
    except Exception as e:
        print(f"Error fetching data: {e}")
        return

    signals = compute_signals(data)
    if signals.empty:
        print("No signals generated.")
        return

    # Ensure 'date' is date object for comparison
    signals['date'] = pd.to_datetime(signals['date']).dt.date
    
    # Check if today is in signals
    today_signals = signals[signals['date'] == today]
    if today_signals.empty:
        print("Market closed. Skipping.")
        return
    
    today_row = today_signals.iloc[-1]
    regime = today_row['regime']
    action = today_row['action']
    
    # Load history
    history = []
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, 'r') as f:
                history = json.load(f)
        except Exception:
            history = []
            
    if not history:
        # First run initialization
        yesterday_val = 10000.0
        yesterday_bench = 10000.0
        # Default allocation (CALM/NORMAL)
        yesterday_spy_w = 1.0
        yesterday_tlt_w = 0.0
        yesterday_cash_w = 0.0
        yesterday_regime = None
        is_first_run = True
    else:
        last_entry = history[-1]
        # Check if already processed
        if last_entry['date'] == str(today):
            print(f"Already processed {today}. Skipping.")
            return
            
        yesterday_val = last_entry['portfolio_value']
        yesterday_bench = last_entry['benchmark_value']
        yesterday_spy_w = last_entry['spy_weight']
        yesterday_tlt_w = last_entry['tlt_weight']
        yesterday_cash_w = last_entry['cash_weight']
        yesterday_regime = last_entry['regime']
        is_first_run = False

    # Calculate returns
    spy_today = today_row['spy_close']
    
    # Find previous market day in signals
    # today_signals.index[0] is the index of 'today' in the full 'signals' df
    today_idx = today_signals.index[-1]
    if today_idx == 0:
        # First day in 3y data, shouldn't happen
        spy_ret = 0.0
        tlt_ret = 0.0
    else:
        prev_row = signals.iloc[today_idx - 1]
        spy_prev = prev_row['spy_close']
        spy_ret = (spy_today / spy_prev) - 1
        
        # TLT return calculation
        tlt_ret = 0.0
        if "TLT" in data and not data["TLT"].empty:
            tlt_df = data["TLT"]
            tlt_df.index = pd.to_datetime(tlt_df.index).date
            prev_date = prev_row['date']
            if today in tlt_df.index and prev_date in tlt_df.index:
                tlt_today = tlt_df.loc[today, 'Close']
                tlt_prev = tlt_df.loc[prev_date, 'Close']
                if tlt_prev != 0:
                    tlt_ret = (tlt_today / tlt_prev) - 1
    
    # Portfolio return (using weights from yesterday)
    # On first run, we have no realized return because we just started
    if is_first_run:
        portfolio_return = 0.0
        spy_ret_realized = 0.0 # Just for the log of the first day
        new_value = 10000.0
        new_bench = 10000.0
    else:
        portfolio_return = (yesterday_spy_w * spy_ret) + (yesterday_tlt_w * tlt_ret)
        spy_ret_realized = spy_ret
        new_value = yesterday_val * (1 + portfolio_return)
        new_bench = yesterday_bench * (1 + spy_ret)
    
    # Rebalance logic & Fees
    rebalanced = False
    fee_applied = 0.0
    # Apply fee if regime changed OR if it's the first run (initial entry fee)
    # The prompt says: "Apply fee if regime changed from yesterday"
    if not is_first_run and yesterday_regime is not None and regime != yesterday_regime:
        rebalanced = True
        fee_rate = 0.0025 # 0.25%
        fee_applied = new_value * fee_rate
        new_value -= fee_applied
    elif is_first_run:
        # Initial rebalance to target weights
        rebalanced = True
        fee_rate = 0.0025
        fee_applied = new_value * fee_rate
        new_value -= fee_applied

    # Determine today's allocation for NEXT period
    alloc = config.PORTFOLIO_ALLOCATIONS.get(regime, config.PORTFOLIO_ALLOCATIONS["NORMAL"])
    spy_w = alloc.get('SPY', 0.0)
    tlt_w = alloc.get('TLT', 0.0)
    cash_w = alloc.get('cash', 0.0)
    
    # Save log entry
    entry = {
        "date": str(today),
        "regime": regime,
        "action": action,
        "spy_weight": float(spy_w),
        "tlt_weight": float(tlt_w),
        "cash_weight": float(cash_w),
        "spy_return_pct": float(spy_ret * 100),
        "tlt_return_pct": float(tlt_ret * 100),
        "portfolio_return_pct": float(portfolio_return * 100),
        "portfolio_value": round(float(new_value), 2),
        "benchmark_value": round(float(new_bench), 2),
        "rebalanced": rebalanced,
        "fee_applied": round(float(fee_applied), 2)
    }
    
    history.append(entry)
    with open(LOG_PATH, 'w') as f:
        json.dump(history, f, indent=2)
        
    # Print summary
    print(f"=== GeoRisk Paper Trade: {today} ===")
    print(f"Regime:     {regime}")
    print(f"Action:     {action}")
    print(f"Allocation: SPY {int(spy_w*100)}% / TLT {int(tlt_w*100)}% / Cash {int(cash_w*100)}%")
    print(f"SPY ret:    {spy_ret*100:+.2f}%")
    print(f"Portfolio:  ${new_value:,.2f} ({portfolio_return*100:+.2f}%)")
    print(f"Benchmark:  ${new_bench:,.2f} ({spy_ret*100:+.2f}%)")
    print(f"Rebalanced: {'YES' if rebalanced else 'NO'} (fee: ${fee_applied:,.2f})")
    print("======================================")

    try:
        from telegram_notify import send, daily_summary
        msg = daily_summary(entry, yesterday_regime if not is_first_run else None)
        ok = send(msg)
        if not ok:
            print("[Telegram] 전송 실패 (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 확인)")
    except Exception as e:
        print(f"[Telegram] 오류: {e}")

if __name__ == "__main__":
    main()

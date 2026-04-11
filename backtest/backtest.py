import argparse
import json
import os
from datetime import datetime
import pandas as pd
import numpy as np

from data_fetcher import fetch_all
from signals import compute_signals
from metrics import compute_metrics

def run_backtest(period, initial_capital):
    # Fetch data
    data = fetch_all(period=period)
    
    # Compute signals
    signals_df = compute_signals(data)
    
    spy = data.get('SPY')
    tlt = data.get('TLT')
    schd = data.get('SCHD')
    
    if spy is None:
        raise ValueError("SPY data is required")
        
    dates = spy.index
    signals_df.index = dates
    
    # Daily returns
    spy_ret = spy['Close'].pct_change().fillna(0)
    tlt_ret = tlt['Close'].pct_change().fillna(0) if tlt is not None else pd.Series(0, index=dates)
    schd_ret = schd['Close'].pct_change().fillna(0) if schd is not None else pd.Series(0, index=dates)
    
    # Portfolios
    bench_val = [initial_capital]
    strat_val = [initial_capital]
    
    bench_holdings = initial_capital
    
    # GeoRisk state
    curr_signal = 'HOLD'
    strat_cash = 0
    strat_spy = initial_capital
    strat_tlt = 0
    strat_schd = 0
    
    bench_equity = pd.Series(index=dates, dtype=float)
    strat_equity = pd.Series(index=dates, dtype=float)
    
    FEE_RATE = 0.0025
    USD_KRW = 1350
    TAX_THRESHOLD_KRW = 2500000
    TAX_RATE = 0.22
    
    # Tax tracking per year
    realized_gains_usd = 0
    cost_basis_spy = initial_capital
    cost_basis_tlt = 0
    cost_basis_schd = 0
    
    for i, date in enumerate(dates):
        # Apply market moves (after day 1)
        if i > 0:
            bench_holdings *= (1 + spy_ret.iloc[i])
            
            strat_spy *= (1 + spy_ret.iloc[i])
            strat_tlt *= (1 + tlt_ret.iloc[i])
            strat_schd *= (1 + schd_ret.iloc[i])
        
        bench_equity.iloc[i] = bench_holdings
        total_strat = strat_cash + strat_spy + strat_tlt + strat_schd
        
        # Determine signal action for today
        sig = signals_df['signal'].iloc[i]
        vix_regime = signals_df['vix_regime'].iloc[i]
        stress = signals_df['stress_score'].iloc[i]
        
        # CRISIS logic from prompt
        if vix_regime == 'CRISIS' or stress >= 3:
            target_sig = 'CRISIS'
        else:
            target_sig = sig
            
        if target_sig != curr_signal:
            # Rebalance
            if target_sig == 'HOLD':
                w_spy, w_tlt, w_schd, w_cash = 1.0, 0.0, 0.0, 0.0
            elif target_sig == 'DEFENSIVE':
                w_spy, w_tlt, w_schd, w_cash = 0.7, 0.2, 0.1, 0.0
            elif target_sig == 'CRISIS':
                w_spy, w_tlt, w_schd, w_cash = 0.45, 0.25, 0.25, 0.05
            else:
                w_spy, w_tlt, w_schd, w_cash = 1.0, 0.0, 0.0, 0.0
                
            new_spy = total_strat * w_spy
            new_tlt = total_strat * w_tlt
            new_schd = total_strat * w_schd
            new_cash = total_strat * w_cash
            
            # Calculate trades
            trade_spy = new_spy - strat_spy
            trade_tlt = new_tlt - strat_tlt
            trade_schd = new_schd - strat_schd
            
            # Fees
            fees = (abs(trade_spy) + abs(trade_tlt) + abs(trade_schd)) * FEE_RATE
            
            # Realized gains calculation (simplified average cost basis)
            if trade_spy < 0 and strat_spy > 0:
                fraction_sold = -trade_spy / strat_spy
                gain = -trade_spy - (cost_basis_spy * fraction_sold)
                realized_gains_usd += gain
                cost_basis_spy -= (cost_basis_spy * fraction_sold)
            elif trade_spy > 0:
                cost_basis_spy += trade_spy
                
            if trade_tlt < 0 and strat_tlt > 0:
                fraction_sold = -trade_tlt / strat_tlt
                gain = -trade_tlt - (cost_basis_tlt * fraction_sold)
                realized_gains_usd += gain
                cost_basis_tlt -= (cost_basis_tlt * fraction_sold)
            elif trade_tlt > 0:
                cost_basis_tlt += trade_tlt
                
            if trade_schd < 0 and strat_schd > 0:
                fraction_sold = -trade_schd / strat_schd
                gain = -trade_schd - (cost_basis_schd * fraction_sold)
                realized_gains_usd += gain
                cost_basis_schd -= (cost_basis_schd * fraction_sold)
            elif trade_schd > 0:
                cost_basis_schd += trade_schd
            
            total_strat -= fees
            if total_strat < 0:
                total_strat = 0
            
            # Apply after fees
            strat_spy = total_strat * w_spy
            strat_tlt = total_strat * w_tlt
            strat_schd = total_strat * w_schd
            strat_cash = total_strat * w_cash
            
            curr_signal = target_sig
        
        strat_equity.iloc[i] = strat_spy + strat_tlt + strat_schd + strat_cash
        
        # End of year tax
        if i == len(dates) - 1 or date.year != dates[i+1].year:
            gain_krw = realized_gains_usd * USD_KRW
            if gain_krw > TAX_THRESHOLD_KRW:
                tax_krw = (gain_krw - TAX_THRESHOLD_KRW) * TAX_RATE
                tax_usd = tax_krw / USD_KRW
                if strat_equity.iloc[i] > 0:
                    tax_ratio = tax_usd / strat_equity.iloc[i]
                    strat_spy *= (1 - tax_ratio)
                    strat_tlt *= (1 - tax_ratio)
                    strat_schd *= (1 - tax_ratio)
                    strat_cash *= (1 - tax_ratio)
                    strat_equity.iloc[i] -= tax_usd
                    # Reduce cost basis proportionally
                    cost_basis_spy *= (1 - tax_ratio)
                    cost_basis_tlt *= (1 - tax_ratio)
                    cost_basis_schd *= (1 - tax_ratio)
            realized_gains_usd = 0
            
    metrics = compute_metrics(bench_equity, strat_equity, signals_df, spy)
    
    print(json.dumps(metrics, indent=2))
    
    results_dir = os.path.expanduser("~/georisk/results")
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
        
    date_str = datetime.now().strftime("%Y%m%d")
    out_file = os.path.join(results_dir, f"georisk_v6_{date_str}.json")
    with open(out_file, "w") as f:
        json.dump(metrics, f, indent=2)
        
    print(f"Saved results to {out_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", type=str, default="5y")
    parser.add_argument("--initial", type=float, default=10000)
    args = parser.parse_args()
    
    run_backtest(args.period, args.initial)

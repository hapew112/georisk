import pandas as pd
import numpy as np

def compute_metrics(bench_equity: pd.Series, strat_equity: pd.Series, signals_df: pd.DataFrame, spy: pd.DataFrame) -> dict:
    if len(strat_equity) < 2:
        return {}
    
    # CAGR
    years = (strat_equity.index[-1] - strat_equity.index[0]).days / 365.25
    if years <= 0:
        years = 1
        
    bench_cagr = (bench_equity.iloc[-1] / bench_equity.iloc[0]) ** (1 / years) - 1
    strat_cagr = (strat_equity.iloc[-1] / strat_equity.iloc[0]) ** (1 / years) - 1
    
    # MDD
    def get_mdd(eq):
        roll_max = eq.cummax()
        drawdown = eq / roll_max - 1.0
        return abs(drawdown.min())
        
    bench_mdd = get_mdd(bench_equity)
    strat_mdd = get_mdd(strat_equity)
    
    # Volatility and Sharpe
    rf = 0.05
    def get_sharpe_vol(eq):
        rets = eq.pct_change().dropna()
        if len(rets) == 0:
            return 0, 0
        vol = rets.std() * np.sqrt(252)
        if vol == 0:
            return 0, 0
        mean_ret = rets.mean() * 252
        sharpe = (mean_ret - rf) / vol
        return sharpe, vol
        
    bench_sharpe, bench_vol = get_sharpe_vol(bench_equity)
    strat_sharpe, strat_vol = get_sharpe_vol(strat_equity)
    
    # Calmar
    strat_calmar = strat_cagr / strat_mdd if strat_mdd > 0 else 0
    bench_calmar = bench_cagr / bench_mdd if bench_mdd > 0 else 0
    
    # Hit rate: % of DEFENSIVE signals where SPY fell in next 3d AND 5d
    defensive_mask = signals_df['signal'] == 'DEFENSIVE'
    
    hits = 0
    total_def = 0
    spy_closes = spy['Close'].values
    
    for i, is_def in enumerate(defensive_mask):
        if is_def and i < len(spy_closes) - 5:
            total_def += 1
            spy_close = spy_closes[i]
            spy_3d = spy_closes[i+3]
            spy_5d = spy_closes[i+5]
            if spy_3d < spy_close and spy_5d < spy_close:
                hits += 1
                
    hit_rate = hits / total_def if total_def > 0 else 0
    
    # Monthly win rate
    strat_monthly = strat_equity.resample('ME').last().pct_change().dropna()
    bench_monthly = bench_equity.resample('ME').last().pct_change().dropna()
    
    if len(strat_monthly) > 0 and len(bench_monthly) > 0:
        monthly_win_rate = (strat_monthly > bench_monthly).mean()
    else:
        monthly_win_rate = 0.0
        
    # Kelly fraction (informational only)
    # W - ( (1-W) / R )
    W = monthly_win_rate
    if W == 0:
        kelly = 0
    else:
        # Pseudo win/loss ratio R based on monthly average
        strat_monthly_wins = strat_monthly[strat_monthly > 0].mean()
        strat_monthly_losses = abs(strat_monthly[strat_monthly < 0].mean())
        if pd.isna(strat_monthly_wins) or pd.isna(strat_monthly_losses) or strat_monthly_losses == 0:
            kelly = 0
        else:
            R = strat_monthly_wins / strat_monthly_losses
            kelly = W - ((1 - W) / R)
            
    return {
        "Benchmark": {
            "CAGR": bench_cagr,
            "MDD": bench_mdd,
            "Sharpe": bench_sharpe,
            "Calmar": bench_calmar,
            "AnnVol": bench_vol,
        },
        "Strategy": {
            "CAGR": strat_cagr,
            "MDD": strat_mdd,
            "Sharpe": strat_sharpe,
            "Calmar": strat_calmar,
            "AnnVol": strat_vol,
            "HitRate3d_5d": hit_rate,
            "MonthlyWinRate": monthly_win_rate,
            "KellyFraction": max(0, kelly)
        }
    }

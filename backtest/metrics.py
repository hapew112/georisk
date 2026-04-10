"""
metrics.py
포트폴리오 성과 메트릭 계산 (MDD, CAGR, Sharpe, Calmar, 변동성).
순수 함수, 사이드이펙트 없음.
"""

import math
import numpy as np
import pandas as pd


def compute_mdd(equity_curve: pd.Series) -> float:
    """
    Maximum Drawdown (최대 낙폭).
    고점 대비 최대 하락 비율을 반환 (음수, 예: -0.25 = -25%).
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return 0.0
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    return float(drawdown.min())


def compute_cagr(equity_curve: pd.Series) -> float:
    """
    Compound Annual Growth Rate (연평균 복리 수익률).
    거래일 252일 기준.
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return 0.0
    start = equity_curve.iloc[0]
    end = equity_curve.iloc[-1]
    if start <= 0:
        return 0.0
    n_days = len(equity_curve)
    n_years = n_days / 252.0
    if n_years <= 0:
        return 0.0
    return float((end / start) ** (1.0 / n_years) - 1.0)


def compute_annual_volatility(daily_returns: pd.Series) -> float:
    """
    연환산 변동성 (일수익률 표준편차 × sqrt(252)).
    """
    if daily_returns.empty or len(daily_returns) < 2:
        return 0.0
    return float(daily_returns.std() * np.sqrt(252))


def compute_sharpe(daily_returns: pd.Series, rf: float = 0.04) -> float:
    """
    Sharpe Ratio (연환산).
    rf: 연간 무위험이자율 (기본 4%).
    """
    vol = compute_annual_volatility(daily_returns)
    if vol == 0:
        return 0.0
    annual_ret = float(daily_returns.mean() * 252)
    return (annual_ret - rf) / vol


def compute_calmar(cagr: float, mdd: float) -> float:
    """
    Calmar Ratio = CAGR / |MDD|.
    """
    if mdd == 0:
        return 0.0
    return cagr / abs(mdd)


def compute_sortino(daily_returns: pd.Series, rf: float = 0.04) -> float:
    """
    Sortino Ratio — 하방 변동성만 사용.
    """
    if daily_returns.empty or len(daily_returns) < 2:
        return 0.0
    daily_rf = rf / 252.0
    downside = daily_returns[daily_returns < daily_rf] - daily_rf
    if downside.empty:
        return 0.0
    downside_std = float(downside.std() * np.sqrt(252))
    if downside_std == 0:
        return 0.0
    annual_ret = float(daily_returns.mean() * 252)
    return (annual_ret - rf) / downside_std


def compute_win_rate(daily_returns: pd.Series) -> float:
    """일별 수익률 중 양수인 날의 비율."""
    if daily_returns.empty:
        return 0.0
    return float((daily_returns > 0).sum() / len(daily_returns))


def equity_curve_from_returns(daily_returns: pd.Series, initial: float = 10000.0) -> pd.Series:
    """일별 수익률로부터 자산 곡선 생성."""
    return initial * (1 + daily_returns).cumprod()


def compute_portfolio_metrics(benchmark_equity: pd.Series,
                               strategy_equity: pd.Series) -> dict:
    """
    벤치마크(SPY B&H) vs 전략(GeoRisk) 성과를 한꺼번에 계산.

    Parameters
    ----------
    benchmark_equity : pd.Series  — SPY 100% Buy & Hold 자산 곡선
    strategy_equity  : pd.Series  — GeoRisk 전략 자산 곡선

    Returns
    -------
    dict with all metrics for both benchmark and strategy
    """
    b_ret = benchmark_equity.pct_change().dropna()
    s_ret = strategy_equity.pct_change().dropna()

    b_mdd  = compute_mdd(benchmark_equity)
    s_mdd  = compute_mdd(strategy_equity)

    b_cagr = compute_cagr(benchmark_equity)
    s_cagr = compute_cagr(strategy_equity)

    b_vol  = compute_annual_volatility(b_ret)
    s_vol  = compute_annual_volatility(s_ret)

    b_sharpe = compute_sharpe(b_ret)
    s_sharpe = compute_sharpe(s_ret)

    b_calmar = compute_calmar(b_cagr, b_mdd)
    s_calmar = compute_calmar(s_cagr, s_mdd)

    b_sortino = compute_sortino(b_ret)
    s_sortino = compute_sortino(s_ret)

    # MDD 개선률 (양수 = 전략이 더 나음)
    # b_mdd=-0.55, s_mdd=-0.28 → improvement = (0.55-0.28)/0.55 * 100 = 48%
    mdd_improvement = 0.0
    if b_mdd != 0:
        mdd_improvement = (abs(b_mdd) - abs(s_mdd)) / abs(b_mdd) * 100

    # 총 수익률
    b_total = (benchmark_equity.iloc[-1] / benchmark_equity.iloc[0] - 1) * 100
    s_total = (strategy_equity.iloc[-1] / strategy_equity.iloc[0] - 1) * 100

    def r(v, d=4):
        if isinstance(v, float) and math.isnan(v):
            return None
        return round(v, d)

    return {
        "benchmark": {
            "total_return_pct": r(b_total, 2),
            "cagr": r(b_cagr, 4),
            "mdd": r(b_mdd, 4),
            "annual_volatility": r(b_vol, 4),
            "sharpe": r(b_sharpe, 2),
            "calmar": r(b_calmar, 2),
            "sortino": r(b_sortino, 2),
            "win_rate": r(compute_win_rate(b_ret), 4),
        },
        "strategy": {
            "total_return_pct": r(s_total, 2),
            "cagr": r(s_cagr, 4),
            "mdd": r(s_mdd, 4),
            "annual_volatility": r(s_vol, 4),
            "sharpe": r(s_sharpe, 2),
            "calmar": r(s_calmar, 2),
            "sortino": r(s_sortino, 2),
            "win_rate": r(compute_win_rate(s_ret), 4),
        },
        "comparison": {
            "mdd_improvement_pct": r(mdd_improvement, 1),
            "cagr_diff_pct": r((s_cagr - b_cagr) * 100, 2),
            "sharpe_diff": r(s_sharpe - b_sharpe, 2),
            "volatility_reduction_pct": r((b_vol - s_vol) / b_vol * 100 if b_vol > 0 else 0, 1),
        },
    }

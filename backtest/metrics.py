"""
metrics.py
백테스트 메트릭 계산 (순수 함수, 사이드이펙트 없음).
"""

import math
import numpy as np
import pandas as pd


def compute_forward_returns(spy: pd.Series, signal_dates: list) -> pd.DataFrame:
    """
    각 signal date에 대해 SPY의 선물 수익률을 계산한다.
    달력 날짜가 아닌 iloc 위치 기반으로 계산해서 시장 휴일을 올바르게 처리함.

    반환 컬럼: date, score, ret_1d, ret_3d, ret_5d, ret_10d, drawdown_5d
    """
    spy_vals = spy.values
    spy_idx = spy.index
    n = len(spy_vals)

    # signal_dates를 spy 인덱스 위치로 변환
    idx_map = {d: i for i, d in enumerate(spy_idx)}

    rows = []
    for entry in signal_dates:
        date = entry["date"]
        score = entry["score"]

        pos = idx_map.get(date)
        if pos is None:
            continue

        base = spy_vals[pos]
        if base == 0 or math.isnan(base):
            continue

        def ret_at(offset):
            target = pos + offset
            if target >= n:
                return float("nan")
            v = spy_vals[target]
            if math.isnan(v):
                return float("nan")
            return (v - base) / base * 100

        # 최대 낙폭 (t ~ t+5 구간)
        end5 = min(pos + 6, n)
        window = spy_vals[pos:end5]
        valid = window[~np.isnan(window)]
        if len(valid) > 1:
            dd = (min(valid) - base) / base * 100
        else:
            dd = float("nan")

        rows.append({
            "date":        date,
            "score":       score,
            "ret_1d":      ret_at(1),
            "ret_3d":      ret_at(3),
            "ret_5d":      ret_at(5),
            "ret_10d":     ret_at(10),
            "drawdown_5d": dd,
        })

    return pd.DataFrame(rows)


def compute_baseline(spy: pd.Series) -> dict:
    """
    모든 거래일에 대한 평균 선물 수익률 (baseline).
    """
    vals = spy.values
    n = len(vals)
    rets_3d, rets_5d, rets_10d = [], [], []

    for i in range(n):
        base = vals[i]
        if base == 0 or math.isnan(base):
            continue

        def r(offset):
            t = i + offset
            if t >= n:
                return float("nan")
            v = vals[t]
            if math.isnan(v):
                return float("nan")
            return (v - base) / base * 100

        r3 = r(3)
        r5 = r(5)
        r10 = r(10)
        if not math.isnan(r3):
            rets_3d.append(r3)
        if not math.isnan(r5):
            rets_5d.append(r5)
        if not math.isnan(r10):
            rets_10d.append(r10)

    def safe_mean(lst):
        return round(float(np.mean(lst)), 4) if lst else float("nan")

    return {
        "baseline_avg_3d":  safe_mean(rets_3d),
        "baseline_avg_5d":  safe_mean(rets_5d),
        "baseline_avg_10d": safe_mean(rets_10d),
    }


def compute_metrics(forward_df: pd.DataFrame, spy: pd.Series, threshold: int) -> dict:
    """
    모든 백테스트 메트릭을 계산해 dict로 반환.
    """
    if forward_df.empty:
        return {"total_signals": 0, "error": "No signals found"}

    total = len(forward_df)

    def mean_col(col):
        vals = forward_df[col].dropna()
        return round(float(vals.mean()), 4) if len(vals) > 0 else float("nan")

    def hit_rate(col):
        vals = forward_df[col].dropna()
        if len(vals) == 0:
            return float("nan")
        return round(float((vals < 0).sum() / len(vals)), 4)

    avg_ret_3d  = mean_col("ret_3d")
    avg_ret_5d  = mean_col("ret_5d")
    avg_ret_10d = mean_col("ret_10d")
    hr_3d       = hit_rate("ret_3d")
    hr_5d       = hit_rate("ret_5d")

    ret5_vals = forward_df["ret_5d"].dropna()
    false_alarm_rate = round(float((ret5_vals >= 0).sum() / len(ret5_vals)), 4) if len(ret5_vals) > 0 else float("nan")
    avg_dd      = mean_col("drawdown_5d")
    worst_case  = round(float(forward_df["ret_5d"].dropna().min()), 4) if len(ret5_vals) > 0 else float("nan")

    baseline    = compute_baseline(spy)

    def diff(signal_val, baseline_val):
        if math.isnan(signal_val) or math.isnan(baseline_val):
            return float("nan")
        return round(signal_val - baseline_val, 4)

    return {
        "total_signals":          int(total),
        "avg_return_3d":          avg_ret_3d,
        "avg_return_5d":          avg_ret_5d,
        "avg_return_10d":         avg_ret_10d,
        "hit_rate_3d":            hr_3d,
        "hit_rate_5d":            hr_5d,
        "false_alarm_rate":       false_alarm_rate,
        "avg_drawdown_5d":        avg_dd,
        "worst_case":             worst_case,
        "baseline_avg_3d":        baseline["baseline_avg_3d"],
        "baseline_avg_5d":        baseline["baseline_avg_5d"],
        "baseline_avg_10d":       baseline["baseline_avg_10d"],
        "signal_vs_baseline_3d":  diff(avg_ret_3d,  baseline["baseline_avg_3d"]),
        "signal_vs_baseline_5d":  diff(avg_ret_5d,  baseline["baseline_avg_5d"]),
        "signal_vs_baseline_10d": diff(avg_ret_10d, baseline["baseline_avg_10d"]),
    }


def verdict(metrics: dict) -> str:
    hr3 = metrics.get("hit_rate_3d", 0)
    hr5 = metrics.get("hit_rate_5d", 0)
    vs5 = metrics.get("signal_vs_baseline_5d", 0)

    if math.isnan(hr3) or math.isnan(hr5) or math.isnan(vs5):
        return "Insufficient data for verdict."
    if (hr3 >= 0.60 or hr5 >= 0.60) and vs5 <= -0.5:
        return "Signal has predictive value."
    return "Signal needs further validation."

"""
investor_profile.py
투자자 성향 프로파일링 모듈.

수익 곡선(equity curve)과 트레이드 이력으로부터
투자자의 성향을 분석하고 분류한다.

사용법:
    from investor_profile import analyze_profile

    # 방법 1: equity curve만으로 분석
    profile = analyze_profile(equity_curve=my_equity_series)

    # 방법 2: 트레이드 이력으로 분석
    trades = [
        {"date": "2025-01-15", "action": "buy",  "ticker": "AAPL", "amount": 5000},
        {"date": "2025-02-20", "action": "sell", "ticker": "AAPL", "amount": 5500},
    ]
    profile = analyze_profile(trades=trades)
"""

import math
from typing import Optional

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════
# 투자자 유형 정의
# ═══════════════════════════════════════════════════════════════

INVESTOR_TYPES = {
    "CONSERVATIVE": {
        "name_kr": "안정 추구형",
        "description": "손실 회피 성향이 강하고, 변동성이 낮은 안정적인 수익을 선호합니다.",
        "characteristics": [
            "낮은 일변동성",
            "낮은 MDD",
            "위기 시 빠른 손절",
            "현금 비율 높음",
        ],
        "recommended_regime_weights": {
            "CALM":     {"SPY": 0.70, "TLT": 0.25, "cash": 0.05},
            "NORMAL":   {"SPY": 0.50, "TLT": 0.35, "cash": 0.15},
            "ELEVATED": {"SPY": 0.30, "TLT": 0.40, "cash": 0.30},
            "CRISIS":   {"SPY": 0.10, "TLT": 0.40, "cash": 0.50},
        },
    },
    "BALANCED": {
        "name_kr": "균형 투자형",
        "description": "리스크와 수익의 균형을 추구하며, 적절한 분산투자를 합니다.",
        "characteristics": [
            "중간 수준의 변동성",
            "적정 MDD 허용 (15~25%)",
            "트렌드 추종 경향",
            "주기적 리밸런싱",
        ],
        "recommended_regime_weights": {
            "CALM":     {"SPY": 1.00, "TLT": 0.00, "cash": 0.00},
            "NORMAL":   {"SPY": 0.80, "TLT": 0.15, "cash": 0.05},
            "ELEVATED": {"SPY": 0.50, "TLT": 0.35, "cash": 0.15},
            "CRISIS":   {"SPY": 0.25, "TLT": 0.45, "cash": 0.30},
        },
    },
    "AGGRESSIVE": {
        "name_kr": "공격 투자형",
        "description": "높은 수익을 위해 높은 리스크를 감수하며, 변동성을 기회로 봅니다.",
        "characteristics": [
            "높은 변동성 감내",
            "높은 MDD 허용 (25%+)",
            "하락장에서도 매수 (역방향 투자)",
            "레버리지 가능성",
        ],
        "recommended_regime_weights": {
            "CALM":     {"SPY": 1.00, "TLT": 0.00, "cash": 0.00},
            "NORMAL":   {"SPY": 1.00, "TLT": 0.00, "cash": 0.00},
            "ELEVATED": {"SPY": 0.80, "TLT": 0.15, "cash": 0.05},
            "CRISIS":   {"SPY": 0.60, "TLT": 0.25, "cash": 0.15},
        },
    },
    "MOMENTUM": {
        "name_kr": "모멘텀 추종형",
        "description": "추세를 따라가며, 상승 모멘텀에서 집중 투자하고 하락 시 빠르게 빠집니다.",
        "characteristics": [
            "승률이 낮지만 큰 수익",
            "빈번한 매매",
            "손절 빠름",
            "상승장에서 수익 극대화",
        ],
        "recommended_regime_weights": {
            "CALM":     {"SPY": 1.00, "TLT": 0.00, "cash": 0.00},
            "NORMAL":   {"SPY": 0.90, "TLT": 0.10, "cash": 0.00},
            "ELEVATED": {"SPY": 0.40, "TLT": 0.20, "cash": 0.40},
            "CRISIS":   {"SPY": 0.10, "TLT": 0.30, "cash": 0.60},
        },
    },
}


# ═══════════════════════════════════════════════════════════════
# 분석 함수들
# ═══════════════════════════════════════════════════════════════

def _analyze_equity_curve(equity: pd.Series) -> dict:
    """자산 곡선에서 투자자 행동 특성을 추출."""
    daily_ret = equity.pct_change().dropna()

    if len(daily_ret) < 20:
        return {"error": "데이터 부족 (최소 20일 필요)"}

    # 기본 통계
    vol = float(daily_ret.std() * np.sqrt(252))
    annual_ret = float(daily_ret.mean() * 252)

    # MDD
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    mdd = float(drawdown.min())

    # 가장 큰 낙폭 후 회복까지 걸린 시간
    dd_end_idx = drawdown.idxmin()
    dd_end_pos = equity.index.get_loc(dd_end_idx)
    peak_before = running_max.loc[dd_end_idx]
    recovery_days = None
    for i in range(dd_end_pos + 1, len(equity)):
        if equity.iloc[i] >= peak_before:
            recovery_days = i - dd_end_pos
            break

    # 손실 지속 기간 분석
    losing_streaks = []
    current_streak = 0
    for r in daily_ret:
        if r < 0:
            current_streak += 1
        else:
            if current_streak > 0:
                losing_streaks.append(current_streak)
            current_streak = 0
    avg_losing_streak = np.mean(losing_streaks) if losing_streaks else 0
    max_losing_streak = max(losing_streaks) if losing_streaks else 0

    # 수익 vs 손실 비대칭
    gains = daily_ret[daily_ret > 0]
    losses = daily_ret[daily_ret < 0]
    avg_gain = float(gains.mean()) if len(gains) > 0 else 0
    avg_loss = float(losses.mean()) if len(losses) > 0 else 0
    gain_loss_ratio = abs(avg_gain / avg_loss) if avg_loss != 0 else 0
    win_rate = len(gains) / len(daily_ret)

    # 꼬리 위험 (5th percentile)
    var_95 = float(daily_ret.quantile(0.05))
    cvar_95 = float(daily_ret[daily_ret <= var_95].mean()) if len(daily_ret[daily_ret <= var_95]) > 0 else var_95

    return {
        "annual_return": round(annual_ret, 4),
        "annual_volatility": round(vol, 4),
        "mdd": round(mdd, 4),
        "mdd_recovery_days": recovery_days,
        "win_rate": round(win_rate, 4),
        "avg_gain": round(avg_gain * 100, 4),
        "avg_loss": round(avg_loss * 100, 4),
        "gain_loss_ratio": round(gain_loss_ratio, 2),
        "avg_losing_streak": round(avg_losing_streak, 1),
        "max_losing_streak": max_losing_streak,
        "var_95": round(var_95 * 100, 2),
        "cvar_95": round(cvar_95 * 100, 2),
        "total_days": len(daily_ret),
    }


def _classify_investor(stats: dict) -> str:
    """통계 기반 투자자 유형 분류."""
    if "error" in stats:
        return "BALANCED"  # 기본값

    vol = stats["annual_volatility"]
    mdd = abs(stats["mdd"])
    win_rate = stats["win_rate"]
    gl_ratio = stats["gain_loss_ratio"]

    score = 0  # 높을수록 공격적

    # 변동성 기반
    if vol < 0.10:
        score -= 2
    elif vol < 0.18:
        score += 0
    elif vol < 0.25:
        score += 2
    else:
        score += 3

    # MDD 허용도
    if mdd < 0.10:
        score -= 2
    elif mdd < 0.20:
        score += 0
    elif mdd < 0.30:
        score += 2
    else:
        score += 3

    # 승률 vs 수익비
    if win_rate > 0.55 and gl_ratio < 1.2:
        score -= 1  # 높은 승률, 작은 수익 = 안정형
    elif win_rate < 0.45 and gl_ratio > 1.5:
        score += 2  # 낮은 승률, 큰 수익 = 모멘텀형

    # 분류
    if score <= -2:
        return "CONSERVATIVE"
    elif score <= 1:
        return "BALANCED"
    elif win_rate < 0.48 and gl_ratio > 1.3:
        return "MOMENTUM"
    else:
        return "AGGRESSIVE"


def _generate_recommendations(investor_type: str, stats: dict) -> list:
    """투자자 유형에 맞는 맞춤 조언 생성."""
    recs = []
    info = INVESTOR_TYPES[investor_type]

    if investor_type == "CONSERVATIVE":
        if stats.get("mdd", 0) < -0.05:
            recs.append("현재 MDD가 감내 수준 내에 있습니다. 좋은 리스크 관리입니다.")
        recs.append("ELEVATED/CRISIS 레짐에서 채권(TLT) + 현금 비중을 높이세요.")
        recs.append("변동성이 큰 개별 종목보다 인덱스 ETF 위주로 투자하세요.")

    elif investor_type == "BALANCED":
        recs.append("현재 균형 잡힌 투자 스타일입니다.")
        recs.append("레짐 변화에 따라 자동으로 배분이 조정되는 것을 활용하세요.")
        if stats.get("annual_volatility", 0) > 0.20:
            recs.append("변동성이 다소 높습니다. ELEVATED 레짐에서 주식 비중을 줄여보세요.")

    elif investor_type == "AGGRESSIVE":
        recs.append("높은 리스크 감내력이 있지만, CRISIS 레짐에서는 방어적으로 전환하세요.")
        if abs(stats.get("mdd", 0)) > 0.25:
            recs.append(f"MDD가 {stats['mdd']*100:.1f}%입니다. "
                        "레버리지보다 분산투자로 수익을 추구하세요.")
        recs.append("하락장 매수(적립식 투자)가 장기적으로 유리합니다.")

    elif investor_type == "MOMENTUM":
        recs.append("모멘텀 추종 전략에 레짐 필터를 결합하면 효과적입니다.")
        recs.append("CALM/NORMAL 레짐에서만 모멘텀 매매를 진행하세요.")
        recs.append("ELEVATED 이상에서는 현금 비율을 크게 높이세요.")

    return recs


# ═══════════════════════════════════════════════════════════════
# 공개 API
# ═══════════════════════════════════════════════════════════════

def analyze_profile(equity_curve: Optional[pd.Series] = None,
                    trades: Optional[list] = None) -> dict:
    """
    투자자 프로파일 분석.

    Parameters
    ----------
    equity_curve : pd.Series (optional)
        일별 자산 가치 시계열.
    trades : list of dict (optional)
        트레이드 이력. 각 항목: {"date", "action", "ticker", "amount"}

    Returns
    -------
    dict with: investor_type, type_info, statistics, recommendations,
               recommended_weights
    """
    if equity_curve is not None and not equity_curve.empty:
        stats = _analyze_equity_curve(equity_curve)
    elif trades:
        # 트레이드 이력 → 간이 equity curve 생성
        df = pd.DataFrame(trades)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        # 매수/매도 기반 포지션 가치 추적 (단순화)
        cumulative = 0
        values = []
        for _, row in df.iterrows():
            if row["action"] == "buy":
                cumulative += row["amount"]
            elif row["action"] == "sell":
                cumulative += row["amount"]  # sell amount는 회수금
            values.append({"date": row["date"], "value": max(cumulative, 0)})

        if values:
            eq = pd.Series(
                [v["value"] for v in values],
                index=pd.DatetimeIndex([v["date"] for v in values])
            )
            stats = _analyze_equity_curve(eq)
        else:
            stats = {"error": "트레이드 이력 부족"}
    else:
        stats = {"error": "equity_curve 또는 trades 데이터 필요"}

    investor_type = _classify_investor(stats)
    type_info = INVESTOR_TYPES[investor_type]
    recommendations = _generate_recommendations(investor_type, stats)

    return {
        "investor_type": investor_type,
        "investor_type_kr": type_info["name_kr"],
        "description": type_info["description"],
        "characteristics": type_info["characteristics"],
        "statistics": stats,
        "recommendations": recommendations,
        "recommended_regime_weights": type_info["recommended_regime_weights"],
    }


def print_profile(profile: dict):
    """프로파일 결과를 보기 좋게 출력."""
    print(f"\n{'='*60}")
    print(f"  📊 투자자 프로파일 분석 결과")
    print(f"{'='*60}")
    print(f"\n  유형: {profile['investor_type']} ({profile['investor_type_kr']})")
    print(f"  설명: {profile['description']}")

    stats = profile.get("statistics", {})
    if "error" not in stats:
        print(f"\n  ── 투자 통계 ──")
        print(f"  연수익률       : {stats['annual_return']*100:.1f}%")
        print(f"  연변동성       : {stats['annual_volatility']*100:.1f}%")
        print(f"  MDD           : {stats['mdd']*100:.1f}%")
        if stats.get('mdd_recovery_days'):
            print(f"  MDD 회복      : {stats['mdd_recovery_days']}거래일")
        print(f"  승률           : {stats['win_rate']*100:.1f}%")
        print(f"  수익/손실 비율 : {stats['gain_loss_ratio']:.2f}")
        print(f"  VaR (95%)     : {stats['var_95']:.2f}%")
        print(f"  분석 기간      : {stats['total_days']}거래일")

    print(f"\n  ── 특성 ──")
    for c in profile.get("characteristics", []):
        print(f"  • {c}")

    print(f"\n  ── 맞춤 조언 ──")
    for r in profile.get("recommendations", []):
        print(f"  💡 {r}")

    print(f"\n  ── 레짐별 추천 배분 ──")
    for regime, weights in profile.get("recommended_regime_weights", {}).items():
        parts = [f"{k}:{v*100:.0f}%" for k, v in weights.items() if v > 0]
        print(f"  {regime:<12} → {', '.join(parts)}")

    print(f"\n{'='*60}\n")

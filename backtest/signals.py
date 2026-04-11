"""
signals.py
멀티팩터 시장 레짐 분류 엔진.

단일 VIX가 아닌 5가지 매크로+기술적 팩터를 종합하여
시장 레짐(CALM / NORMAL / ELEVATED / CRISIS)을 결정하고
레짐별 포트폴리오 배분 비율을 반환한다.

팩터 목록:
  1. VIX 수준          — 변동성 공포 지표
  2. 수익률 곡선 역전    — 10Y-3M 스프레드 (경기침체 선행지표)
  3. 달러 강세 모멘텀    — DXY 20일 변화율 (위험회피 신호)
  4. SPY 200일 이평선   — 기술적 추세 판단 (차트 분석)
  5. 원유 급등/급락      — 에너지 쇼크 (지정학 리스크 프록시)
"""

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════
# 레짐 정의 및 포트폴리오 배분
# ═══════════════════════════════════════════════════════════════

REGIME_NAMES = ["CALM", "NORMAL", "ELEVATED", "CRISIS"]

# 레짐별 기본 포트폴리오 배분 (SPY, TLT, Cash)
DEFAULT_WEIGHTS = {
    "CALM":     {"SPY": 0.95, "SGOV": 0.00, "cash": 0.05},
    "NORMAL":   {"SPY": 0.85, "SGOV": 0.10, "cash": 0.05},
    "ELEVATED": {"SPY": 0.60, "SGOV": 0.30, "cash": 0.10},
    "CRISIS":   {"SPY": 0.30, "SGOV": 0.50, "cash": 0.20},
}


# ═══════════════════════════════════════════════════════════════
# 팩터별 스코어링 (각 0~3점)
# ═══════════════════════════════════════════════════════════════

def _score_vix(vix_val: float) -> int:
    """VIX 수준 기반 스트레스 점수 (0~3)."""
    if np.isnan(vix_val):
        return 0
    if vix_val < 15:
        return 0      # CALM
    elif vix_val < 20:
        return 1      # 약간 긴장
    elif vix_val < 28:
        return 2      # 경계
    else:
        return 3      # 위기





def _score_dollar(dxy_pct_20d: float) -> int:
    """
    달러 인덱스 20일 변화율 기반 점수.
    달러 급등 = 위험회피 (risk-off) 신호.
    """
    if np.isnan(dxy_pct_20d):
        return 0
    if dxy_pct_20d < 1.0:
        return 0
    elif dxy_pct_20d < 3.0:
        return 1
    elif dxy_pct_20d < 5.0:
        return 2
    else:
        return 3


def _score_sma200(spy_close: float, sma200: float) -> int:
    """
    SPY가 200일 이평선 대비 어디에 있는지 (기술적 분석).
    200SMA 아래 = 약세장 진입 신호.
    """
    if np.isnan(spy_close) or np.isnan(sma200) or sma200 == 0:
        return 0
    pct_from_sma = (spy_close - sma200) / sma200 * 100
    if pct_from_sma > 5:
        return 0      # 이평선 위 + 충분한 여유
    elif pct_from_sma > 0:
        return 1      # 이평선 위이나 근접
    elif pct_from_sma > -5:
        return 2      # 이평선 아래 (약세 전환 신호)
    else:
        return 3      # 이평선 크게 하회 (약세장 확정)


def _score_oil(oil_pct_5d: float) -> int:
    """
    유가 5일 급변동 (지정학 리스크 프록시).
    급등이든 급락이든 극단적 변동 = 불확실성 증가.
    """
    if np.isnan(oil_pct_5d):
        return 0
    abs_chg = abs(oil_pct_5d)
    if abs_chg < 5:
        return 0
    elif abs_chg < 10:
        return 1
    elif abs_chg < 15:
        return 2
    else:
        return 3


# ═══════════════════════════════════════════════════════════════
# 종합 레짐 분류
# ═══════════════════════════════════════════════════════════════

def classify_regime(composite_score: float) -> str:
    """
    종합 점수(0~15) → 레짐 명칭.
    5개 팩터 × 최대 3점 = 최대 15점.
    임계값을 낮게 잡아 위험에 빨리 반응하도록 설정.
    """
    if composite_score <= 1:
        return "CALM"
    elif composite_score <= 4:
        return "NORMAL"
    elif composite_score <= 7:
        return "ELEVATED"
    else:
        return "CRISIS"


def get_portfolio_weights(regime: str, custom_weights: dict = None) -> dict:
    """
    레짐에 따른 포트폴리오 배분 반환.
    custom_weights가 주어지면 해당 설정 사용, 아니면 기본값.
    """
    weights_table = custom_weights if custom_weights else DEFAULT_WEIGHTS
    return weights_table.get(regime, DEFAULT_WEIGHTS["NORMAL"])


# ═══════════════════════════════════════════════════════════════
# 메인: 일별 레짐 계산
# ═══════════════════════════════════════════════════════════════

def compute_regimes(data: dict) -> pd.DataFrame:
    """
    매일의 멀티팩터 스코어를 계산하고 레짐을 분류한다.

    Parameters
    ----------
    data : dict
        {symbol: DataFrame} — fetch_all()의 반환값

    Returns
    -------
    DataFrame with columns:
        vix_score, yield_curve_score, dollar_score, sma200_score, oil_score,
        composite_score, regime, spy_weight, tlt_weight, cash_weight
    """
    spy_df = data.get("SPY")
    if spy_df is None:
        raise ValueError("SPY data is required")

    idx = spy_df.index

    def close_series(symbol: str) -> pd.Series:
        df = data.get(symbol)
        if df is None or df.empty:
            return pd.Series(np.nan, index=idx)
        s = df["Close"].reindex(idx).ffill()
        return s

    spy   = close_series("SPY")
    vix   = close_series("^VIX")
    tnx   = close_series("^TNX")
    irx   = close_series("^IRX")
    dxy   = close_series("DX-Y.NYB")
    oil   = close_series("CL=F")

    # 파생 지표 계산
    spy_sma200 = spy.rolling(200, min_periods=200).mean()
    dxy_pct_20d = dxy.pct_change(20) * 100       # 20일 변화율(%)
    oil_pct_5d  = oil.pct_change(5) * 100         # 5일 변화율(%)

    # 수익률 곡선 연속 역전일 계산 (지속성 필터)
    curve_spread = tnx - irx
    is_inverted = curve_spread < 0
    inv_group = (~is_inverted).cumsum()
    consec_inv = is_inverted.groupby(inv_group).cumsum().where(is_inverted, 0)

    # 일별 스코어링
    records = []
    for dt in idx:
        vs  = _score_vix(vix.get(dt, np.nan))
        
        spread = curve_spread.get(dt, float('nan'))
        days_inv = int(consec_inv.get(dt, 0))
        if spread != spread or spread > 1.0:   # nan or steep normal
            ycs = 0
        elif spread > 0.0:                     # flattening
            ycs = 1
        elif days_inv < 60:                    # new inversion
            ycs = 1
        else:                                  # sustained 60d+
            ycs = 2

        ds  = _score_dollar(dxy_pct_20d.get(dt, np.nan))
        ss  = _score_sma200(spy.get(dt, np.nan), spy_sma200.get(dt, np.nan))
        os_ = _score_oil(oil_pct_5d.get(dt, np.nan))

        composite = vs + ycs + ds + ss + os_
        regime = classify_regime(composite)
        weights = get_portfolio_weights(regime)

        records.append({
            "date":              dt,
            "vix_score":         vs,
            "yield_curve_score": ycs,
            "dollar_score":      ds,
            "sma200_score":      ss,
            "oil_score":         os_,
            "composite_score":   composite,
            "regime":            regime,
            "spy_weight":        weights.get("SPY", 0),
            "tlt_weight":        weights.get("SGOV", 0),
            "cash_weight":       weights.get("cash", 0),
        })

    result = pd.DataFrame(records).set_index("date")

    # SMA200 계산에 200일 필요 → 첫 200일은 NaN → 제거
    result = result.dropna(subset=["composite_score"])

    return result

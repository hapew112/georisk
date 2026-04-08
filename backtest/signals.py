"""
signals.py
일별 composite stress_score 계산.
"""

import pandas as pd


def label_stress(score: int) -> str:
    if score == 0:
        return "CALM"
    elif score == 1:
        return "NORMAL"
    elif score == 2:
        return "ELEVATED"
    else:
        return "HIGH_STRESS"


def compute_signals(data: dict) -> pd.DataFrame:
    """
    각 심볼 데이터로부터 일별 stress_score를 계산한다.

    스트레스 조건:
      1. VIX  일변화율 > +15%
      2. DXY  일변화율 > +0.8%
      3. WTI  일변화율 > +5%
      4. TNX  절대 변화  > +0.08 (이미 %포인트 단위)
      5. Gold 일변화율 > +2%

    반환 DataFrame 컬럼:
      date, vix_spike, dollar_surge, oil_spike, yield_jump, gold_rush,
      stress_score (0-5), stress_label
    """
    spy = data.get("SPY")
    if spy is None:
        raise ValueError("SPY data is required to build the signal index")

    # SPY 거래일 기준 인덱스
    idx = spy.index

    def close_series(symbol: str) -> pd.Series:
        df = data.get(symbol)
        if df is None or df.empty:
            return pd.Series(dtype=float)
        s = df["Close"].reindex(idx).ffill()
        return s

    vix   = close_series("^VIX")
    dxy   = close_series("DX-Y.NYB")
    wti   = close_series("CL=F")
    tnx   = close_series("^TNX")
    gold  = close_series("GC=F")

    # 일변화
    vix_chg  = vix.pct_change()
    dxy_chg  = dxy.pct_change()
    wti_chg  = wti.pct_change()
    tnx_diff = tnx.diff()          # 절대 변화 (단위: %포인트)
    gold_chg = gold.pct_change()

    # 스트레스 조건 (Boolean)
    vix_spike    = vix_chg  > 0.15
    dollar_surge = dxy_chg  > 0.008
    oil_spike    = wti_chg  > 0.05
    yield_jump   = tnx_diff > 0.08
    gold_rush    = gold_chg > 0.02

    stress_score = (
        vix_spike.astype(int)
        + dollar_surge.astype(int)
        + oil_spike.astype(int)
        + yield_jump.astype(int)
        + gold_rush.astype(int)
    )

    result = pd.DataFrame({
        "date":         idx,
        "vix_spike":    vix_spike,
        "dollar_surge": dollar_surge,
        "oil_spike":    oil_spike,
        "yield_jump":   yield_jump,
        "gold_rush":    gold_rush,
        "stress_score": stress_score,
    })
    result["stress_label"] = result["stress_score"].apply(label_stress)
    result = result.set_index("date")

    # 첫 행은 pct_change로 NaN → 제거
    result = result.dropna(subset=["stress_score"])

    return result

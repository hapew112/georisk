"""
backtest.py
GeoRisk 멀티팩터 레짐 백테스트 엔진 — CLI 진입점.

매일 5개 매크로/기술적 팩터를 종합하여 시장 레짐을 결정하고,
레짐에 따라 SPY/TLT/Cash 비율을 조정하는 포트폴리오를 시뮬레이션한다.

사용법:
    python backtest.py                        # 기본 max (20년+)
    python backtest.py --period 10y           # 10년
    python backtest.py --initial 50000        # 초기 자본 5만 달러
    python backtest.py --extra AAPL MSFT      # 추가 심볼 모니터링
"""

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import numpy as np

from data_fetcher import fetch_all
from signals import compute_regimes, REGIME_NAMES
from metrics import compute_portfolio_metrics, equity_curve_from_returns


RESULTS_DIR = Path(__file__).parent.parent / "results"


# ═══════════════════════════════════════════════════════════════
# 포트폴리오 시뮬레이션 엔진
# ═══════════════════════════════════════════════════════════════

def simulate_portfolio(data: dict, regimes_df: pd.DataFrame,
                       initial: float = 10000.0) -> dict:
    """
    일별 레짐 기반 포트폴리오를 시뮬레이션한다.

    Returns
    -------
    dict with:
        benchmark_equity : pd.Series  (SPY 100% B&H)
        strategy_equity  : pd.Series  (GeoRisk 레짐 전략)
        daily_log        : pd.DataFrame (일별 상세 기록)
    """
    spy_close = data["SPY"]["Close"]
    tlt_close = data.get("SGOV", pd.DataFrame()).get("Close")

    # 레짐 df와 SPY의 공통 인덱스만 사용
    common_idx = regimes_df.index.intersection(spy_close.index)
    if tlt_close is not None:
        common_idx = common_idx.intersection(tlt_close.index)
    common_idx = common_idx.sort_values()

    if len(common_idx) < 2:
        raise ValueError("Insufficient overlapping data between SPY, TLT, and regime dates")

    spy = spy_close.reindex(common_idx)
    tlt = tlt_close.reindex(common_idx) if tlt_close is not None else pd.Series(0.0, index=common_idx)
    regimes = regimes_df.reindex(common_idx)

    # 일수익률
    spy_ret = spy.pct_change().fillna(0)
    tlt_ret = tlt.pct_change().fillna(0)

    # 벤치마크: SPY 100% Buy & Hold
    benchmark = initial * (1 + spy_ret).cumprod()

    # 전략: 레짐별 가중치로 일별 포트폴리오 수익률
    strategy_values = [initial]
    daily_records = []

    for i in range(1, len(common_idx)):
        dt = common_idx[i]
        prev_dt = common_idx[i - 1]

        # 전일 레짐 기반으로 오늘 배분 결정 (look-ahead bias 방지)
        row = regimes.loc[prev_dt] if prev_dt in regimes.index else None
        if row is None:
            spy_w, tlt_w, cash_w = 1.0, 0.0, 0.0
            regime = "NORMAL"
        else:
            spy_w  = row["spy_weight"]
            tlt_w  = row["tlt_weight"]
            cash_w = row["cash_weight"]
            regime = row["regime"]

        # 오늘의 수익률
        r_spy = spy_ret.iloc[i]
        r_tlt = tlt_ret.iloc[i]

        port_ret = spy_w * r_spy + tlt_w * r_tlt + cash_w * 0.0
        new_val = strategy_values[-1] * (1 + port_ret)
        strategy_values.append(new_val)

        daily_records.append({
            "date": dt,
            "regime": regime,
            "spy_weight": spy_w,
            "tlt_weight": tlt_w,
            "cash_weight": cash_w,
            "spy_return": round(r_spy * 100, 4),
            "sgov_return": round(r_tlt * 100, 4),
            "portfolio_return": round(port_ret * 100, 4),
            "benchmark_value": round(benchmark.iloc[i], 2),
            "strategy_value": round(new_val, 2),
        })

    strategy_equity = pd.Series(strategy_values, index=common_idx)

    return {
        "benchmark_equity": benchmark,
        "strategy_equity": strategy_equity,
        "daily_log": pd.DataFrame(daily_records),
    }


# ═══════════════════════════════════════════════════════════════
# 결과 출력 및 저장
# ═══════════════════════════════════════════════════════════════

def _json_safe(obj):
    """numpy/pandas 타입을 JSON 직렬화 가능한 Python 기본 타입으로 변환."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "item"):
        return obj.item()
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj


def print_summary(metrics: dict, regimes_df: pd.DataFrame, period: str):
    b = metrics["benchmark"]
    s = metrics["strategy"]
    c = metrics["comparison"]

    def pct(v):
        return f"{v*100:.1f}%" if v is not None else "N/A"

    def pct2(v):
        return f"{v:.1f}%" if v is not None else "N/A"

    def ratio(v):
        return f"{v:.2f}" if v is not None else "N/A"

    # 데이터 기간 정보
    start = regimes_df.index[0].strftime("%Y-%m-%d")
    end = regimes_df.index[-1].strftime("%Y-%m-%d")
    n_years = len(regimes_df) / 252

    print(f"\n{'='*60}")
    print(f"  GeoRisk 멀티팩터 레짐 백테스트")
    print(f"  {start} → {end} ({n_years:.1f}년, {len(regimes_df)}거래일)")
    print(f"{'='*60}")
    print()
    print(f"  {'지표':<20} {'SPY B&H':>12} {'GeoRisk':>12}")
    print(f"  {'─'*20} {'─'*12} {'─'*12}")
    print(f"  {'총 수익률':<20} {pct2(b['total_return_pct']):>12} {pct2(s['total_return_pct']):>12}")
    print(f"  {'CAGR':<20} {pct(b['cagr']):>12} {pct(s['cagr']):>12}")
    print(f"  {'MDD':<20} {pct(b['mdd']):>12} {pct(s['mdd']):>12}")
    print(f"  {'연간 변동성':<20} {pct(b['annual_volatility']):>12} {pct(s['annual_volatility']):>12}")
    print(f"  {'Sharpe':<20} {ratio(b['sharpe']):>12} {ratio(s['sharpe']):>12}")
    print(f"  {'Calmar':<20} {ratio(b['calmar']):>12} {ratio(s['calmar']):>12}")
    print(f"  {'Sortino':<20} {ratio(b['sortino']):>12} {ratio(s['sortino']):>12}")
    print(f"  {'Win Rate':<20} {pct(b['win_rate']):>12} {pct(s['win_rate']):>12}")
    print()
    print(f"  ── 비교 ──")
    print(f"  MDD 개선률     : {pct2(c['mdd_improvement_pct'])}")
    print(f"  CAGR 차이      : {c['cagr_diff_pct']:+.2f}%p")
    print(f"  Sharpe 차이    : {c['sharpe_diff']:+.2f}")
    print(f"  변동성 감소율  : {pct2(c['volatility_reduction_pct'])}")
    print()

    # 레짐 분포
    regime_counts = regimes_df["regime"].value_counts()
    total = len(regimes_df)
    print(f"  ── 레짐 분포 ──")
    for r in REGIME_NAMES:
        cnt = regime_counts.get(r, 0)
        pct_r = cnt / total * 100
        bar = "█" * int(pct_r / 2)
        print(f"  {r:<12} {cnt:>5}일 ({pct_r:>5.1f}%)  {bar}")
    print()

    # 팩터별 평균
    print(f"  ── 팩터 평균 점수 (0~3) ──")
    for col in ["vix_score", "yield_curve_score", "dollar_score", "sma200_score", "oil_score"]:
        label = col.replace("_score", "").replace("_", " ").title()
        val = regimes_df[col].mean()
        print(f"  {label:<18} {val:.2f}")
    print(f"  {'Composite':<18} {regimes_df['composite_score'].mean():.2f} / 15")
    print()

    # 판정 (MDD 개선 + 리스크 조정 수익률 종합 판단)
    mdd_imp = c["mdd_improvement_pct"] or 0
    calmar_better = (s.get("calmar", 0) or 0) > (b.get("calmar", 0) or 0)
    sharpe_better = (s.get("sharpe", 0) or 0) >= (b.get("sharpe", 0) or 0) - 0.1

    if mdd_imp >= 50:
        verdict = "✅ 목표 달성 — MDD 50%+ 개선"
    elif mdd_imp >= 40 and calmar_better:
        verdict = "✅ 목표 달성 — MDD 40%+ 개선 + Calmar 우위"
    elif mdd_imp >= 30:
        verdict = "⚠️ 부분 달성 — MDD 30%+ 개선 (목표: 50%)"
    else:
        verdict = "❌ 미달 — 전략 재검토 필요"
    print(f"  판정: {verdict}")
    print(f"{'='*60}\n")


def build_result(metrics: dict, regimes_df: pd.DataFrame,
                 sim: dict, period: str) -> dict:
    """결과를 JSON 저장용 dict로 구성."""
    regime_counts = regimes_df["regime"].value_counts().to_dict()
    factor_means = {
        col: round(regimes_df[col].mean(), 3)
        for col in ["vix_score", "yield_curve_score", "dollar_score",
                     "sma200_score", "oil_score", "composite_score"]
    }

    # 최근 30일 일별 기록만 JSON에 포함 (전체는 너무 큼)
    recent_log = sim["daily_log"].tail(60).to_dict(orient="records")
    for rec in recent_log:
        if hasattr(rec["date"], "strftime"):
            rec["date"] = rec["date"].strftime("%Y-%m-%d")

    # 레짐 전환 이벤트 (레짐이 바뀐 날들)
    regime_changes = []
    prev_regime = None
    for _, row in regimes_df.iterrows():
        if row["regime"] != prev_regime:
            regime_changes.append({
                "date": row.name.strftime("%Y-%m-%d"),
                "from": prev_regime,
                "to": row["regime"],
                "composite_score": int(row["composite_score"]),
            })
            prev_regime = row["regime"]

    return _json_safe({
        "run_date": str(date.today()),
        "data_range": f"{regimes_df.index[0].date()} to {regimes_df.index[-1].date()}",
        "period": period,
        "trading_days": len(regimes_df),
        "years": round(len(regimes_df) / 252, 1),
        "metrics": metrics,
        "regime_distribution": regime_counts,
        "factor_averages": factor_means,
        "regime_changes_count": len(regime_changes),
        "regime_changes": regime_changes[-50:],   # 최근 50건
        "recent_daily_log": recent_log,
    })


# ═══════════════════════════════════════════════════════════════
# CLI 진입점
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="GeoRisk Multi-Factor Regime Backtest Engine"
    )
    parser.add_argument(
        "--period", default="max",
        help="yfinance 데이터 기간: max, 20y, 10y, 5y, 3y, 2y, 1y (기본: max)"
    )
    parser.add_argument(
        "--initial", type=float, default=10000.0,
        help="초기 투자 금액 (기본: $10,000)"
    )
    parser.add_argument(
        "--extra", nargs="*", default=[],
        help="추가 모니터링 심볼 (예: AAPL MSFT)"
    )
    parser.add_argument(
        "--output-dir", default=str(RESULTS_DIR),
        help="결과 JSON 출력 디렉토리"
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. 데이터 다운로드 ──
    print("=" * 60)
    print("  GeoRisk 멀티팩터 레짐 백테스트 시작")
    print("=" * 60)
    print(f"\n[1/4] 시장 데이터 다운로드 (period={args.period}) ...")
    data = fetch_all(period=args.period, extra_symbols=args.extra)

    if "SPY" not in data:
        print("ERROR: SPY 데이터를 가져올 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    spy_len = len(data["SPY"])
    print(f"       SPY: {spy_len}거래일 ({spy_len/252:.1f}년)")
    for sym, df in data.items():
        if sym != "SPY":
            print(f"       {sym}: {len(df)}거래일")

    # ── 2. 레짐 계산 ──
    print(f"\n[2/4] 멀티팩터 레짐 계산 ...")
    regimes_df = compute_regimes(data)
    print(f"       유효 거래일: {len(regimes_df)}")

    # ── 3. 포트폴리오 시뮬레이션 ──
    print(f"\n[3/4] 포트폴리오 시뮬레이션 (초기 ${args.initial:,.0f}) ...")
    sim = simulate_portfolio(data, regimes_df, initial=args.initial)

    # ── 4. 메트릭 계산 ──
    print(f"\n[4/4] 성과 메트릭 계산 ...")
    metrics = compute_portfolio_metrics(sim["benchmark_equity"], sim["strategy_equity"])

    # ── 결과 출력 ──
    print_summary(metrics, regimes_df, args.period)

    # ── JSON 저장 ──
    today_str = date.today().strftime("%Y%m%d")
    result = build_result(metrics, regimes_df, sim, args.period)
    out_path = out_dir / f"georisk_regime_{today_str}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

"""
backtest.py
GeoRisk Stress Backtest Engine — CLI 진입점.

사용법:
    python backtest.py
    python backtest.py --threshold 2 3
    python backtest.py --threshold 3 --period 1y
    python backtest.py --mode bearish --threshold 1 2
    python backtest.py --mode bearish --period 5y --threshold 1 2
"""

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

from data_fetcher import fetch_all
from signals import compute_signals
from metrics import compute_forward_returns, compute_metrics, verdict


RESULTS_DIR = Path(__file__).parent.parent / "results"


def _json_safe(obj):
    """numpy/pandas 타입을 JSON 직렬화 가능한 Python 기본 타입으로 변환."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "item"):          # numpy scalar
        return obj.item()
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj


def run_backtest(threshold: int, data: dict, signals_df, period: str, mode: str = "stress") -> dict:
    spy = data["SPY"]["Close"]

    # mode에 따라 사용할 score 컬럼 선택
    score_col = "bearish_score" if mode == "bearish" else "stress_score"

    # signal 발동일 추출
    fired = signals_df[signals_df[score_col] >= threshold]
    signal_dates = [
        {"date": d, "score": int(row[score_col])}
        for d, row in fired.iterrows()
    ]

    forward_df = compute_forward_returns(spy, signal_dates)
    metrics = compute_metrics(forward_df, spy, threshold)
    vdict = verdict(metrics)

    # signal_events 리스트 (JSON용)
    events = []
    for _, row in forward_df.iterrows():
        events.append({
            "date":        str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"]),
            "score":       int(row["score"]) if not math.isnan(row["score"]) else None,
            "ret_1d":      round(float(row["ret_1d"]),  2) if not math.isnan(row["ret_1d"])  else None,
            "ret_3d":      round(float(row["ret_3d"]),  2) if not math.isnan(row["ret_3d"])  else None,
            "ret_5d":      round(float(row["ret_5d"]),  2) if not math.isnan(row["ret_5d"])  else None,
            "ret_10d":     round(float(row["ret_10d"]), 2) if not math.isnan(row["ret_10d"]) else None,
            "drawdown_5d": round(float(row["drawdown_5d"]), 2) if not math.isnan(row["drawdown_5d"]) else None,
        })

    spy_idx = spy.index
    data_range = f"{spy_idx[0].date()} to {spy_idx[-1].date()}"

    result = {
        "run_date":      str(date.today()),
        "data_range":    data_range,
        "period":        period,
        "mode":          mode,
        "threshold":     threshold,
        "total_signals": metrics.get("total_signals", 0),
        "metrics":       metrics,
        "signal_events": events,
        "verdict":       vdict,
    }
    return _json_safe(result)


def print_summary(result: dict):
    m = result["metrics"]
    hr3  = m.get("hit_rate_3d")
    hr5  = m.get("hit_rate_5d")
    ar3  = m.get("avg_return_3d")
    ar5  = m.get("avg_return_5d")
    vs5  = m.get("signal_vs_baseline_5d")
    far  = m.get("false_alarm_rate")

    def fmt_pct(v, decimals=1):
        if v is None:
            return "N/A"
        return f"{v * 100:.{decimals}f}%"

    def fmt_ret(v):
        if v is None:
            return "N/A"
        return f"{v:+.2f}%"

    mode_label = "BEARISH (SPY↓ filter)" if result.get("mode") == "bearish" else "STRESS (volatility)"
    print(f"\nGeoRisk Stress Backtest  ({result['data_range']})")
    print("━" * 50)
    print(f"Mode          : {mode_label}")
    print(f"Threshold     : score >= {result['threshold']}")
    print(f"Signals fired : {result['total_signals']}")
    print(f"Hit rate (3d) : {fmt_pct(hr3)}")
    print(f"Hit rate (5d) : {fmt_pct(hr5)}")
    print(f"False alarms  : {fmt_pct(far)}")
    print(f"Avg ret  (3d) : {fmt_ret(ar3)}")
    print(f"Avg ret  (5d) : {fmt_ret(ar5)}")
    print(f"vs Baseline 5d: {fmt_ret(vs5)}")
    print(f"Verdict       : {result['verdict']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="GeoRisk Stress Backtest Engine")
    parser.add_argument(
        "--threshold", type=int, nargs="+", default=[2, 3],
        help="Stress score threshold(s) to evaluate (default: 2 3)"
    )
    parser.add_argument(
        "--period", default="2y",
        help="Data period for yfinance (default: 2y)"
    )
    parser.add_argument(
        "--mode", choices=["stress", "bearish"], default="stress",
        help="stress=순수 변동성 신호, bearish=SPY 하락일 필터링 (default: stress)"
    )
    parser.add_argument(
        "--output-dir", default=str(RESULTS_DIR),
        help="Directory for JSON output files"
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching market data ...")
    data = fetch_all(period=args.period)

    if "SPY" not in data:
        print("ERROR: Could not fetch SPY data. Aborting.", file=sys.stderr)
        sys.exit(1)

    print("Computing stress signals ...")
    signals_df = compute_signals(data)

    today_str = date.today().strftime("%Y%m%d")

    for threshold in args.threshold:
        print(f"\nRunning backtest: threshold={threshold}, mode={args.mode} ...")
        result = run_backtest(threshold, data, signals_df, args.period, mode=args.mode)
        print_summary(result)

        out_path = out_dir / f"backtest_{args.mode}_threshold{threshold}_{today_str}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

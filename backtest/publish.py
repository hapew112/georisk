"""
publish.py
Cloudflare KV 업로드:
  --backtest  : 최신 백테스트 결과 → latest_regime
  --paper     : paper_log.json 요약 → paper_summary
  (인자 없음) : 두 가지 모두 실행

Requires env vars: CF_ACCOUNT_ID, CF_NAMESPACE_ID, CF_API_TOKEN
"""
import os
import json
import glob
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

ACCOUNT_ID   = os.environ.get("CF_ACCOUNT_ID", "")
NAMESPACE_ID = os.environ.get("CF_NAMESPACE_ID", "")
API_TOKEN    = os.environ.get("CF_API_TOKEN", "")

LOG_PATH = Path.home() / "georisk" / "paper_log.json"


def kv_put(kv_key: str, data: dict) -> bool:
    if not all([ACCOUNT_ID, NAMESPACE_ID, API_TOKEN]):
        print("CF 환경변수 미설정 (CF_ACCOUNT_ID / CF_NAMESPACE_ID / CF_API_TOKEN)")
        return False
    url = (f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"
           f"/storage/kv/namespaces/{NAMESPACE_ID}/values/{kv_key}")
    cmd = [
        "curl", "-s", "-X", "PUT", url,
        "-H", f"Authorization: Bearer {API_TOKEN}",
        "-H", "Content-Type: application/json",
        "--data", json.dumps(data),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    ok = '"success":true' in result.stdout
    print(f"[KV] {kv_key}: {'OK' if ok else 'FAILED ' + result.stderr[:120]}")
    return ok


def publish_backtest():
    results_dir = Path(__file__).parent.parent / "results"
    files = sorted(glob.glob(str(results_dir / "*.json")))
    if not files:
        print("백테스트 결과 파일 없음 (results/*.json)")
        return
    with open(files[-1]) as f:
        data = json.load(f)
    print(f"[Backtest] 업로드: {files[-1]}")
    kv_put("latest_regime", data)


def publish_paper():
    if not LOG_PATH.exists():
        print("paper_log.json 없음")
        return

    with open(LOG_PATH) as f:
        history = json.load(f)

    if not history:
        print("paper_log.json 비어있음")
        return

    history.sort(key=lambda x: x['date'])
    last = history[-1]
    first = history[0]

    initial_value    = 10000.0
    current_value    = last['portfolio_value']
    benchmark_value  = last['benchmark_value']
    total_return_pct = (current_value / initial_value - 1) * 100
    bench_return_pct = (benchmark_value / initial_value - 1) * 100
    alpha_pct        = total_return_pct - bench_return_pct

    total_fees   = sum(e.get('fee_applied', 0) for e in history)
    rebalances   = sum(1 for e in history if e.get('rebalanced'))

    # 7일치 최근 데이터
    cutoff = (datetime.strptime(last['date'], "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")
    recent = [e for e in history if e['date'] >= cutoff]

    expected_monthly = 0.017
    adjusted_expected = expected_monthly * (len(history) / 21.0)
    actual = total_return_pct / 100
    if actual > adjusted_expected * 1.1:
        status = "AHEAD"
    elif actual < adjusted_expected * 0.9:
        status = "BEHIND"
    else:
        status = "ON TRACK"

    summary = {
        "as_of":              last['date'],
        "trading_days":       len(history),
        "start_value":        initial_value,
        "current_value":      round(current_value, 2),
        "benchmark_value":    round(benchmark_value, 2),
        "total_return_pct":   round(total_return_pct, 4),
        "benchmark_return_pct": round(bench_return_pct, 4),
        "alpha_pct":          round(alpha_pct, 4),
        "current_regime":     last['regime'],
        "current_action":     last['action'],
        "current_alloc": {
            "SPY":  last['spy_weight'],
            "TLT":  last['tlt_weight'],
            "cash": last['cash_weight'],
        },
        "rebalances":   rebalances,
        "total_fees":   round(total_fees, 4),
        "status":       status,
        "recent_7d":    recent[-7:],
    }

    print(f"[Paper] 업로드: {len(history)}일치 → paper_summary")
    kv_put("paper_summary", summary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--paper",    action="store_true")
    args = parser.parse_args()

    run_all = not args.backtest and not args.paper
    if run_all or args.backtest:
        publish_backtest()
    if run_all or args.paper:
        publish_paper()


if __name__ == "__main__":
    main()

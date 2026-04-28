import os
import json
import glob
import argparse
import subprocess
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

ACCOUNT_ID   = os.environ.get("CF_ACCOUNT_ID", "")
NAMESPACE_ID = os.environ.get("CF_NAMESPACE_ID", "")
API_TOKEN    = os.environ.get("CF_API_TOKEN", "")

# Update LOG_PATH to be relative to the script location or use an absolute path
# The previous version used Path.home() / "georisk" / "paper_log.json"
# But georisk is at /home/hapew112/georisk/
LOG_PATH = Path("/home/hapew112/georisk/paper_log.json")

def kv_put(kv_key: str, data: dict) -> bool:
    if not all([ACCOUNT_ID, NAMESPACE_ID, API_TOKEN]):
        print(f"CF 환경변수 미설정 (CF_ACCOUNT_ID / CF_NAMESPACE_ID / CF_API_TOKEN)")
        return False
    
    # Use standard python requests if possible, or curl as fallback
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
    if not ok:
        print(f"[KV] {kv_key} FAILED: {result.stdout}")
    else:
        print(f"[KV] {kv_key} OK")
    return ok

def calculate_paper_metrics(history):
    if not history:
        return {}
    
    returns = [e.get('portfolio_return_pct', 0) / 100 for e in history]
    returns = np.array(returns)
    std = returns.std()
    mean = returns.mean()
    sharpe = (mean / std * np.sqrt(252)) if std > 0 else 0
    
    values = [e.get('portfolio_value', 10000.0) for e in history]
    values = np.array(values)
    peak = np.maximum.accumulate(values)
    dd = (values / peak) - 1
    mdd = dd.min()
    
    days_active = len(history)
    initial_value = 10000.0
    current_value = history[-1].get('portfolio_value', 10000.0)
    # Estimate years based on trading days
    years = days_active / 252.0
    cagr = (current_value / initial_value)**(1/years) - 1 if years > 0 else 0
    
    return {
        "sharpe": round(float(sharpe), 2),
        "mdd": round(float(mdd) * 100, 2),
        "cagr": round(float(cagr) * 100, 2),
        "total_return": round(((current_value / initial_value) - 1) * 100, 2),
        "days_active": days_active
    }

def publish_backtest():
    # Adjusted to look for results in georisk/results
    results_dir = Path("/home/hapew112/georisk/results")
    files = sorted(glob.glob(str(results_dir / "*.json")))
    if not files:
        print(f"백테스트 결과 파일 없음 ({results_dir}/*.json)")
        return
    with open(files[-1]) as f:
        data = json.load(f)
    print(f"[Backtest] 업로드: {files[-1]}")
    kv_put("latest_regime", data)

def publish_paper():
    if not LOG_PATH.exists():
        print(f"paper_log.json 없음: {LOG_PATH}")
        return

    with open(LOG_PATH) as f:
        history = json.load(f)

    if not history:
        print("paper_log.json 비어있음")
        return

    history.sort(key=lambda x: x['date'])
    last = history[-1]
    
    # Push 3 keys to KV:
    # 1. paper_log -> last 30 days
    kv_put("paper_log", history[-30:])
    
    # 2. paper_status -> {regime, action, weights, updated_at}
    status = {
        "regime": last.get('regime', 'N/A'),
        "action": last.get('action', 'N/A'),
        "weights": {
            "SPY": last.get('spy_weight', 0),
            "TLT": last.get('tlt_weight', 0),
            "cash": last.get('cash_weight', 0),
        },
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    kv_put("paper_status", status)
    
    # 3. paper_metrics -> {sharpe, mdd, cagr, total_return, days_active}
    metrics = calculate_paper_metrics(history)
    kv_put("paper_metrics", metrics)
    
    # Also keep paper_summary for backward compatibility if needed
    summary = {
        "as_of":              last['date'],
        "trading_days":       len(history),
        "current_value":      round(last.get('portfolio_value', 10000.0), 2),
        "total_return_pct":   metrics['total_return'],
        "current_regime":     last.get('regime', 'N/A'),
        "current_action":     last.get('action', 'N/A'),
        "metrics":            metrics
    }
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

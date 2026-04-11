"""
publish.py
Upload latest backtest result to Cloudflare KV.
Usage: python publish.py
Requires env vars: CF_ACCOUNT_ID, CF_NAMESPACE_ID, CF_API_TOKEN
"""
import os, json, glob, subprocess
from pathlib import Path

ACCOUNT_ID   = os.environ.get("CF_ACCOUNT_ID", "")
NAMESPACE_ID = os.environ.get("CF_NAMESPACE_ID", "")
API_TOKEN    = os.environ.get("CF_API_TOKEN", "")

def main():
    results_dir = Path(__file__).parent.parent / "results"
    files = sorted(glob.glob(str(results_dir / "*.json")))
    if not files:
        print("No result files found in results/")
        return
    latest = files[-1]
    print(f"Uploading: {latest}")
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/values/latest_regime"
    cmd = [
        "curl", "-s", "-X", "PUT", url,
        "-H", f"Authorization: Bearer {API_TOKEN}",
        "-H", "Content-Type: application/json",
        "--data-binary", f"@{latest}"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if '"success":true' in result.stdout:
        print("Upload OK")
    else:
        print("Upload FAILED:", result.stderr)

if __name__ == "__main__":
    main()

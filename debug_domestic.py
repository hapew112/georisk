
import os
import requests
import json
from pathlib import Path

BASE_URL = "https://openapivts.koreainvestment.com:29443"
APP_KEY    = "PSOSmYfVzEaN9FGy3h3fHSrgNaaMbvm5MqEy"
APP_SECRET = "x4oNggjkv+x4YI+LcQ32Fn0GM6aOOzmORAexbL1Ylymp2fjn0jnWd1SDRkvfpMHXuD2NmpN5JIjCxikPk2g6/zANA7SfSclTTS8GQAHzDjoKkxn9NAwIHXFNGNeuR+eiL1dTAYo3NrapKceQLSYz/NcVdgds/3mRhXHKPIpiwJa5Z6A/sj4="
ACCOUNT    = "50184581"
TOKEN_CACHE = Path("/home/hapew112/georisk/.kis_token.json")

def get_token():
    if TOKEN_CACHE.exists():
        cached = json.loads(TOKEN_CACHE.read_text())
        return cached["token"]
    return None

def debug_domestic_deposit(token, prod_code):
    # 국내주식 예수금 조회 (VTTR3112R)
    params = {
        "CANO": ACCOUNT,
        "ACNT_PRDT_CD": prod_code,
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTR3112R",
        "custtype": "P",
    }
    resp = requests.get(f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-order", headers=headers, params=params)
    print(f"\n--- [국내 예수금] Prod Code: {prod_code} ---")
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except:
        print("Response is not JSON:", resp.text)

if __name__ == "__main__":
    token = get_token()
    if token:
        debug_domestic_deposit(token, "01")
        debug_domestic_deposit(token, "02")

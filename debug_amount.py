
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
    
    resp = requests.post(f"{BASE_URL}/oauth2/tokenP", json={
        "grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET
    })
    return resp.json().get("access_token")

def debug_orderable_amount(token, prod_code):
    params = {
        "CANO": ACCOUNT,
        "ACNT_PRDT_CD": prod_code,
        "OVRS_EXCG_CD": "NASD",
        "TR_CRCY_CD": "USD",
    }
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTT3011R", # 해외주식 주문가능금액 조회
        "custtype": "P",
    }
    resp = requests.get(f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-psbl-order", headers=headers, params=params)
    print(f"\n--- [주문가능금액] Prod Code: {prod_code} ---")
    try:
        data = resp.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except:
        print("Response is not JSON:", resp.text)

if __name__ == "__main__":
    token = get_token()
    if token:
        debug_orderable_amount(token, "01")
        debug_orderable_amount(token, "02")

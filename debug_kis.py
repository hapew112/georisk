
import os
import requests
import json
from datetime import datetime, timedelta
from pathlib import Path

BASE_URL = "https://openapivts.koreainvestment.com:29443"
APP_KEY    = "PSOSmYfVzEaN9FGy3h3fHSrgNaaMbvm5MqEy"
APP_SECRET = "x4oNggjkv+x4YI+LcQ32Fn0GM6aOOzmORAexbL1Ylymp2fjn0jnWd1SDRkvfpMHXuD2NmpN5JIjCxikPk2g6/zANA7SfSclTTS8GQAHzDjoKkxn9NAwIHXFNGNeuR+eiL1dTAYo3NrapKceQLSYz/NcVdgds/3mRhXHKPIpiwJa5Z6A/sj4="
ACCOUNT    = "50184581"

def get_token():
    resp = requests.post(
        f"{BASE_URL}/oauth2/tokenP",
        headers={"Content-Type": "application/json"},
        json={
            "grant_type": "client_credentials",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
        },
    )
    if resp.status_code != 200:
        print("Token Error:", resp.text)
        return None
    return resp.json()["access_token"]

def debug_balance(token, prod_code):
    params = {
        "CANO": ACCOUNT,
        "ACNT_PRDT_CD": prod_code,
        "OVRS_EXCG_CD": "NASD",
        "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": "",
    }
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTS3012R",
        "custtype": "P",
    }
    resp = requests.get(
        f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-balance",
        headers=headers,
        params=params,
    )
    print(f"\n--- Product Code: {prod_code} ---")
    print("Response Status:", resp.status_code)
    print("Response Body:", json.dumps(resp.json(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    token = get_token()
    if token:
        debug_balance(token, "01")
        debug_balance(token, "02")
        debug_balance(token, "03")

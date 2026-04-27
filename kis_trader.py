"""
KIS Trader - 한국투자증권 모의투자 API 연동
georisk_v2.py 시그널 → 해외주식 자동 주문 (SPY / TLT)

사용법:
  python3 kis_trader.py           # 시그널 확인 + 주문 실행
  python3 kis_trader.py --dry-run # 주문 없이 시뮬레이션만
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# 설정
# ============================================================
BASE_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자

APP_KEY    = os.environ.get("KIS_APP_KEY",    "PSOSmYfVzEaN9FGy3h3fHSrgNaaMbvm5MqEy")
APP_SECRET = os.environ.get("KIS_APP_SECRET", "x4oNggjkv+x4YI+LcQ32Fn0GM6aOOzmORAexbL1Ylymp2fjn0jnWd1SDRkvfpMHXuD2NmpN5JIjCxikPk2g6/zANA7SfSclTTS8GQAHzDjoKkxn9NAwIHXFNGNeuR+eiL1dTAYo3NrapKceQLSYz/NcVdgds/3mRhXHKPIpiwJa5Z6A/sj4=")
ACCOUNT    = os.environ.get("KIS_ACCOUNT",    "50184581")
ACNT_PROD  = os.environ.get("KIS_ACCOUNT_PROD","01")

TOKEN_CACHE = Path(__file__).parent / ".kis_token.json"

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ============================================================
# 토큰 관리
# ============================================================
def get_token() -> str:
    # 캐시된 토큰이 유효하면 재사용
    if TOKEN_CACHE.exists():
        cached = json.loads(TOKEN_CACHE.read_text())
        expires = datetime.fromisoformat(cached["expires"])
        if datetime.now() < expires - timedelta(minutes=10):
            return cached["token"]

    resp = requests.post(
        f"{BASE_URL}/oauth2/tokenP",
        headers={"Content-Type": "application/json"},
        json={
            "grant_type": "client_credentials",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["access_token"]
    expires_in = int(data.get("expires_in", 86400))

    TOKEN_CACHE.write_text(json.dumps({
        "token": token,
        "expires": (datetime.now() + timedelta(seconds=expires_in)).isoformat(),
    }))
    return token


def headers(token: str, tr_id: str) -> dict:
    return {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }

# ============================================================
# 잔고 조회
# ============================================================
def get_balance(token: str) -> dict:
    """
    해외주식 잔고 조회 → {"SPY": {"qty": x, "price": y}, ...}
    """
    params = {
        "CANO": ACCOUNT,
        "ACNT_PRDT_CD": ACNT_PROD,
        "OVRS_EXCG_CD": "NASD",
        "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": "",
    }
    resp = requests.get(
        f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-balance",
        headers=headers(token, "VTTS3012R"),
        params=params,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    holdings = {}
    total_stock_val = 0.0
    output1 = data.get("output1", [])
    if isinstance(output1, dict):
        output1 = [output1]
    for item in output1:
        sym   = item.get("ovrs_pdno", "").strip()
        qty   = float(item.get("ovrs_cblc_qty", 0) or 0)
        price = float(item.get("now_pric2", 0) or 0)
        evlu  = float(item.get("ovrs_stck_evlu_amt", 0) or 0)
        if sym and qty > 0:
            holdings[sym] = {"qty": qty, "price": price}
            total_stock_val += evlu if evlu else qty * price

    # output2: 총평가 / 예수금
    output2 = data.get("output2", {})
    if isinstance(output2, list):
        output2 = output2[0] if output2 else {}
    total_eval = float(output2.get("tot_evlu_pfls_amt", 0) or 0)
    cash_usd   = float(output2.get("frcr_dncl_amt_2", 0) or 0)

    # total_eval 이 0이면 주식 평가액 + 예수금으로 추정
    if total_eval == 0:
        total_eval = total_stock_val + cash_usd

    return {"holdings": holdings, "total_eval": total_eval, "cash_usd": cash_usd}


def get_current_price(symbol: str) -> float:
    """현재가 조회 (yfinance — 모의투자 서버는 시세 API 미지원)"""
    import yfinance as yf
    try:
        return float(yf.Ticker(symbol).fast_info["last_price"])
    except Exception as e:
        print(f"  {symbol} 시세 조회 실패: {e}")
        return 0.0

# ============================================================
# 주문
# ============================================================
def place_order(token: str, symbol: str, side: str, qty: int, price: float) -> dict:
    """
    side: "buy" | "sell"
    미국(NASD): 매수 VTTT1002U / 매도 VTTT1006U  (모의: T→V)
    모의투자는 지정가(ORD_DVSN=00)만 가능
    """
    if side == "buy":
        tr_id = "VTTT1002U"
        sll_type = ""
    else:
        tr_id = "VTTT1006U"
        sll_type = "00"

    body = {
        "CANO": ACCOUNT,
        "ACNT_PRDT_CD": ACNT_PROD,
        "OVRS_EXCG_CD": "NASD",
        "PDNO": symbol,
        "ORD_DVSN": "00",
        "ORD_QTY": str(qty),
        "OVRS_ORD_UNPR": f"{price:.2f}",
        "CTAC_TLNO": "",
        "MGCO_APTM_ODNO": "",
        "SLL_TYPE": sll_type,
        "ORD_SVR_DVSN_CD": "0",
    }
    resp = requests.post(
        f"{BASE_URL}/uapi/overseas-stock/v1/trading/order",
        headers=headers(token, tr_id),
        json=body,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

# ============================================================
# 시그널 가져오기
# ============================================================
def get_signal() -> dict:
    from georisk_v2 import GeoRiskV2, fetch_data
    engine = GeoRiskV2()
    df = fetch_data(period="2y")
    signal = engine.run(df, mode="live")
    return signal

# ============================================================
# 리밸런싱 계산
# ============================================================
def calc_orders(signal: dict, balance: dict, prices: dict) -> list:
    """
    목표비중 vs 현재비중 비교 → 주문 리스트 반환
    [{"symbol": "SPY", "side": "buy"/"sell", "qty": n, "price": p}, ...]
    """
    total = balance["total_eval"]
    if total <= 0:
        print("잔고 없음 — 주문 스킵")
        return []

    targets = {
        "SPY": signal["w_spy"],
        "TLT": signal["w_tlt"],
    }

    holdings = balance["holdings"]
    orders = []

    for sym, target_w in targets.items():
        price = prices.get(sym, 0)
        if price <= 0:
            continue

        current_qty  = holdings.get(sym, {}).get("qty", 0)
        current_val  = current_qty * price
        current_w    = current_val / total

        target_val   = total * target_w
        target_qty   = int(target_val / price)
        diff_w       = target_w - current_w

        # 리밸런싱 필터: 비중 차이 5% 미만 skip
        if abs(diff_w) < 0.05:
            print(f"  {sym}: 변화 {diff_w*100:.1f}%p → SKIP")
            continue

        diff_qty = target_qty - int(current_qty)
        if diff_qty == 0:
            continue

        side = "buy" if diff_qty > 0 else "sell"
        orders.append({
            "symbol": sym,
            "side": side,
            "qty": abs(diff_qty),
            "price": price,
            "current_w": current_w,
            "target_w": target_w,
        })

    return orders

# ============================================================
# Telegram
# ============================================================
def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    import urllib.request
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg}).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Telegram error: {e}")

# ============================================================
# 메인
# ============================================================
def main(dry_run: bool = False):
    print(f"\n{'='*45}")
    print(f"  KIS Trader {'[DRY RUN]' if dry_run else '[LIVE]'} — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*45}")

    # 1. 토큰
    print("토큰 발급 중...")
    token = get_token()
    print("  OK")

    # 2. 시그널
    print("시그널 계산 중...")
    signal = get_signal()
    print(f"  SPY {signal['w_spy']*100:.1f}% / TLT {signal['w_tlt']*100:.1f}% / CASH {signal['w_cash']*100:.1f}%")

    # 3. 잔고
    print("잔고 조회 중...")
    balance = get_balance(token)
    print(f"  총 평가액: ${balance['total_eval']:,.2f}")
    print(f"  예수금:    ${balance['cash_usd']:,.2f}")
    for sym, info in balance["holdings"].items():
        print(f"  {sym}: {info['qty']:.0f}주 × ${info['price']:.2f}")

    # 4. 현재가 (yfinance)
    prices = {}
    for sym in ["SPY", "TLT"]:
        prices[sym] = get_current_price(sym)
        print(f"  {sym} 현재가: ${prices[sym]:.2f}")

    # 5. 주문 계산
    print("\n주문 계산 중...")
    # dry-run + 잔고 0 → 가상 $10,000으로 시뮬레이션
    if dry_run and balance["total_eval"] == 0:
        print("  [DRY RUN] 잔고 없음 → 가상 $10,000 기준 시뮬레이션")
        spy_price = prices.get("SPY", 550)
        tlt_price = prices.get("TLT", 90)
        balance = {
            "holdings": {},
            "total_eval": 10000.0,
            "cash_usd": 10000.0,
        }
    orders = calc_orders(signal, balance, prices)

    if not orders:
        msg = (
            f"📊 GeoRisk | {signal['date']}\n"
            f"SPY {signal['w_spy']*100:.1f}% / TLT {signal['w_tlt']*100:.1f}%\n"
            f"리밸런싱 불필요 — HOLD"
        )
        print("  리밸런싱 불필요")
        send_telegram(msg)
        return

    # 6. 주문 실행
    results = []
    for o in orders:
        action = f"  {'[DRY]' if dry_run else ''} {o['side'].upper()} {o['symbol']} {o['qty']}주 @ ${o['price']:.2f}"
        action += f"  ({o['current_w']*100:.1f}% → {o['target_w']*100:.1f}%)"
        print(action)

        if not dry_run:
            try:
                result = place_order(token, o["symbol"], o["side"], o["qty"], o["price"])
                status = result.get("rt_cd", "?")
                msg_code = result.get("msg1", "")
                print(f"    → rt_cd={status} {msg_code}")
                results.append({"symbol": o["symbol"], "side": o["side"],
                                 "qty": o["qty"], "status": status, "msg": msg_code})
                time.sleep(0.5)  # API rate limit
            except Exception as e:
                print(f"    → 오류: {e}")
                results.append({"symbol": o["symbol"], "side": o["side"],
                                 "qty": o["qty"], "status": "ERROR", "msg": str(e)})

    # 7. Telegram
    order_lines = "\n".join(
        f"{'✅' if r.get('status')=='0' else '⚠️'} {r['side'].upper()} {r['symbol']} {r['qty']}주"
        for r in (results if results else orders)
    )
    tg_msg = (
        f"📊 GeoRisk {'DRY RUN' if dry_run else '주문 완료'} | {signal['date']}\n"
        f"SPY {signal['w_spy']*100:.1f}% / TLT {signal['w_tlt']*100:.1f}% / CASH {signal['w_cash']*100:.1f}%\n"
        f"Vol: {signal['realized_vol']*100:.1f}%  Corr: {signal['corr']:.3f}  DD: {signal['drawdown']*100:.2f}%\n\n"
        f"{order_lines}"
    )
    send_telegram(tg_msg)
    print(f"\n{'='*45}")


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)

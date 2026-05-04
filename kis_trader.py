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
from zoneinfo import ZoneInfo
import google.generativeai as genai  # Added for market insights

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

# 미국 장 운영시간 (ET) → KST 기준 23:30~06:00 (정규장)
# 모의투자 주문 가능: 정규장 시간 + 프리마켓/애프터 일부
US_MARKET_OPEN_ET  = 9   # 9:30 AM ET
US_MARKET_CLOSE_ET = 16  # 4:00 PM ET

# ============================================================
# 유틸: 미국 장 오픈 여부 확인
# ============================================================
def is_us_market_open() -> bool:
    """미국 정규장 시간인지 확인 (ET 기준 9:30~16:00, 평일만)"""
    try:
        now_et = datetime.now(ZoneInfo("America/New_York"))
        # 주말 체크
        if now_et.weekday() >= 5:  # 토(5), 일(6)
            return False
        hour = now_et.hour
        minute = now_et.minute
        # 9:30 ~ 16:00
        if hour < US_MARKET_OPEN_ET or (hour == US_MARKET_OPEN_ET and minute < 30):
            return False
        if hour >= US_MARKET_CLOSE_ET:
            return False
        return True
    except Exception:
        return False  # 불확실하면 False


def get_market_status_str() -> str:
    """현재 미국 장 상태를 문자열로 반환"""
    try:
        now_et = datetime.now(ZoneInfo("America/New_York"))
        now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
        status = "OPEN ✅" if is_us_market_open() else "CLOSED ❌"
        return f"{status} (ET: {now_et.strftime('%H:%M')}, KST: {now_kst.strftime('%H:%M')})"
    except Exception:
        return "UNKNOWN"


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
# 잔고 및 자산 조회
# ============================================================
def get_holdings(token: str, max_retries: int = 3) -> dict:
    """
    해외주식 잔고 조회 (보유 종목 수량 및 수익률)
    → {"SPY": {"qty": x, "price": y, "avg_price": z, "profit_rt": p}, ...}
    TR_ID: VTTS3012R (모의)
    """
    params = {
        "CANO": ACCOUNT,
        "ACNT_PRDT_CD": ACNT_PROD,
        "OVRS_EXCG_CD": "NASD",
        "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": "",
    }
    
    for attempt in range(max_retries):
        try:
            resp = requests.get(
                f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-balance",
                headers=headers(token, "VTTS3012R"),
                params=params,
                timeout=15,
            )
            if resp.status_code == 500:
                print(f"  [WARN] 잔고 조회 500 에러 (attempt {attempt+1}/{max_retries})")
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()

            holdings = {}
            output1 = data.get("output1", [])
            if isinstance(output1, dict):
                output1 = [output1]
            for item in output1:
                sym   = item.get("ovrs_pdno", "").strip()
                qty   = float(item.get("ovrs_cblc_qty", 0) or 0)
                price = float(item.get("now_pric2", 0) or 0)
                avg_p = float(item.get("pchs_avg_pric", 0) or 0)
                profit = float(item.get("evlu_pflt_rt", 0) or 0)
                if sym and qty > 0:
                    holdings[sym] = {
                        "qty": qty, 
                        "price": price, 
                        "avg_price": avg_p,
                        "profit_rt": profit
                    }
            return holdings
        except Exception as e:
            print(f"  [ERR] 잔고 조회 실패 (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
    
    print("  [WARN] 잔고 조회 최종 실패 — 빈 잔고로 진행")
    return {}


def get_account_summary(token: str, max_retries: int = 3) -> dict:
    """
    통합증거금 및 예수금 상세 조회
    → {"total_krw": x, "cash_usd": y, "ord_psbl_krw": z}
    TR_ID: VTRP6504R (모의)
    """
    params = {
        "CANO": ACCOUNT,
        "ACNT_PRDT_CD": ACNT_PROD,
        "WCRC_FRCR_DVSN_CD": "02", # 외화
        "NATN_CD": "000",          # 전체
        "TR_MKET_CD": "00",        # 전체
        "INQR_DVSN_CD": "00",      # 전체
    }
    
    for attempt in range(max_retries):
        try:
            resp = requests.get(
                f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-present-balance",
                headers=headers(token, "VTRP6504R"),
                params=params,
                timeout=15,
            )
            if resp.status_code == 500:
                print(f"  [WARN] 자산 조회 500 에러 (attempt {attempt+1}/{max_retries})")
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            
            output3 = data.get("output3", {})
            if isinstance(output3, list):
                output3 = output3[0] if output3 else {}
            
            return {
                "total_krw": float(output3.get("tot_asst_amt", 0) or 0),
                "cash_usd": float(output3.get("frcr_dncl_amt_2", 0) or 0),
                "ord_psbl_krw": float(output3.get("ord_psbl_amt", 0) or 0)
            }
        except Exception as e:
            print(f"  [ERR] 자산 조회 실패 (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
    
    print("  [WARN] 자산 조회 최종 실패")
    return {"total_krw": 0, "cash_usd": 0, "ord_psbl_krw": 0}


def get_total_krw(token: str) -> float:
    summary = get_account_summary(token)
    return summary["total_krw"]


def get_psamount(token: str, symbol: str, price: float) -> int:
    """
    해외주식 매수 가능 수량 조회
    TR_ID: VTTS3307R (모의 추정)
    """
    params = {
        "CANO": ACCOUNT,
        "ACNT_PRDT_CD": ACNT_PROD,
        "OVRS_EXCG_CD": "NASD",
        "ITEM_CD": symbol,
        "OVRS_ORD_UNPR": f"{price:.2f}",
    }
    try:
        resp = requests.get(
            f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-psamount",
            headers=headers(token, "VTTS3307R"),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        qty = int(data.get("output", {}).get("ovrs_max_ord_psbl_qty", 0) or 0)
        return qty
    except Exception as e:
        print(f"  [WARN] {symbol} 매수가능수량 조회 실패: {e}")
        return -1  # -1 = 조회 실패 (999999 대신 명확한 실패 반환)


def get_krw_usd() -> float:
    """환율 조회 (Frankfurter API)"""
    fallback = float(os.environ.get("KRW_USD_RATE", 1430))
    try:
        resp = requests.get("https://api.frankfurter.app/latest?from=USD&to=KRW", timeout=5)
        resp.raise_for_status()
        return float(resp.json()["rates"]["KRW"])
    except Exception as e:
        print(f"  환율 조회 실패, fallback {fallback} 사용: {e}")
        return fallback


def get_current_price(symbol: str) -> float:
    """현재가 조회 (yfinance — 모의투자 서버는 시세 API 미지원)"""
    import yfinance as yf
    try:
        return float(yf.Ticker(symbol).fast_info["last_price"])
    except Exception as e:
        print(f"  {symbol} 시세 조회 실패: {e}")
        return 0.0

# ============================================================
# 주문 (재시도 로직 포함)
# ============================================================
def place_order(token: str, symbol: str, side: str, qty: int, price: float,
                max_retries: int = 2) -> dict:
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

    last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{BASE_URL}/uapi/overseas-stock/v1/trading/order",
                headers=headers(token, tr_id),
                json=body,
                timeout=15,
            )
            
            # 500 에러 시 재시도
            if resp.status_code == 500:
                last_error = f"500 Internal Server Error (attempt {attempt+1})"
                print(f"    → KIS 500 에러, {3*(attempt+1)}초 후 재시도...")
                time.sleep(3 * (attempt + 1))
                continue
            
            resp.raise_for_status()
            result = resp.json()
            
            # 장종료 메시지 감지
            msg1 = result.get("msg1", "")
            rt_cd = result.get("rt_cd", "")
            if "장종료" in msg1 or "장마감" in msg1:
                result["_market_closed"] = True
                
            return result
            
        except requests.exceptions.HTTPError as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                time.sleep(3 * (attempt + 1))
        except Exception as e:
            last_error = str(e)
            break

    return {"rt_cd": "ERROR", "msg1": last_error or "Unknown error", "_retries_exhausted": True}

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
def calc_orders(signal: dict, holdings: dict, total_krw: float, prices: dict, krw_usd: float) -> list:
    """
    목표비중 vs 현재비중 비교 → 주문 리스트 반환
    total_krw 기반으로 수량 계산
    """
    if total_krw <= 0:
        print("잔고 없음 (KRW 0) — 주문 스킵")
        return []

    total_usd = total_krw / krw_usd
    
    # 모의투자 레버리지 방지: 비중 합계를 95%로 캡 (증거금 여유분)
    raw_spy = min(signal["w_spy"], 1.0)
    raw_tlt = min(signal["w_tlt"], 1.0)
    total_w = raw_spy + raw_tlt
    if total_w > 0.95:
        scale = 0.95 / total_w
        raw_spy *= scale
        raw_tlt *= scale
    
    targets = {
        "SPY": raw_spy,
        "TLT": raw_tlt,
    }

    orders = []

    for sym, target_w in targets.items():
        price = prices.get(sym, 0)
        if price <= 0:
            continue

        current_qty  = holdings.get(sym, {}).get("qty", 0)
        current_val  = current_qty * price
        current_w    = current_val / total_usd if total_usd > 0 else 0

        target_val_usd = total_usd * target_w
        target_qty     = int(target_val_usd / price)
        diff_w         = target_w - current_w

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
# Insight: Gemini Market Rationale
# ============================================================
def get_market_insight(signal: dict) -> str:
    """Gemini를 사용하여 현재 시그널에 대한 시장 인사이트 생성"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return ""

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-flash-latest")
        
        prompt = f"""
        당신은 전문 퀀트 투자 분석가입니다. 아래의 시장 지표와 오늘 발생한 시그널을 바탕으로, 
        왜 이러한 포트폴리오 비중이 결정되었는지 투자자에게 친절하고 전문적으로 설명해주세요.
        
        [시장 지표]
        - 날짜: {signal['date']}
        - SPY 실현 변동성 (20일): {signal['realized_vol']*100:.2f}%
        - SPY-TLT 상관관계 (60일): {signal['corr']:.3f}
        - 현재 낙폭 (Drawdown): {signal['drawdown']*100:.2f}%
        
        [오늘의 목표 비중]
        - SPY (주식): {signal['w_spy']*100:.1f}%
        - TLT (채권): {signal['w_tlt']*100:.1f}%
        - CASH (현금): {signal['w_cash']*100:.1f}%
        
        [참고: 전략 로직]
        1. 변동성 타겟팅: 변동성이 낮을수록 주식 비중 확대, 높을수록 축소 (Target Vol 15%).
        2. 상관관계 필터: 상관관계가 0.2보다 높으면 채권의 분산 효과가 없다고 보고 채권 비중을 0%로 만들고 현금화.
        3. 낙폭 제어: 낙폭이 -12%를 넘어가면 안전을 위해 전체 노출도를 50%로 축소.
        
        위 데이터를 바탕으로 오늘 매수/매도/유지 결정의 핵심 이유를 3문장 내외로 요약해서 한국어로 알려주세요.
        결과에 "오늘의 인사이트:" 라는 제목을 붙여주세요.
        """
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"  [WARN] Gemini insight error: {e}")
        return ""


# ============================================================
# Telegram
# ============================================================
SNAPSHOT_PATH = Path.home() / "georisk/kis_snapshot.json"

def save_snapshot(holdings: dict, account: dict, prices: dict, signal: dict, krw_usd: float):
    """KIS 실잔고 스냅샷을 kis_snapshot.json에 저장"""
    total_krw = account.get("total_krw", 0)
    total_usd = total_krw / krw_usd if krw_usd else 0

    snap = {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_krw": round(total_krw),
        "total_usd": round(total_usd, 2),
        "krw_usd": round(krw_usd, 2),
        "cash_usd": round(account.get("cash_usd", 0), 2),
        "ord_psbl_krw": round(account.get("ord_psbl_krw", 0)),
        "signal": {
            "w_spy": signal.get("w_spy", 0),
            "w_tlt": signal.get("w_tlt", 0),
            "w_cash": signal.get("w_cash", 0),
            "regime": signal.get("regime", "?"),
        },
        "holdings": {},
    }

    for sym, info in holdings.items():
        qty = info.get("qty", 0)
        price = prices.get(sym, info.get("price", 0))
        avg_p = info.get("avg_price", 0)
        profit_rt = info.get("profit_rt", 0)
        value_usd = qty * price
        snap["holdings"][sym] = {
            "qty": qty,
            "price": round(price, 2),
            "avg_price": round(avg_p, 2),
            "value_usd": round(value_usd, 2),
            "profit_rt": round(profit_rt, 4),
        }

    # 히스토리에 누적 저장
    history = []
    if SNAPSHOT_PATH.exists():
        try:
            with open(SNAPSHOT_PATH) as f:
                history = json.load(f)
            if not isinstance(history, list):
                history = [history]
        except Exception:
            history = []

    # 같은 날짜면 덮어쓰기
    history = [h for h in history if h.get("date") != snap["date"]]
    history.append(snap)
    history = history[-90:]  # 최대 90일 보관

    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"  📸 스냅샷 저장: {SNAPSHOT_PATH} (총 {len(history)}일)")


def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

# ============================================================
# 메인
# ============================================================
def main(dry_run: bool = False):
    print(f"\n{'='*50}")
    print(f"  KIS Trader {'[DRY RUN]' if dry_run else '[LIVE]'} — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Market: {get_market_status_str()}")
    print(f"{'='*50}")

    market_open = is_us_market_open()

    # 1. 토큰 & 환율
    print("토큰 및 환율 조회 중...")
    token = get_token()
    krw_usd = get_krw_usd()
    print(f"  OK (환율: {krw_usd:,.2f})")

    # 2. 시그널
    print("시그널 계산 중...")
    signal = get_signal()
    if signal is None:
        print("  ❌ 시그널 생성 실패 — 데이터 부족")
        send_telegram("⚠️ GeoRisk 시그널 생성 실패")
        return
    print(f"  SPY {signal['w_spy']*100:.1f}% / TLT {signal['w_tlt']*100:.1f}% / CASH {signal['w_cash']*100:.1f}%")

    # 2-1. 인사이트 생성 (제미나이)
    print("시장 인사이트 생성 중...")
    insight = get_market_insight(signal)

    # 3. 잔고 조회
    print("잔고 조회 중...")
    holdings = get_holdings(token)
    account = get_account_summary(token)
    total_krw = account["total_krw"]
    
    # 4. 현재가 및 등락폭 (yfinance)
    prices = {}
    changes = {}
    for sym in ["SPY", "TLT"]:
        try:
            ticker = yf.Ticker(sym)
            fast = ticker.fast_info
            prices[sym] = float(fast["last_price"])
            prev_close = float(fast["previous_close"])
            changes[sym] = ((prices[sym] / prev_close) - 1) * 100
            print(f"  {sym} 현재가: ${prices[sym]:.2f} ({changes[sym]:+.2f}%)")
        except:
            prices[sym] = get_current_price(sym)
            changes[sym] = 0.0
            print(f"  {sym} 현재가: ${prices[sym]:.2f}")

    # 5. 주문 계산
    print("\n주문 계산 중...")
    if dry_run and total_krw == 0:
        print("  [DRY RUN] 잔고 없음 → 가상 15,000,000 KRW 기준 시뮬레이션")
        total_krw = 15000000.0
    
    print(f"  총 자산(KRW): {total_krw:,.0f}원")
    print(f"  총 자산(USD): ${total_krw/krw_usd:,.2f}")
    
    holdings_str_list = []
    for sym, info in holdings.items():
        h_line = f"  {sym}: {info['qty']:.0f}주 × ${info['price']:.2f} (수익률: {info['profit_rt']:+.2f}%)"
        print(h_line)
        holdings_str_list.append(f"• {sym}: {info['qty']:.0f}주 (${info['price']:.2f}, {info['profit_rt']:+.2f}%)")

    orders = calc_orders(signal, holdings, total_krw, prices, krw_usd)

    if not orders:
        msg = (
            f"📊 GeoRisk Report | {signal['date']}\n\n"
            f"💰 총 자산: {total_krw/10000:,.0f}만원\n"
            f"📈 SPY: ${prices['SPY']:.2f} ({changes['SPY']:+.2f}%)\n"
            f"📉 TLT: ${prices['TLT']:.2f} ({changes['TLT']:+.2f}%)\n\n"
            f"현재 잔고:\n" + ("\n".join(holdings_str_list) if holdings_str_list else "• 보유 종목 없음") + "\n\n"
            f"💡 인사이트:\n{insight if insight else '인사이트 생성 중...'}\n\n"
            f"✨ 리밸런싱 불필요 — HOLD"
        )
        print("  리밸런싱 불필요")
        send_telegram(msg)
        print("\n잔고 스냅샷 저장 중...")
        save_snapshot(holdings, account, prices, signal, krw_usd)
        return

    # 6. 장 상태 체크 (LIVE 모드)
    # ... (생략된 기존 코드 유지) ...
    if not dry_run and not market_open:
        # ... (생략된 기존 코드 유지) ...
        tg_msg = (
            f"⏳ GeoRisk 대기 주문 | {signal['date']}\n\n"
            f"💰 총 자산: {total_krw/10000:,.0f}만원\n"
            f"현재 잔고:\n" + ("\n".join(holdings_str_list) if holdings_str_list else "• 보유 종목 없음") + "\n\n"
            f"💡 인사이트:\n{insight if insight else '인사이트 생성 중...'}\n\n"
            f"미국 장 닫힘 — 다음 장 개시 시 실행 예정\n\n"
            + "\n".join(f"⏳ {o['side'].upper()} {o['symbol']} {o['qty']}주" for o in orders)
        )
        send_telegram(tg_msg)
        return

    # 7. 주문 실행
    results = []
    # ... (생략된 기존 주문 실행 코드 유지) ...
    for o in orders:
        if o["side"] == "buy" and not dry_run:
            psamount = get_psamount(token, o["symbol"], o["price"])
            if psamount == 0:
                print(f"  [INFO] {o['symbol']} psamount=0 (장 마감 시간대 가능성) — 수량 {o['qty']}주 유지")
            elif psamount > 0 and psamount < o["qty"]:
                print(f"  [ADJUST] {o['symbol']} 수량 축소: {o['qty']} → {psamount} (주문가능수량 부족)")
                o["qty"] = psamount
            elif psamount < 0:
                print(f"  [WARN] {o['symbol']} psamount 조회 실패 — 수량 {o['qty']}주로 주문 시도")

        if o["qty"] <= 0:
            print(f"  {o['symbol']} 주문 스킵 (수량 0)")
            continue

        action = f"  {'[DRY]' if dry_run else ''} {o['side'].upper()} {o['symbol']} {o['qty']}주 @ ${o['price']:.2f}"
        action += f"  ({o['current_w']*100:.1f}% → {o['target_w']*100:.1f}%)"
        print(action)

        if not dry_run:
            result = place_order(token, o["symbol"], o["side"], o["qty"], o["price"])
            status = result.get("rt_cd", "?")
            msg_code = result.get("msg1", "")
            
            if result.get("_market_closed"):
                print(f"    → ❌ 장 종료: {msg_code}")
            elif result.get("_retries_exhausted"):
                print(f"    → ❌ 재시도 소진: {msg_code}")
            elif status == "0":
                print(f"    → ✅ 주문 성공: {msg_code}")
            else:
                print(f"    → ⚠️ rt_cd={status} {msg_code}")
                
            results.append({
                "symbol": o["symbol"], "side": o["side"],
                "qty": o["qty"], "status": status, "msg": msg_code
            })
            time.sleep(0.5)
        else:
            results.append(o)

    # 8. Telegram
    order_lines = "\n".join(
        f"{'✅' if r.get('status')=='0' or dry_run else '⚠️'} {r.get('side','?').upper()} {r.get('symbol','?')} {r.get('qty',0)}주"
        for r in results
    )
    tg_msg = (
        f"📊 GeoRisk {'DRY RUN' if dry_run else '주문 완료'} | {signal['date']}\n\n"
        f"💰 총 자산: {total_krw/10000:,.0f}만원\n"
        f"📈 SPY: ${prices['SPY']:.2f} ({changes['SPY']:+.2f}%)\n"
        f"📉 TLT: ${prices['TLT']:.2f} ({changes['TLT']:+.2f}%)\n\n"
        f"현재 잔고:\n" + ("\n".join(holdings_str_list) if holdings_str_list else "• 보유 종목 없음") + "\n\n"
        f"💡 인사이트:\n{insight if insight else '인사이트 생성 중...'}\n\n"
        f"주문 내역:\n{order_lines}"
    )
    print("\n" + tg_msg)
    send_telegram(tg_msg)

    # 실잔고 스냅샷 저장
    print("\n잔고 스냅샷 저장 중...")
    save_snapshot(holdings, account, prices, signal, krw_usd)
    print(f"\n{'='*50}")


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)

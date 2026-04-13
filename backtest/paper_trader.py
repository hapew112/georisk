import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from data_fetcher import fetch_all
from signals import compute_signals

LOG_PATH = os.path.expanduser("~/georisk/paper_log.json")

# ── Realistic cost model ───────────────────────────────────────────────────
FEE_TRADE_RATE = 0.001              # 0.1% per side (매수/매도 각각)
FEE_FX_RATE    = 0.002              # 0.2% KRW↔USD 환전 스프레드
DIV_DAILY_SPY  = 0.013 * 0.15 / 252  # SPY ~1.3%/yr, 15% 원천징수 → 일별
DIV_DAILY_TLT  = 0.035 * 0.15 / 252  # TLT ~3.5%/yr, 15% 원천징수 → 일별
CGT_EXEMPT_USD = 1900               # ≈ 250만원 연간 양도소득세 기본공제
CGT_RATE       = 0.22               # 22% 양도소득세율
# ──────────────────────────────────────────────────────────────────────────


def get_us_date():
    """
    9:00 AM KST = 이전날 8:00 PM EDT.
    FORCE_DATE 환경변수로 특정 날짜 강제 지정 가능 (테스트용).
    """
    force_date = os.environ.get("FORCE_DATE")
    if force_date:
        return pd.to_datetime(force_date).date()
    return (datetime.now(timezone.utc) - timedelta(hours=7)).date()


def main():
    today = get_us_date()
    current_year = today.year

    try:
        data = fetch_all(period="3y")
    except Exception as e:
        print(f"Error fetching data: {e}")
        return

    signals = compute_signals(data)
    if signals.empty:
        print("No signals generated.")
        return

    signals['date'] = pd.to_datetime(signals['date']).dt.date

    today_signals = signals[signals['date'] == today]
    if today_signals.empty:
        print("Market closed. Skipping.")
        return

    today_row = today_signals.iloc[-1]
    regime = today_row['regime']
    action = today_row['action']

    # ── Load history ───────────────────────────────────────────────────────
    history = []
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, 'r') as f:
                history = json.load(f)
        except Exception:
            history = []

    if not history:
        yesterday_val          = 10000.0
        yesterday_bench        = 10000.0
        yesterday_spy_w        = 1.0
        yesterday_tlt_w        = 0.0
        yesterday_cash_w       = 0.0
        yesterday_regime       = None
        this_year_start_value  = 10000.0
        is_first_run           = True
    else:
        last_entry = history[-1]
        if last_entry['date'] == str(today):
            print(f"Already processed {today}. Skipping.")
            return

        yesterday_val          = last_entry['portfolio_value']
        yesterday_bench        = last_entry['benchmark_value']
        yesterday_spy_w        = last_entry['spy_weight']
        yesterday_tlt_w        = last_entry['tlt_weight']
        yesterday_cash_w       = last_entry['cash_weight']
        yesterday_regime       = last_entry['regime']
        this_year_start_value  = last_entry.get('this_year_start_value', 10000.0)
        is_first_run           = False

    # ── Market returns ─────────────────────────────────────────────────────
    spy_today = today_row['spy_close']
    today_idx = today_signals.index[-1]

    if today_idx == 0:
        spy_ret = 0.0
        tlt_ret = 0.0
    else:
        prev_row = signals.iloc[today_idx - 1]
        spy_prev = prev_row['spy_close']
        spy_ret  = (spy_today / spy_prev) - 1

        tlt_ret = 0.0
        if "TLT" in data and not data["TLT"].empty:
            tlt_df = data["TLT"].copy()
            tlt_df.index = pd.to_datetime(tlt_df.index).date
            prev_date = prev_row['date']
            if today in tlt_df.index and prev_date in tlt_df.index:
                tlt_prev_price = tlt_df.loc[prev_date, 'Close']
                if tlt_prev_price != 0:
                    tlt_ret = (tlt_df.loc[today, 'Close'] / tlt_prev_price) - 1

    if is_first_run:
        portfolio_return = 0.0
        new_value        = 10000.0
        new_bench        = 10000.0
    else:
        portfolio_return = (yesterday_spy_w * spy_ret) + (yesterday_tlt_w * tlt_ret)
        new_value        = yesterday_val * (1 + portfolio_return)
        new_bench        = yesterday_bench * (1 + spy_ret)

    # ── Year-end: 양도소득세 정산 ────────────────────────────────────────
    cgt_applied = 0.0
    if not is_first_run and current_year > int(history[-1]['date'][:4]):
        gain = yesterday_val - this_year_start_value
        if gain > CGT_EXEMPT_USD:
            cgt_applied = (gain - CGT_EXEMPT_USD) * CGT_RATE
            new_value  -= cgt_applied
            print(f"[양도소득세] ${cgt_applied:,.2f} 차감 (차익 ${gain:,.2f} 중 ${CGT_EXEMPT_USD} 공제)")
        this_year_start_value = new_value

    # ── Next allocation ────────────────────────────────────────────────────
    alloc  = config.PORTFOLIO_ALLOCATIONS.get(regime, config.PORTFOLIO_ALLOCATIONS["NORMAL"])
    spy_w  = alloc.get('SPY', 0.0)
    tlt_w  = alloc.get('TLT', 0.0)
    cash_w = alloc.get('cash', 0.0)

    # ── Rebalancing: 거래세 + 환전 스프레드 ─────────────────────────────
    regime_changed = (not is_first_run) and yesterday_regime is not None and regime != yesterday_regime
    rebalanced     = is_first_run or regime_changed

    trade_fee = 0.0
    fx_fee    = 0.0

    if rebalanced:
        if is_first_run:
            # 최초 매수: SPY 전액
            total_traded = new_value * spy_w
        else:
            # 리밸런싱: 변경분만
            total_traded = (abs(spy_w - yesterday_spy_w) + abs(tlt_w - yesterday_tlt_w)) * new_value

        trade_fee  = total_traded * FEE_TRADE_RATE
        fx_fee     = total_traded * FEE_FX_RATE
        new_value -= (trade_fee + fx_fee)

    # ── 배당 원천징수 (매일 발생) ────────────────────────────────────────
    div_cost = 0.0
    if not is_first_run:
        div_cost   = (yesterday_spy_w * DIV_DAILY_SPY + yesterday_tlt_w * DIV_DAILY_TLT) * new_value
        new_value -= div_cost

    total_fee = trade_fee + fx_fee + div_cost + cgt_applied

    # ── Save entry ─────────────────────────────────────────────────────────
    entry = {
        "date":                  str(today),
        "regime":                regime,
        "action":                action,
        "spy_weight":            float(spy_w),
        "tlt_weight":            float(tlt_w),
        "cash_weight":           float(cash_w),
        "spy_return_pct":        float(spy_ret * 100),
        "tlt_return_pct":        float(tlt_ret * 100),
        "portfolio_return_pct":  float(portfolio_return * 100),
        "portfolio_value":       round(float(new_value), 2),
        "benchmark_value":       round(float(new_bench), 2),
        "rebalanced":            rebalanced,
        "trade_fee":             round(float(trade_fee), 4),
        "fx_fee":                round(float(fx_fee), 4),
        "div_cost":              round(float(div_cost), 4),
        "cgt_applied":           round(float(cgt_applied), 2),
        "fee_applied":           round(float(total_fee), 4),
        "this_year_start_value": round(float(this_year_start_value), 2),
    }

    history.append(entry)
    with open(LOG_PATH, 'w') as f:
        json.dump(history, f, indent=2)

    # ── Print summary ──────────────────────────────────────────────────────
    print(f"=== GeoRisk Paper Trade: {today} ===")
    print(f"Regime:      {regime}")
    print(f"Action:      {action}")
    print(f"Allocation:  SPY {int(spy_w*100)}% / TLT {int(tlt_w*100)}% / Cash {int(cash_w*100)}%")
    print(f"SPY ret:     {spy_ret*100:+.2f}%")
    print(f"Portfolio:   ${new_value:,.2f} ({portfolio_return*100:+.2f}%)")
    print(f"Benchmark:   ${new_bench:,.2f} ({spy_ret*100:+.2f}%)")
    if rebalanced:
        print(f"거래세:      ${trade_fee:,.4f}  FX 스프레드: ${fx_fee:,.4f}")
    print(f"배당원천징수: ${div_cost:,.6f}/일")
    if cgt_applied > 0:
        print(f"양도소득세:  ${cgt_applied:,.2f}")
    print(f"총 비용:     ${total_fee:,.4f}")
    print("======================================")

    try:
        from telegram_notify import send, daily_summary
        msg = daily_summary(entry, yesterday_regime if not is_first_run else None)
        ok = send(msg)
        if not ok:
            print("[Telegram] 전송 실패 (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 확인)")
    except Exception as e:
        print(f"[Telegram] 오류: {e}")


if __name__ == "__main__":
    main()

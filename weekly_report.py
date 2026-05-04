#!/usr/bin/env python3
"""
주간 GeoRisk 리포트 — Gemini API로 분석 후 텔레그램 발송
매주 일요일 09:00 KST 실행 (cron)
"""
import os
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

LOG_PATH = Path.home() / "georisk/paper_log.json"
SNAPSHOT_PATH = Path.home() / "georisk/kis_snapshot.json"
BACKTEST_DIR = Path.home() / "georisk/backtest/results"


def load_paper_log(weeks=4):
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH) as f:
        data = json.load(f)
    cutoff = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    return [h for h in data if h.get("date", "") >= cutoff]


def load_kis_snapshots(weeks=4):
    if not SNAPSHOT_PATH.exists():
        return []
    with open(SNAPSHOT_PATH) as f:
        data = json.load(f)
    cutoff = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    return [s for s in data if s.get("date", "") >= cutoff]


def load_latest_backtest():
    results = {}
    for period in ["3y", "5y"]:
        files = sorted(BACKTEST_DIR.glob(f"*_{period}_backtest.json"))
        if files:
            with open(files[-1]) as f:
                results[period] = json.load(f)
    return results


def build_kis_summary(snapshots):
    if not snapshots:
        return ""
    lines = ["[KIS 모의투자 실잔고]"]
    first = snapshots[0]
    last = snapshots[-1]

    first_val = first.get("total_krw", 0)
    last_val = last.get("total_krw", 0)
    week_ret = (last_val / first_val - 1) * 100 if first_val else 0

    lines.append(f"- 조회 기준: {last.get('as_of', '?')}")
    lines.append(f"- 총 자산: {last_val/10000:,.0f}만원 (${last.get('total_usd',0):,.0f})")
    lines.append(f"- 주간 변동: {week_ret:+.2f}% ({first.get('date','?')} → {last.get('date','?')})")
    lines.append(f"- 환율: {last.get('krw_usd', 0):,.0f} KRW/USD")

    holdings = last.get("holdings", {})
    if holdings:
        lines.append("- 보유 종목:")
        for sym, info in holdings.items():
            lines.append(
                f"  • {sym}: {info['qty']:.0f}주 @ ${info['price']:.2f} "
                f"(평균 ${info['avg_price']:.2f}, 평가손익 {info['profit_rt']:+.2f}%)"
            )

    sig = last.get("signal", {})
    if sig:
        lines.append(f"- 현재 레짐: {sig.get('regime','?')} | 시그널: SPY {sig.get('w_spy',0)*100:.0f}% / TLT {sig.get('w_tlt',0)*100:.0f}%")

    # 주간 일별 자산 변화
    if len(snapshots) > 1:
        lines.append("- 일별 총자산(만원):"),
        for s in snapshots[-5:]:
            lines.append(f"  {s['date']}: {s.get('total_krw',0)/10000:,.0f}만원")

    return "\n".join(lines)


def build_summary(history, backtests):
    lines = []

    # 이번 주 성과
    if history:
        last = history[-1]
        week = history[-5:] if len(history) >= 5 else history

        # cum_ret 포맷
        if "cum_ret" in last:
            cum = last["cum_ret"]
            week_start_cum = week[0].get("cum_ret", cum)
            week_ret = (cum / week_start_cum - 1) * 100 if week_start_cum else 0
            total_ret = (cum - 1) * 100
            lines.append(f"[페이퍼 트레이딩 현황]")
            lines.append(f"- 이번 주 수익: {week_ret:+.2f}%")
            lines.append(f"- 누적 수익률: {total_ret:+.2f}%")
            lines.append(f"- 현재 비중: SPY {last.get('w_spy',0)*100:.0f}% / TLT {last.get('w_tlt',0)*100:.0f}% / Cash {last.get('w_cash',0)*100:.0f}%")
            lines.append(f"- 변동성: {last.get('realized_vol',0)*100:.1f}% / 드로다운: {last.get('drawdown',0)*100:.2f}%")

        # portfolio_value 포맷
        elif "portfolio_value" in last:
            pv = last["portfolio_value"]
            total_ret = (pv / 10000 - 1) * 100
            week_vals = [h.get("portfolio_value", 10000) for h in week]
            week_ret = (week_vals[-1] / week_vals[0] - 1) * 100 if week_vals[0] else 0
            lines.append(f"[페이퍼 트레이딩 현황]")
            lines.append(f"- 이번 주 수익: {week_ret:+.2f}%")
            lines.append(f"- 누적 수익률: {total_ret:+.2f}%  (${pv:,.0f})")
            lines.append(f"- 최근 레짐: {last.get('regime','?')} / 액션: {last.get('action','?')}")

        lines.append(f"- 기록 기간: {history[0]['date']} ~ {last['date']} ({len(history)}일)")

    # 백테스트 요약
    for period, bt in backtests.items():
        q = bt.get("quality", {})
        lines.append(f"\n[백테스트 {period.upper()}]")
        lines.append(f"- 1일 적중률: {q.get('hit_rate_1d',0)*100:.1f}%")
        lines.append(f"- 5일 평균수익: {q.get('avg_return_5d',0):.3f}%")
        lines.append(f"- 허위경보율: {q.get('false_alarm_rate',0)*100:.1f}%")
        lines.append(f"- Kelly: {bt.get('kelly',0)*100:.1f}%")

    return "\n".join(lines)


def ask_gemini(summary_text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""당신은 퀀트 투자 전문가입니다. 아래 GeoRisk 모의투자 시스템의 주간 성과 데이터를 보고,
한국어로 간결하고 날카로운 주간 리포트를 작성해주세요.
KIS 실잔고 데이터가 있으면 그것을 중심으로, 없으면 시그널 기반 로그를 참고하세요.

형식:
1. 이번 주 핵심 요약 (2~3문장)
2. 성과 평가 (좋은 점 / 우려 사항)
3. 다음 주 주목할 점
4. 전략 제언 한 줄

데이터:
{summary_text}

리포트는 텔레그램 메시지에 맞게 이모지 활용하고 500자 내외로."""

    body = {"contents": [{"parts": [{"text": prompt}]}]}
    r = requests.post(url, json=body, timeout=30)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] 환경변수 없음 — 출력만")
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }, timeout=10)
    if r.ok:
        print("텔레그램 발송 완료")
    else:
        print(f"텔레그램 오류: {r.text}")


def main():
    now = datetime.now(timezone.utc) + timedelta(hours=9)
    week_str = now.strftime("%Y년 %m월 %d일")
    print(f"=== 주간 리포트 생성 ({week_str}) ===")

    history = load_paper_log(weeks=4)
    snapshots = load_kis_snapshots(weeks=4)
    backtests = load_latest_backtest()

    if not history and not snapshots and not backtests:
        print("데이터 없음 — 종료")
        return

    kis_summary = build_kis_summary(snapshots)
    paper_summary = build_summary(history, backtests)
    summary = (kis_summary + "\n\n" + paper_summary).strip() if kis_summary else paper_summary
    print("--- 데이터 요약 ---")
    print(summary)

    if not GEMINI_API_KEY:
        print("[ERROR] GEMINI_API_KEY 없음")
        return

    print("\n--- Gemini 리포트 생성 중 ---")
    report = ask_gemini(summary)

    header = f"📊 *GeoRisk 주간 리포트* — {week_str}\n{'='*30}\n"
    full_msg = header + report

    print("\n--- 최종 리포트 ---")
    print(full_msg)
    send_telegram(full_msg)


if __name__ == "__main__":
    main()

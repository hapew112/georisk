import os
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

REGIME_EMOJI = {
    "CALM":     "🟢",
    "NORMAL":   "🟡",
    "ELEVATED": "🟠",
    "CRISIS":   "🔴",
}


def send(text: str) -> bool:
    """Send a Telegram message. Returns True on success, False on failure."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.json().get("ok", False)
    except Exception:
        return False


def daily_summary(entry: dict, prev_regime: str | None) -> str:
    """Format a paper_log entry into a Telegram message."""
    regime = entry["regime"]
    emoji  = REGIME_EMOJI.get(regime, "⚪")

    change = ""
    if prev_regime and prev_regime != regime:
        prev_emoji = REGIME_EMOJI.get(prev_regime, "⚪")
        change = (
            f"\n⚠️ <b>레짐 변경!</b> "
            f"{prev_emoji}{prev_regime} → {emoji}{regime}"
        )

    crisis_warn = ""
    if regime == "CRISIS":
        crisis_warn = "\n🚨 <b>CRISIS — 포트폴리오 방어 모드 전환</b>"

    alloc = (
        f"SPY {int(entry['spy_weight'] * 100)}% / "
        f"TLT {int(entry['tlt_weight'] * 100)}% / "
        f"Cash {int(entry['cash_weight'] * 100)}%"
    )

    pnl_sign = "📈" if entry["portfolio_return_pct"] >= 0 else "📉"

    fee_line = ""
    if entry.get("rebalanced") and entry.get("fee_applied", 0) > 0:
        fee_line = f"💸 리밸런싱 수수료: ${entry['fee_applied']:,.2f}\n"

    return (
        f"📊 <b>GeoRisk Daily | {entry['date']}</b>"
        f"{change}{crisis_warn}\n\n"
        f"레짐: {emoji} <b>{regime}</b> ({entry['action']})\n"
        f"배분: {alloc}\n\n"
        f"SPY 일간: {entry['spy_return_pct']:+.2f}%\n"
        f"{pnl_sign} 포트폴리오: ${entry['portfolio_value']:,.0f} "
        f"({entry['portfolio_return_pct']:+.2f}%)\n"
        f"벤치마크:  ${entry['benchmark_value']:,.0f} "
        f"({entry['spy_return_pct']:+.2f}%)\n"
        f"{fee_line}"
    )

"""
GeoRisk v2 Final - Volatility Targeting Asset Allocation
=========================================================
JARVIS에서 매일 cron으로 실행.
시그널 계산 → 비중 출력 → 로그 저장 → (선택) Telegram 알림

사용법:
  python3 georisk_v2.py              # 오늘 시그널
  python3 georisk_v2.py --backtest   # 전체 백테스트
"""

import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta

# ============================================================
# 설정
# ============================================================
CONFIG = {
    "target_vol": 0.15,          # 연 15% 변동성 타겟
    "dd_threshold": -0.12,       # -12% drawdown → exposure 50% 축소
    "corr_threshold": 0.2,       # SPY-TLT corr > 0.2 → TLT 제거
    "rebal_filter": 0.05,        # weight 변화 5% 미만 → skip
    "spy_cap": 1.3,              # SPY 최대 비중
    "spy_floor": 0.2,            # SPY 최소 비중
    "lookback_vol": 20,          # 변동성 계산 기간
    "lookback_corr": 60,         # 상관관계 계산 기간
    "fee_rate": 0.00015,         # 편도 수수료
    "log_path": os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_log.json"),
}

# ============================================================
# 데이터 수집
# ============================================================
def fetch_data(period="2y"):
    """yfinance로 SPY, TLT, VIX 데이터 수집"""
    import yfinance as yf
    data = yf.download(['SPY', 'TLT', '^VIX'], period=period)['Close']
    data.columns = ['SPY', 'TLT', 'VIX']
    return data.dropna()

# ============================================================
# 핵심 엔진
# ============================================================
class GeoRiskV2:
    def __init__(self, config=None):
        self.cfg = config or CONFIG

    def compute_signal(self, df):
        """
        입력: SPY, TLT, VIX가 포함된 DataFrame
        출력: 시그널 DataFrame (weight, regime 정보 포함)
        """
        df = df.copy()
        df['SPY_ret'] = df['SPY'].pct_change()
        df['TLT_ret'] = df['TLT'].pct_change()

        # 실현 변동성 (연율화)
        df['realized_vol'] = (
            df['SPY_ret']
            .rolling(self.cfg['lookback_vol'])
            .std() * np.sqrt(252)
        )

        # SPY-TLT 상관관계
        df['corr_60'] = (
            df['SPY_ret']
            .rolling(self.cfg['lookback_corr'])
            .corr(df['TLT_ret'])
        )

        # TLT 변동성 (포트폴리오 vol 계산용)
        df['rv_tlt'] = (
            df['TLT_ret']
            .rolling(self.cfg['lookback_vol'])
            .std() * np.sqrt(252)
        )

        return df

    def run(self, df, mode="live"):
        """
        mode="live": 마지막 날 시그널만 반환
        mode="backtest": 전체 기간 백테스트
        """
        df = self.compute_signal(df)
        tv = self.cfg['target_vol']

        results = []
        prev_w_spy, prev_w_tlt = 1.0, 0.0
        peak, cum = 1.0, 1.0
        start = max(self.cfg['lookback_corr'], self.cfg['lookback_vol']) + 1

        for i in range(start, len(df)):
            rv = df['realized_vol'].iloc[i-1]
            corr = df['corr_60'].iloc[i-1]
            rv_tlt = df['rv_tlt'].iloc[i-1]

            # --- 1) Vol Targeting ---
            if rv <= 0 or np.isnan(rv):
                w_spy, w_tlt = prev_w_spy, prev_w_tlt
            else:
                # --- 2) Correlation filter ---
                if corr > self.cfg['corr_threshold']:
                    # TLT 제거 → CASH
                    w_tlt = 0.0
                    w_spy = np.clip(tv / rv,
                                    self.cfg['spy_floor'],
                                    self.cfg['spy_cap'])
                else:
                    # 정상: 포트폴리오 vol 기반 스케일링
                    raw_spy = np.clip(tv / rv,
                                     self.cfg['spy_floor'], 1.0)
                    remainder = max(0, 1.0 - raw_spy)
                    w_tlt = remainder

                    # 포트폴리오 변동성 계산
                    port_vol = np.sqrt(
                        (raw_spy * rv) ** 2
                        + (w_tlt * rv_tlt) ** 2
                        + 2 * raw_spy * w_tlt * rv * rv_tlt * corr
                    )
                    scale = tv / port_vol if port_vol > 0 else 1.0
                    w_spy = np.clip(raw_spy * scale,
                                    self.cfg['spy_floor'],
                                    self.cfg['spy_cap'])
                    w_tlt = w_tlt * scale

            # --- 3) Drawdown overlay ---
            dd = (cum - peak) / peak if peak > 0 else 0
            if dd < self.cfg['dd_threshold']:
                w_spy *= 0.5
                w_tlt *= 0.5

            # --- 4) Rebalancing filter ---
            turnover = abs(w_spy - prev_w_spy) + abs(w_tlt - prev_w_tlt)
            if turnover < self.cfg['rebal_filter']:
                w_spy, w_tlt = prev_w_spy, prev_w_tlt
                turnover = 0

            # --- 5) 수익 계산 ---
            cost = turnover * self.cfg['fee_rate']
            w_cash = max(0, 1.0 - w_spy - w_tlt)
            ret = (w_spy * df['SPY_ret'].iloc[i]
                   + w_tlt * df['TLT_ret'].iloc[i]
                   - cost)

            cum *= (1 + ret)
            peak = max(peak, cum)

            results.append({
                'date': df.index[i].strftime('%Y-%m-%d'),
                'w_spy': round(w_spy, 4),
                'w_tlt': round(w_tlt, 4),
                'w_cash': round(w_cash, 4),
                'realized_vol': round(rv, 4) if not np.isnan(rv) else 0,
                'corr': round(corr, 4) if not np.isnan(corr) else 0,
                'drawdown': round(dd, 4),
                'daily_ret': round(ret, 6),
                'cum_ret': round(cum, 6),
                'turnover': round(turnover, 4),
            })

            prev_w_spy, prev_w_tlt = w_spy, w_tlt

        if mode == "live":
            return results[-1] if results else None
        return pd.DataFrame(results)

# ============================================================
# 로그 저장
# ============================================================
def save_log(signal, path=None):
    path = path or CONFIG['log_path']
    logs = []
    if os.path.exists(path):
        with open(path, 'r') as f:
            logs = json.load(f)
    logs.append(signal)
    with open(path, 'w') as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)
    return path

# ============================================================
# Telegram 알림 (선택)
# ============================================================
def send_telegram(signal, token=None, chat_id=None):
    """환경변수 TELEGRAM_TOKEN, TELEGRAM_CHAT_ID 설정 필요"""
    token = token or os.environ.get('TELEGRAM_TOKEN')
    chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return

    msg = (
        f"📊 GeoRisk v2 Signal\n"
        f"Date: {signal['date']}\n"
        f"SPY: {signal['w_spy']*100:.1f}%\n"
        f"TLT: {signal['w_tlt']*100:.1f}%\n"
        f"CASH: {signal['w_cash']*100:.1f}%\n"
        f"Vol: {signal['realized_vol']*100:.1f}%\n"
        f"Corr: {signal['corr']:.3f}\n"
        f"DD: {signal['drawdown']*100:.2f}%"
    )

    import urllib.request
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": msg}).encode()
    req = urllib.request.Request(url, data=data,
                                headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Telegram error: {e}")

# ============================================================
# 백테스트 성과 리포트
# ============================================================
def print_report(results_df):
    rets = results_df['daily_ret']
    cum = (1 + rets).cumprod()
    years = len(rets) / 252

    cagr = cum.iloc[-1] ** (1/years) - 1
    vol = rets.std() * np.sqrt(252)
    sharpe = cagr / vol if vol > 0 else 0
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    calmar = cagr / abs(mdd) if mdd != 0 else 0

    print("=" * 50)
    print("GeoRisk v2 Backtest Report")
    print("=" * 50)
    print(f"  Period:    {results_df['date'].iloc[0]} ~ {results_df['date'].iloc[-1]}")
    print(f"  CAGR:      {cagr*100:.2f}%")
    print(f"  Sharpe:    {sharpe:.3f}")
    print(f"  MDD:       {mdd*100:.2f}%")
    print(f"  Calmar:    {calmar:.3f}")
    print(f"  Vol:       {vol*100:.2f}%")
    print(f"  Trades:    {(results_df['turnover'] > 0).sum()}")
    print("=" * 50)

# ============================================================
# 메인
# ============================================================
if __name__ == "__main__":
    import sys

    engine = GeoRiskV2()

    if "--backtest" in sys.argv:
        print("Loading data for backtest...")
        df = fetch_data(period="10y")
        results = engine.run(df, mode="backtest")
        print_report(results)

        results.to_csv("backtest_results.csv", index=False)
        print("Results saved: backtest_results.csv")

    else:
        print("Fetching latest data...")
        df = fetch_data(period="2y")
        signal = engine.run(df, mode="live")

        if signal:
            print(f"\n{'='*40}")
            print(f"  📊 TODAY'S SIGNAL: {signal['date']}")
            print(f"{'='*40}")
            print(f"  SPY:  {signal['w_spy']*100:.1f}%")
            print(f"  TLT:  {signal['w_tlt']*100:.1f}%")
            print(f"  CASH: {signal['w_cash']*100:.1f}%")
            print(f"  Vol:  {signal['realized_vol']*100:.1f}%")
            print(f"  Corr: {signal['corr']:.3f}")
            print(f"  DD:   {signal['drawdown']*100:.2f}%")
            print(f"{'='*40}")

            save_log(signal)
            print(f"Log saved: {CONFIG['log_path']}")

            send_telegram(signal)
        else:
            print("No signal generated. Check data.")

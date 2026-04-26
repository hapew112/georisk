# GeoRisk Terminal

개인 트레이딩용 퀀트 자산배분 + 모의투자 통합 대시보드.
Vol Targeting 기반 SPY/TLT/Cash 동적 배분, 매일 JARVIS에서 자동 실행.

- **목표**: 20M KRW × 20%/yr 복리, 바이앤홀드 대비 MDD 50% 감소
- **환경**: JARVIS (8GB RAM 미니PC, Linux) + Cloudflare Workers + Telegram 알림

---

## 현재 상태 (2026-04-27)

| Phase | 내용 | 상태 |
|-------|------|------|
| Phase 1 — Backtest | 10년 백테스트, 지표 산출, OOS 검증 | ✅ 완료 |
| Phase 2 — Paper Trading | georisk_v2.py, 매일 cron 자동 실행, Telegram 알림 | ✅ 완료 |
| Phase 3 — Dashboard | Cloudflare KV → /api/paper → index.html 위젯 | ✅ 완료 |
| v7 — Signal Upgrade | Kalman Filter VIX 스무딩, VaR/CVaR 지표 추가 | ✅ 완료 |
| **Vol Targeting (v2)** | **실현변동성 기반 연속 배분, OOS gap 0.263 PASS** | ✅ **완료 — 현재 전략** |
| **KIS API 연동** | 한국투자증권 모의투자 API → 자동 주문 | 🔄 **진행 중** |
| ARCH/GARCH 레짐 감지 | 변동성 클러스터링 기반 신호 | ⬜ 예정 |
| HMM 레짐 감지 | hmmlearn 기반 은닉 레짐 | ⬜ 예정 |

---

## 전략 비교 및 채택 근거 (2026-04-27 확정)

### v7 (Kalman VIX 레짐) vs Vol Targeting v2 (10y, 2016-2026)

| 지표 | v7 레짐 | **Vol Targeting v2** | Buy & Hold |
|------|---------|----------------------|------------|
| CAGR | 12.31% | 12.00% | 14.85% |
| Sharpe | 0.896 | **0.955** | 0.826 |
| MDD | -27.69% | **-19.65%** | -33.72% |
| Calmar | 0.445 | **0.643** | 0.440 |
| OOS Sharpe gap | 미측정 | **0.263 ✅ PASS** | — |

### OOS 검증 (IS: 2016-2020 → OOS: 2021-2026)

| | IS Sharpe | OOS Sharpe | Gap |
|--|--|--|--|
| Vol Targeting v2 | 1.131 | 0.800 | **0.263 ✅** |

### 주요 구간 성과

| 구간 | Vol Targeting v2 | v7 | Buy & Hold |
|------|------------------|----|------------|
| 코로나 급락 (2020.2-3) | **-7.73%** | -14.75% | -33.40% |
| 금리 인상 (2022) | **-16.32%** | -21.92% | -18.18% |

**채택 결론:** Vol Targeting v2가 Sharpe, MDD, Calmar, OOS 안정성 모두 우위.
v7 레짐 스위칭은 폐기. v7의 Kalman VIX CRISIS 감지는 향후 overlay로 검토.

---

## 현재 전략 스펙 (georisk_v2.py)

```
핵심: Vol Targeting (target_vol / realized_vol)
자산: SPY / TLT / CASH

파라미터:
  target_vol     = 15%       # 연 변동성 타겟
  dd_threshold   = -12%      # drawdown → exposure 50% 축소
  corr_threshold = 0.2       # SPY-TLT 60d corr > 0.2 → TLT binary 제거
  rebal_filter   = 5%        # weight 변화 5% 미만 → skip
  spy_cap        = 130%      # SPY 최대 비중
  spy_floor      = 20%       # SPY 최소 비중
  lookback_vol   = 20d
  lookback_corr  = 60d
  fee_rate       = 0.015%/side
```

---

## 아키텍처

```
JARVIS (로컬, 매일 09:00 KST 자동 실행)
├── georisk_v2.py             # Vol Targeting 전략 엔진 (현재 메인)
├── backtest/
│   ├── data_fetcher.py       # yfinance: SPY, TLT, VIX, GLD 등
│   ├── signals.py            # Kalman VIX → z-score → 레짐/액션 (v7)
│   ├── paper_trader.py       # 일별 P&L, 4-비용 모델 (v7)
│   ├── paper_summary.py      # 주간 요약 (매주 일요일)
│   ├── publish.py            # → Cloudflare KV 업로드
│   ├── telegram_notify.py    # Telegram Bot 알림
│   ├── metrics.py            # Sharpe, MDD, CAGR, VaR, CVaR, Kelly
│   ├── backtest.py           # 백테스트 엔진
│   └── allocation.py         # Risk Parity 배분 (v7)
├── paper_log.json            # 일별 시그널 로그 (v2 기준)
├── .env_georisk              # secrets (Telegram) — git 제외
├── .georisk_env              # secrets (Telegram + CF) — git 제외
└── index.html                # 대시보드

Cloudflare Workers (georiskdashboard.a01041116626.workers.dev)
├── /api/regime    ← latest_regime KV 키
├── /api/paper     ← paper_summary KV 키
├── /api/news
└── /api/macro
```

---

## Cron 스케줄 (JARVIS)

```
# 평일 09:00 KST — v2 시그널 계산 + 로그 저장 + Telegram 알림
0 9 * * 1-5  TELEGRAM_TOKEN=xxx TELEGRAM_CHAT_ID=yyy /usr/bin/python3 /home/hapew112/georisk/georisk_v2.py >> /home/hapew112/georisk/cron.log 2>&1

# 평일 09:00 KST — v7 paper trading + KV 업로드 (병행 유지)
0 9 * * 1-5  cd ~/georisk/backtest && source ~/.georisk_env && source venv/bin/activate && python paper_trader.py && python publish.py --paper >> ~/georisk/logs/paper_trade.log 2>&1

# 일요일 09:00 KST — 주간 요약
0 9 * * 0    cd ~/georisk/backtest && source ~/.georisk_env && source venv/bin/activate && python paper_summary.py --telegram >> ~/georisk/logs/weekly_summary.log 2>&1
```

---

## Telegram 알림 예시 (georisk_v2.py)

```
📊 GeoRisk v2 Signal
Date: 2026-04-27
SPY: 82.2%
TLT: 0.0%
CASH: 17.8%
Vol: 18.4%
Corr: 0.211
DD: -1.39%
```

---

## 지표 체계

| 지표 | 설명 |
|------|------|
| CAGR | 연간 복리 수익률 |
| MDD | 최대 낙폭 |
| Sharpe | 위험조정 수익률 |
| Calmar | CAGR / MDD |
| OOS Sharpe gap | IS vs OOS Sharpe 차이 (0.3 이하 = PASS) |
| VaR 95% | 하루 최대 손실 (5% 확률) |
| CVaR 95% | VaR 초과 시 평균 손실 |

---

## 업그레이드 큐

| 우선순위 | 항목 | 상태 |
|---------|------|------|
| 1 | KIS API 모의투자 연동 (해외주식 자동 주문) | 🔄 진행 중 |
| 2 | 주간 리뷰 자동화 (paper_log → 성과 분석 → Telegram) | ⬜ 예정 |
| 3 | v7 Kalman CRISIS overlay 추가 (v2 위에 얹기) | ⬜ 검토 |
| 4 | ARCH/GARCH 변동성 레짐 감지 | ⬜ 예정 |
| 5 | HMM 레짐 감지 | ⬜ 예정 |

---

## 설치 및 실행

```bash
# 1. 환경 설정
git clone https://github.com/hapew112/georisk
cd georisk
pip3 install yfinance pandas numpy --break-system-packages

# 2. 오늘 시그널 확인
python3 georisk_v2.py

# 3. 백테스트 (10년)
python3 georisk_v2.py --backtest

# 4. Telegram 설정
export TELEGRAM_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

# GeoRisk Terminal

개인 트레이딩용 지정학 리스크 모니터링 + 퀀트 백테스트 + 모의투자 통합 대시보드.  
VIX 기반 레짐 감지 신호로 SPY/TLT/Cash 동적 배분, 매일 JARVIS에서 자동 실행.

- **목표**: 20M KRW × 20%/yr 복리, 바이앤홀드 대비 MDD 50% 감소
- **환경**: JARVIS (8GB RAM 미니PC, Linux) + Cloudflare Workers + Telegram 알림

---

## 현재 상태 (2026-04-13)

| Phase | 내용 | 상태 |
|-------|------|------|
| Phase 1 — Backtest | VIX z-score 신호, 10년 백테스트, 지표 산출 | ✅ 완료 |
| Phase 2 — Paper Trading | 현실적 비용 모델, 매일 자동 실행, Telegram 알림 | ✅ 완료 |
| Phase 3 — Dashboard | Cloudflare KV → /api/paper → index.html 위젯 | ✅ 완료 |
| v7 — Signal Upgrade | Kalman Filter VIX 스무딩, VaR/CVaR 지표 추가 | ✅ 완료 |
| v8 — Risk Parity | 동적 변동성 기반 자산 배분 (Risk Parity) | 🔄 진행 중 |

---

## Backtest Results (10y, 2016-2026, post bug-fix)

### Walk-Forward Validation (v7 Fixed)
| Period | CAGR | MDD | Sharpe |
|--------|------|-----|--------|
| In-sample 2016-2021 | 27.7% | -13.3% | 2.00 |
| Out-of-sample 2022-2026 | 17.3% | -16.5% | 0.95 |

### v7 vs v8 (10y full period)
| Method | CAGR | MDD | Sharpe |
|--------|------|-----|--------|
| v7 Fixed (SPY regime-based) | 23.7% | -16.5% | 1.52 |
| v8 Hybrid RP (SPY+TLT+GLD) | 27.4% | -18.1% | 1.99 |
| Buy & Hold SPY | ~14% | ~-34% | ~0.65 |

Note: v8 shows higher CAGR but worse MDD than v7 in long-term.
v7 is the primary strategy. v8 remains experimental.

Walk-forward verdict: CONDITIONAL PASS
- Out-of-sample Sharpe 0.95 (above 0.8 threshold)
- 2022-2026 was historically difficult (worst bond crash + rate hikes)
- Next gate: 30-day paper trading results (target: monthly return > 0.8%)

---

## 아키텍처

```
JARVIS (로컬, 매일 09:00 KST 자동 실행)
├── backtest/
│   ├── data_fetcher.py       # yfinance: SPY, TLT, VIX, GLD 등
│   ├── signals.py            # Kalman VIX → z-score → 레짐/액션
│   ├── paper_trader.py       # 일별 P&L, 4-비용 모델
│   ├── paper_summary.py      # 주간 요약 (매주 일요일)
│   ├── publish.py            # → Cloudflare KV 업로드
│   ├── telegram_notify.py    # Telegram Bot 알림
│   ├── metrics.py            # Sharpe, MDD, CAGR, VaR, CVaR, Kelly
│   ├── backtest.py           # 백테스트 엔진
│   └── alt_signals.py        # A/B/C 신호 비교
├── paper_log.json            # 일별 거래 로그
├── .georisk_env              # secrets (Telegram + CF) — git 제외
└── index.html                # 대시보드 (Portfolio 탭: 레짐 위젯 + Paper 위젯)

Cloudflare Workers (georiskdashboard.a01041116626.workers.dev)
├── /api/regime    ← latest_regime KV 키
├── /api/paper     ← paper_summary KV 키
├── /api/news
└── /api/macro
```

---

## 신호: VIX Kalman + Z-Score (현재 버전)

```
1. Kalman Filter로 VIX 일별 노이즈 스무딩 (std 4.9 → 1.8)
2. 스무딩된 VIX의 20일 이동평균/표준편차로 z-score 계산
3. z-score > 2.0 → DEFENSIVE 액션
4. VIX 절대값으로 레짐 분류:
   - CALM     (VIX < 15)  → SPY 100%
   - NORMAL   (15~20)     → SPY 100%
   - ELEVATED (20~28)     → SPY 70% / TLT 30%
   - CRISIS   (28+)       → SPY 40% / TLT 40% / Cash 20%
```

### 신호 변천사

| 버전 | 방식 | Kelly | Sharpe | 결과 |
|------|------|-------|--------|------|
| v1 | 5-지표 스트레스 스코어 | -1.0 | — | Edge 없음, 폐기 |
| v2 | VIX z-score | 0.25 | 2.04~2.23 | 채택 |
| v7 | Kalman + z-score | 0.18 | 1.88 | 채택 |
| v8 | Risk Parity Allocation | -1.0 | 0.51 | 진행 중 |

---

## 비용 모델 (paper_trader.py)

4가지 실제 비용을 시뮬레이션:

| 비용 항목 | 요율 | 발생 시점 |
|----------|------|----------|
| 거래수수료 | 0.015%/side (키움 실제 요율) | 레짐 변경 시 리밸런싱 |
| FX 스프레드 | 0.2% | 리밸런싱 시 |
| 배당 원천징수 | SPY 0.00077%/일, TLT 0.00208%/일 | 매일 |
| 양도소득세 | 22% (연간 $1,900 공제 후) | 연말 정산 |

---

## Cron 스케줄 (JARVIS)

```
# 평일 09:00 KST — 모의투자 실행 + KV 업로드
0 0 * * 1-5  source ~/.georisk_env && python paper_trader.py && python publish.py --paper

# 일요일 09:00 KST — 주간 요약 리포트
0 0 * * 0    source ~/.georisk_env && python paper_summary.py --telegram
```

---

## Telegram 알림 예시

**일별 (paper_trader.py)**
```
📊 GeoRisk Daily | 2026-04-13
레짐: 🟡 NORMAL (HOLD)
배분: SPY 100% / TLT 0% / Cash 0%
SPY 일간: +0.42%
📈 포트폴리오: $10,423 (+0.42%)
벤치마크:  $10,398 (+0.42%)
```

**주간 (paper_summary.py)**
```
📊 GeoRisk 주간 리포트 | 2026-W15
기간: 2026-04-07 ~ 2026-04-13 (5거래일)
포트폴리오: $10,423 (+2.1%)  벤치마크: $10,312 (+1.1%)
알파: +1.0%p  누적 수수료: $0.87
현재 레짐: 🟡 NORMAL
```

---

## 지표 체계 (metrics.py)

| 지표 | 설명 | 사용처 |
|------|------|--------|
| CAGR | 연간 복리 수익률 | backtest.py |
| MDD | 최대 낙폭 | backtest.py |
| Sharpe | 위험조정 수익률 (rf=4.5%) | backtest.py |
| Calmar | CAGR / MDD | backtest.py |
| Kelly | 최적 베팅 비율 | backtest.py |
| VaR 95% | 하루 최대 손실 (5% 확률) | metrics.py ← **v7 신규** |
| CVaR 95% | VaR 초과 시 평균 손실 | metrics.py ← **v7 신규** |

---

## v7/v8 업그레이드 큐 (Quantopian 기반)

Quantopian GitHub (github.com/quantopian/research_public) 검증된 내용:

| 우선순위 | 항목 | 출처 | 상태 |
|---------|------|------|------|
| 1 | Kalman Filter VIX 스무딩 | Quantopian/Kalman_Filters | ✅ 완료 |
| 2 | VaR/CVaR 리스크 지표 | Quantopian/VaR_and_CVaR | ✅ 완료 |
| 3 | ARCH/GARCH 변동성 레짐 감지 | Quantopian/ARCH_GARCH_and_GMM | ⬜ 예정 |
| 4 | Market Impact Model 수수료 | Quantopian/Market_Impact_Model | ⬜ 예정 |
| 5 | HMM 레짐 감지 | hmmlearn 라이브러리 | ⬜ 예정 |
| 6 | Risk Parity 배분 | scipy 기반 직접 구현 | ✅ 완료 |

> ⚠️ Perplexity가 HMM/Risk Parity/Vol Targeting이 Quantopian에 있다고 hallucination. 실제로 없음. 별도 구현 필요.

---

## 설치 및 실행

```bash
# 1. 환경 설정
git clone https://github.com/hapew112/georisk
cd georisk/backtest
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. .georisk_env 작성 (git 제외)
cp .georisk_env.example .georisk_env
# TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CF_ACCOUNT_ID 등 입력

# 3. 백테스트 실행
python backtest.py

# 4. 모의투자 (수동 테스트)
source ../.georisk_env
FORCE_DATE=2026-04-10 python paper_trader.py

# 5. Cloudflare KV 업로드
python publish.py --paper
```

---

## 환경변수 (.georisk_env)



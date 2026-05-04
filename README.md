# GeoRisk Terminal

개인 퀀트 자산배분 + 모의투자 통합 대시보드.
Vol Targeting 기반 SPY/TLT/Cash 동적 배분, JARVIS에서 매일 자동 실행.

- **목표**: 바이앤홀드 대비 MDD 50% 감소, Sharpe 개선
- **환경**: JARVIS (미니PC, Linux) + Cloudflare Workers + Telegram + KIS 모의투자

**라이브 대시보드**: https://georiskdashboard.a01041116626.workers.dev

---

## 현재 상태 (2026-05-04)

| Phase | 내용 | 상태 |
|-------|------|------|
| Backtest | 5년 백테스트, OOS 검증 (Sharpe gap 0.263 PASS) | ✅ |
| Vol Targeting v2 | 실현변동성 기반 연속 배분 — 현재 메인 전략 | ✅ |
| Dashboard | Cloudflare Workers 2-worker 아키텍처 | ✅ |
| KIS API | 모의투자 자동 주문, 실잔고 스냅샷 | ✅ |
| Weekly Report | Gemini 2.5 Flash 주간 분석 → Telegram | ✅ |
| ARCH/GARCH 레짐 | 변동성 클러스터링 기반 신호 | ⬜ |
| HMM 레짐 감지 | hmmlearn 기반 은닉 레짐 | ⬜ |

---

## 전략 스펙

```
핵심: Vol Targeting (target_vol / realized_vol)
자산: SPY / TLT / CASH

target_vol     = 15%      # 연 변동성 타겟
dd_threshold   = -12%     # drawdown → exposure 50% 축소
corr_threshold = 0.2      # SPY-TLT 60d corr > 0.2 → TLT 제거
rebal_filter   = 5%       # weight 변화 5% 미만 → skip
spy_cap        = 130%
spy_floor      = 20%
lookback_vol   = 20d
lookback_corr  = 60d
```

### 백테스트 결과 (5y, 2021–2026)

| 지표 | Vol Targeting v2 | Buy & Hold |
|------|-----------------|------------|
| Sharpe | **0.955** | 0.826 |
| MDD | **-19.65%** | -33.72% |
| Calmar | **0.643** | 0.440 |

---

## 아키텍처

```
JARVIS (로컬)
├── georisk_v2.py          # 전략 엔진 — 시그널 계산
├── kis_trader.py          # KIS 모의투자 자동 주문 + 잔고 스냅샷
├── weekly_report.py       # Gemini API → 주간 리포트 → Telegram
├── paper_log.json         # 시그널 기반 일별 로그
├── kis_snapshot.json      # KIS 실잔고 스냅샷 (최대 90일)
├── worker.js              # georiskdashboard 워커 (HTML 서빙)
├── wrangler.toml
└── backtest/
    ├── paper_trader.py    # 일별 P&L 기록
    ├── signals.py         # 시그널 계산
    ├── data_fetcher.py    # yfinance 데이터
    ├── metrics.py         # Sharpe, MDD, CAGR 등
    └── backtest.py        # 백테스트 엔진

Cloudflare Workers
├── georisk-proxy          # API 서버 (FINNHUB_KEY, FRED_KEY 보유)
│   ├── /api/macro         # VIX, DXY, Gold, Oil, BTC 등 — Yahoo Finance
│   ├── /api/sectors       # 섹터 ETF 12개
│   ├── /api/heatmap       # 섹터 히트맵
│   ├── /api/chart         # OHLCV 캔들 (Yahoo Finance)
│   ├── /api/credit        # HYG, LQD, TIP
│   ├── /api/putcall       # VIX/SPX 비율
│   ├── /api/yieldcurve    # 2y/10y/30y 수익률
│   ├── /api/feargreed     # CNN Fear & Greed
│   ├── /api/oref          # 이스라엘 공습경보
│   ├── /api/news          # RSS 뉴스
│   └── /api/paper         # 페이퍼 트레이딩 현황
└── georiskdashboard       # HTML 대시보드 서빙
    └── WORKERS_URL → georisk-proxy
```

---

## Cron 스케줄 (KST 기준)

| 시간 | 스크립트 | 역할 |
|------|---------|------|
| 평일 09:00 | `paper_trader.py` | 시그널 계산 + 페이퍼 로그 |
| 평일 23:00 | `georisk_v2.py` | 시그널 + Telegram 알림 |
| 평일 23:40 | `kis_trader.py` | KIS 주문 실행 + 잔고 스냅샷 저장 |
| 일요일 09:00 | `weekly_report.py` | Gemini 주간 분석 → Telegram |

---

## 배포

```bash
# georisk-proxy 또는 georiskdashboard 배포
# ※ backtest/venv/ 때문에 반드시 /tmp/에서 배포
rm -rf /tmp/wrangler_deploy && mkdir /tmp/wrangler_deploy
cp worker.js wrangler.toml /tmp/wrangler_deploy/
cd /tmp/wrangler_deploy && npx wrangler deploy
```

GitHub push → `.github/workflows/deploy.yml` → georiskdashboard 자동 배포

---

## 설치

```bash
git clone https://github.com/hapew112/georisk
cd georisk/backtest
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 오늘 시그널
python3 ../georisk_v2.py

# 드라이런
python3 ../kis_trader.py --dry-run

# 주간 리포트 테스트
python3 ../weekly_report.py
```

환경변수는 `~/.georisk_env` 참고 (git 제외).

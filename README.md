# GeoRisk Terminal

개인 트레이딩용 지정학 리스크 모니터링 대시보드.  
“지정학 이벤트 → 매크로 리스크 → 섹터/자산 → 트레이딩 타이밍”을 한 화면에서 파악하는 툴입니다.

- 구조: 단일 HTML + Cloudflare Workers + JARVIS(미니PC, 8GB RAM) + Raspberry Pi 3B+  
- 현재 상태:  
  - **1차: TA 패널 완료 + 2차: 매크로/국채/리스크 + 3차: 모바일/TradingView/코드 정리 = v6 최종본**  
  - `worker.js`는 이번 업데이트에서 **수정하지 않음**.

---

## 1. 1차: TA 패널 (기초)

이미 개별 README로 작성된 1차 TA 패널을 이 프로젝트에 통합한 상태입니다.

### 포함된 기능

- JS 기반 기술적 지표:
  - SMA, Bollinger, RSI, EMA, MACD, Ichimoku, VWAP, ATR, ADX, StochRSI, Donchian, Supertrend 등.
- **누락 함수 6개 추가**:
  - `calcVWAP`, `calcATR`, `calcADX`, `calcStochRSI`, `calcDonchian`, `calcSupertrend`.
- 모든 계산 함수에 `try-catch` 보호 로직 추가로,  
  - 결측/변이 데이터에 대한 안정성 향상.

---

## 2. 2차 + 3차: v6 최종 버전 (1차 + 2차 + 3차 합본)

현재는 **1차(TA 패널) + 2차(매크로/국채/리스크) + 3차(모바일/TradingView/수정사항)**가 모두 합쳐진 **v6 최종본**입니다.  
`worker.js`는 수정 없음.

### 2‑1. 포함된 주요 수정

- **TA 패널**:
  - 누락 함수 6개 추가 + `try-catch` 보강.

- **매크로/국채/리스크 계측**:
  - 매크로 레이더에서 `Math.random()` 제거 → `/api/macro`에서 실제 시계열 데이터 바인딩.
  - `macroKey` 리스트: 35개 매크로 지표 정상 초기화.
  - `v6fetchReal()` 호출 시 **즉시 Yield Curve 갱신**되도록 처리.

- **TradingView 차트**:
  - SSE: `csi300` → `000300`.
  - TWSE: `taiex` → `TAIEX`로 통일.

- **모바일 패널**:
  - 패널 열 때마다 최신 데이터를 복사하도록 로직 변경.
  - `children.length === 0` 제거.

- **코드 정리 및 검증 (v6)**:
  - `v6tick` 삭제.
  - `v6fetchReal()`에서 모든 핵심 갱신 집중 처리.
  - 수동/자동 테스트 결과:
    - `v6fetchReal ✅`
    - `Math.random in v6 area: 0 ✅`
    - `macroKey: 35개 ✅`
    - `updateYieldCurve in v6fetchReal ✅`
    - `v6tick deleted ✅`
    - `mobile panel children.length === 0 removed ✅`
    - `TradingView fixes (SSE:000300, TWSE:TAIEX) ✅`
    - `TA calc functions (1차 수정) ✅`

### 2‑2. 배포/검증 성공 조건

- 배포 후 SPY가 **≈650달러대**에서 정상 표시되면,  
  - 모든 TA/매크로/모바일/TradingView 패치가 정상적으로 반영된 것으로 간주.

---

## 3. 앞으로 구현할 것: 2026년 3~6개월 로드맵 (구체 작업 리스트)

아래는 **“지금까지 한 것 + 앞으로 할 것”을 섞어서 만든 실전 작업 목록**입니다.

---

### 3‑1. 4‑1단계: 변동성/레짐 전환 예측 PoC (4~8주)

#### 4‑1‑1. JARVIS 서버 환경 준비

- [ ] JARVIS에 Python 3.10 이상 가상 환경(virtualenv 또는 conda) 구성  
- [ ] JARVIS `~/georisk/forecast/` 폴더 생성  
- [ ] `requirements.txt` 작성:  
  - `statsforecast`, `numpy`, `pandas`, `fastapi`, `uvicorn`, `httpx`  
- [ ] `pip install`으로 패키지 설치 및 테스트 실행

#### 4‑1‑2. statsforecast + FastAPI 서버 구현

- [ ] `/georisk/forecast/app.py` 생성:
  - `FastAPI()` 인스턴스 생성  
  - `/forecast/volatility` 엔드포인트:
    - input: `{ticker: string, history: list<dict>}`  
    - output: 예측 분위수 밴드(예: 0.1, 0.5, 0.9 quantile)  
  - `/forecast/regime` 엔드포인트:
    - input: `history`, `window`
    - output: `regime: [prev, current]` (예: low/normal/high)  
- [ ] `/georisk/forecast/forecast.py`:
  - `statsforecast` 불러오기  
  - ARIMA/Theta/ETS 모델 학습 → `predict` 함수 구현  
  - **VIX/ATR 데이터에 대한 PoC만 우선** 적용  
- [ ] 테스트 스크립트 `/georisk/forecast/test.py`:
  - 예시 데이터로 `/forecast/volatility` 호출 → 결과 확인

#### 4‑1‑3. Cloudflare Workers ↔ JARVIS 연동

- [ ] `wrangler.toml`에 `preview` 또는 `production` 인스턴스 준비  
- [ ] `/forecast` 경로를 Workers에서 JARVIS로 프록시:
  - `new Request('http://JARVIS_INTERNAL_IP:8000/forecast/volatility')`  
- [ ] Workers 함수에서 `fetch` 후, JSON 응답을 GeoRisk 프론트로 전달

#### 4‑1‑4. GeoRisk 프론트에서 예측 밴드 오버레이

- [ ] `ui/geoRisk.js` 또는 `geoRisk.chart.js`에:
  - `fetch('./api/forecast/volatility?ticker=VIX')` 호출  
  - 반환된 `quantiles`로 상/하 밴드를 라인/영역으로 그림  
- [ ] 차트 옵션:
  - 예측 구간에는 반투명 색 사용 (예: `rgba(255, 165, 0, 0.2)`)  
- [ ] 레짐 플래그:
  - `regime=high`일 때 차트 배경색/레이어 색상 변경

---

### 3‑2. 4‑2단계: 백테스트 및 가상 포지션 패널 (8~16주)

#### 4‑2‑1. 백테스트 저장 구조 설계

- [ ] `backtests/` 폴더 생성:
  - `YYYY-MM-DD_STRATEGY_RUN001/result.parquet`  
  - `YYYY-MM-DD_STRATEGY_RUN001/meta.json`  
- [ ] `backtests/index.sqlite` 생성:
  - `strategy`, `data_version`, `param_hash`, `result_id`, `created_at` 테이블 정의  
- [ ] Python 백테스트 스크립트 `backtest_runner.py`:
  - 전략 로직 + 데이터 로드 + 결과 저장(Parquet + JSON) + 인덱스 갱신

#### 4‑2‑2. GeoRisk UI 백테스트 패널

- [ ] `ui/backtestPanel.html` 생성:
  - `select`로 전략 선택, `input`으로 시작/종료일, `button`으로 실행  
- [ ] `ui/backtest.js`:
  - `fetch('./api/backtest/run', {strat: 'X', dates: {start, end}})`  
  - `fetch('./api/backtest/list')`로 결과 목록 가져오기  
- [ ] 차트/표에서 주요 지표 표시:
  - Sharpe, IR, CAGR, MDD, VaR 변화, hit rate

#### 4‑2‑3. 가상 포지션 로직

- [ ] `backtest/strategy/volatility_regime.py`:
  - `volatility + regime`에 따라 매매 규칙 정의:
    - 예: `regime=high`일 때 헤징 비율 ↑  
- [ ] 실제 수익/리스크 감소 기여도를 계산해 `meta.json`에 저장

---

### 3‑3. 4‑3단계: 지정학 뉴스/이벤트 파이프라인 (비동시 병렬 가능, 4주~)

#### 4‑3‑1. Raspberry Pi 3B+ 뉴스 수집기

- [ ] RP3B+에 Python 환경 설치  
- [ ] `news_collector.py`:
  - RSS/뉴스 API/크롤링 + `save_to_json`  
- [ ] `cron` 또는 `systemd`로 1시간마다 `v6fetch` 호출:
  - `http://JARVIS:8000/news/update`로 데이터 전달

#### 4‑3‑2. GeoRisk 프론트에서 뉴스 빈도/이상 감지

- [ ] `/api/news/frequency` 엔드포인트 추가:
  - `interval=1h|1d`  
  - `zscore` 계산 반환  
- [ ] 차트 상단에 Z‑Score 2.0 이상이면 경고/색상 표시

---

### 3‑4. 4‑4단계: AI 챗/지식저장소 통합 (비동시, 2~4주)

#### 4‑4‑1. MemRosetta 설정

- [ ] MemRosetta 계정/로컬 저장소 구성  
- [ ] 아래 메모 타입 정의:
  - `design_decisions`: 설계 의사결정, 임계값, 모델 도입/보류 이유  
  - `bugs`: 버그/장애, 원인/해결 방법  
  - `strategy_notes`: 전략/파라미터/실험 노트  
- [ ] 매일 개발/실험 시 해당 메모에 업데이트

#### 4‑4‑2. LLM‑Wiki 구축

- [ ] LLM‑Wiki 폴더/프로젝트 생성:
  - `wikis/georisk/`  
- [ ] 카테고리:
  - `design/`: 설계 철학, 구조, 데이터 흐름  
  - `indicators/`: 각 지표 설명  
  - `strategies/`: 전략/규칙 문서  
  - `research/`: TimesFM, statsforecast, 기타 연구 요약  
- [ ] MemRosetta에서 가치 있는 메모를 매주 `wikis/`로 마이그레이션

---

### 3‑5. 4‑5단계: 외부 API/고급 예측 모델 검토 (16주 이후, 조건부)

#### 4‑5‑1. 검토 전제

- [ ] statsforecast PoC + 백테스트에서  
  - 드로다운 감소, Sharpe 증가, VaR 감소가 **통계적으로 유의**해야 함  
- [ ] 그 결과를 문서로 작성 (내부 보고서)

#### 4‑5‑2. 구체 작업 리스트

- [ ] TimeGEN‑1 API 테스트 계정 가입  
- [ ] `backtest/strategy/timegen_strat.py` 구현:
  - `v6fetch` → `TimeGEN API` → 예측 결과 → 포지션 규칙 적용  
- [ ] ONNX TimesFM 양자화 PoC(S3/GH 등에서 모델 받아서 `onnxruntime`로 추론)  
- [ ] 결과는 `backtests/`에 저장 + `README`에 **“이떄는 무료/저비용/고비용 선택지”** 표로 요약

---

## 4. 앞으로 2026년 3~6개월 간의 주요 마일스톤 (개요)

| 기간 | 마일스톤 | 핵심 작업 |
|------|----------|-----------|
| 4~8주 | 변동성/레짐 PoC | JARVIS 서버 + statsforecast + FastAPI 서버 구축, Workers 프록시, 차트 예측 밴드 오버레이 |
| 8~16주 | 백테스트/가상 포지션 패널 | `backtests/` 구조, `backtest_runner.py`, UI 백테스트 패널, 가상 포지션 규칙 |
| 4~12주 | 지정학 뉴스 파이프라인 | RP3B+ 뉴스 수집기, `/api/news/frequency`, GeoRisk에서 Z‑Score 이상 감지 |
| 2~4주 | AI 챗/지식저장소 | MemRosetta + LLM‑Wiki 통합, 문서화 체계 시작 |
| 16주 이후 | 외부/고급 모델 | TimeGEN API PoC, ONNX TimesFM 실험, 이후 도입/보류 결정 |

---

## 5. 이 README의 역할

이 `README.md`는 다음을 목표로 합니다:

- 나중의 나 또는 다른 개발자가 봤을 때,  
  - “지금까지 1차 + 2차 + 3차가 무엇을 바꿨는지”를 한 번에 파악할 수 있게.
- 향후 2~3년 간의 로드맵을  
  - 지정학 리스크/변동성/레짐 → 백테스트 → 외부 API로  
  단계별로 확인할 수 있게.
- Claude/Gemini 같은 LLM이 이 프로젝트를 이해하고,  
  - 다음 단계 설계/구현/디버그를 바로 보조할 수 있게.

---

## 6. 지금 단계 요약

- 현재는 **v6 최종본(1차 + 2차 + 3차 합본)으로 기능·버그 픽스가 완료된 상태**입니다.  
- `worker.js`는 수정 없음.  
- **앞으로 목표**는  
  - JARVIS에 `statsforecast` + Fast.correct 서버를 올려서  
    - 변동성/레짐 전환 예측 PoC를 만들고,  
    - 그 결과를 GeoRisk UI에 오버레이 + 백테스트 패널 + 가상 포지션 패널로 확장하는 것**입니다.
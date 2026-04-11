# GeoRisk Backtest Engine

> **"Don't predict the market. Detect danger faster than others."**

A quantitative backtest system that measures whether GeoRisk Terminal's
geopolitical + macro stress signals actually predict market drawdowns.

Built for JARVIS (8GB RAM mini-PC). No AI, no ML. Pure data + math.

---

## Goal

| Year | Target | Metric |
|------|--------|--------|
| Year 1 | Cut drawdown in half vs buy-and-hold | MDD: -15% → -8% |
| Year 2 | Risk-adjusted return Sharpe ≥ 1.0 | Annual 15-20% |
| Year 3 | Automated + stable | Annual 20%, Sharpe ≥ 1.2 |

**NOT** "get rich quick." This is compound growth:
- 20M KRW × 20%/yr × 3 years = ~34.5M KRW (+72%)
- Same money with -30% drawdown = years of recovery

---

## Architecture

```
JARVIS (local, offline)
├── data_fetcher.py      # Yahoo Finance → parquet cache
├── signals.py           # Composite stress + VIX regime
├── backtest.py          # Signal → outcome measurement
├── metrics.py           # Sharpe, MDD, Kelly, hit rate
├── config.py            # Thresholds, symbols, params
├── data/cache/          # Auto-created parquet files
├── results/             # JSON output per run
└── requirements.txt
```

No cloud dependency. No GPU. Runs in ~30 seconds on 8GB RAM.

---

## How It Works

### Step 1: Data (data_fetcher.py)

```
Source: yfinance (free, no API key)
Symbols: SPY, ^VIX, DX-Y.NYB, CL=F, ^TNX, GC=F, BTC-USD, ^KS11, TLT
Period: 3 years daily OHLCV
Cache: ./data/cache/{symbol}_3y.parquet
Re-fetch: only if cache > 24h old
```

### Step 2: Signals (signals.py)

Two signal layers:

#### Layer 1: Composite Stress Score (0-5)

Each condition = +1 point per day:

```
VIX spike:      VIX 1-day change > +15%
Dollar surge:   DXY 1-day change > +0.8%  
Oil spike:      WTI 1-day change > +5%
Yield jump:     10Y yield 1-day change > +3%
Gold rush:      Gold 1-day change > +2%
```

#### Layer 2: VIX Regime Classification

```
CALM:      VIX < 15    → full risk-on
NORMAL:    VIX 15-20   → standard allocation
ELEVATED:  VIX 20-28   → reduce risk 30%
CRISIS:    VIX > 28    → reduce risk 60%
```

#### Combined Signal

```
regime = classify_vix(vix_today)
stress = count_stress_conditions(today)

action = HOLD
if stress >= 3:                    action = DEFENSIVE
if stress >= 2 and regime >= ELEVATED: action = DEFENSIVE  
if regime == CRISIS:               action = DEFENSIVE
```

### Step 3: Backtest (backtest.py)

NOT simulating trades. Measuring signal quality:

```
For each day in 3-year dataset:
  1. Compute stress_score + vix_regime
  2. If signal fires (DEFENSIVE):
     - Record: date, score, regime, SPY price
     - Record: SPY at +1d, +3d, +5d, +10d
     - Record: max drawdown in 5d window
  3. Compare signal days vs all days
```

### Step 4: Metrics (metrics.py)

#### Signal Quality Metrics
```
hit_rate_3d:      % of signals where SPY dropped within 3 days
hit_rate_5d:      % of signals where SPY dropped within 5 days
avg_return_3d:    average SPY return 3 days after signal
avg_return_5d:    average SPY return 5 days after signal
avg_drawdown_5d:  average max drawdown in 5-day window after signal
worst_case:       worst single signal outcome
false_alarm_rate: % of signals where SPY went UP
baseline_3d:      average 3-day return on ALL days (no signal)
edge:             signal_avg_return - baseline_avg_return
```

#### Hypothetical Portfolio Metrics
```
Compare two portfolios over 3 years:

Portfolio A (buy & hold):
  - 100% SPY, no changes

Portfolio B (GeoRisk guided):
  - CALM/NORMAL: 100% SPY
  - ELEVATED signal: 70% SPY + 30% TLT
  - CRISIS/stress≥3: 40% SPY + 40% TLT + 20% cash

Metrics for both:
  - Total return (CAGR)
  - Sharpe ratio
  - Maximum drawdown (MDD)
  - Calmar ratio (CAGR / MDD)
  - Monthly win rate
```

#### Kelly Criterion (position sizing reference)
```
kelly_fraction = (win_rate × avg_win - (1 - win_rate) × avg_loss) / avg_win

If kelly > 0.25: cap at 0.25 (never bet more than 25%)
If kelly < 0: signal has no edge, do not trade on it
```

Kelly is informational only in Phase 1. Not used for actual sizing yet.

---

## Output Format

### CLI Output
```
$ python backtest.py

GeoRisk Stress Backtest (2023-04 → 2026-04, 3 years)
═══════════════════════════════════════════════════════

Signal Summary (threshold: stress≥2 + regime≥ELEVATED)
  Signals fired:    23 times
  Hit rate (3d):    69.6%  (16/23 → SPY dropped)
  Hit rate (5d):    65.2%  (15/23)
  Avg return 3d:    -0.95% (baseline: +0.04%)
  Avg drawdown 5d:  -1.82%
  Worst case:       -4.10% (2025-08-05)
  False alarms:     30.4%
  Edge vs baseline: -0.99%

VIX Regime Breakdown
  CALM (VIX<15):     412 days, avg 3d ret: +0.12%
  NORMAL (15-20):    298 days, avg 3d ret: +0.04%
  ELEVATED (20-28):  185 days, avg 3d ret: -0.18%
  CRISIS (28+):       47 days, avg 3d ret: -0.52%

Portfolio Comparison (3 years)
  Buy & Hold:    CAGR 11.2%, Sharpe 0.72, MDD -19.8%
  GeoRisk:       CAGR 10.1%, Sharpe 1.05, MDD -10.2%
  
  Return delta:  -1.1% (slightly less return)
  MDD delta:     -9.6% (HALF the drawdown) ✓
  Sharpe delta:  +0.33 (much better risk-adjusted) ✓

Kelly Criterion
  win_rate: 0.696, avg_win: 1.2%, avg_loss: 0.8%
  kelly_f: 0.22 → recommended max position: 22%
```

### JSON Output
```
results/2026-04-11_stress_vix_regime.json
```

Contains all metrics + individual signal events with dates and outcomes.

---

## Success Criteria

**Phase 1 (backtest) passes if:**
```
hit_rate_3d > 60%
edge_vs_baseline < -0.5%  (signal days are meaningfully worse)
MDD_georisk < MDD_buyhold × 0.6  (40%+ drawdown reduction)
```

**If these fail:** adjust thresholds, add/remove stress components, re-run.

**If these pass:** move to Phase 2 (paper trading with live signals).

---

## What This Does NOT Do

- No price prediction
- No auto-trading
- No leverage (Phase 1)
- No ML/AI models
- No real money
- No "get rich quick"

This measures one thing: **"Does GeoRisk detect danger before it happens?"**

---

## Setup

```bash
# On JARVIS
git clone https://github.com/hapew112/georisk-backtest.git
cd georisk-backtest
pip install -r requirements.txt
python backtest.py
```

## Requirements

```
Python 3.9+
yfinance==0.2.36
pandas==2.2.0
pyarrow==15.0.0
```

RAM usage: ~200MB. No GPU. Runs on JARVIS (8GB) easily.

---

## Roadmap

```
Phase 1 — Signal Quality (now)
  ✓ Design doc
  [x] data_fetcher.py
  [x] signals.py (stress + VIX regime)  
  [x] backtest.py (signal → outcome)
  [x] metrics.py (Sharpe, MDD, Kelly)
  [x] First run + results analysis

Phase 2 — Paper Trading (after Phase 1 passes)
  □ Live signal generator (daily cron on JARVIS)
  □ Telegram/Discord push notifications
  □ 30-day paper trading log
  □ Compare paper vs backtest metrics

Phase 3 — GeoRisk UI Integration
  □ FastAPI wrapper on JARVIS
  □ /backtest/results endpoint
  □ Backtest panel in GeoRisk Terminal
  □ Cloudflare Tunnel or manual JSON upload

Phase 4 — Enhancement (after 3+ months live data)
  □ statsforecast volatility prediction
  □ Kelly-based position sizing
  □ Multi-asset regime allocation
  □ AI chat integration for signal explanation
```

---

## License

MIT — Personal use. Not financial advice.

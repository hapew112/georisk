# GeoRisk Project

## Architecture
- **georisk-proxy** (Cloudflare Worker): all API endpoints, holds FINNHUB_KEY + FRED_KEY
- **georiskdashboard** (Cloudflare Worker): serves HTML only, `WORKERS_URL` points to georisk-proxy
- Frontend JS lives embedded inside `worker.js` as a template literal

## Deploy Rules
- ALWAYS deploy from `/tmp/wrangler_deploy/` with only `worker.js` + `wrangler.toml`
- NEVER deploy from `~/georisk/` directly — wrangler v4 scans `backtest/venv/` and hits 50MB asset limit
- Syntax check before every deploy: `node --check worker.js`

```bash
rm -rf /tmp/wrangler_deploy && mkdir /tmp/wrangler_deploy
cp worker.js wrangler.toml /tmp/wrangler_deploy/
cd /tmp/wrangler_deploy && npx wrangler deploy
```

## Cron Schedule (KST)
| Time | Script | Purpose |
|------|--------|---------|
| 09:00 평일 | `paper_trader.py` | Signal calc + paper log |
| 23:00 평일 | `georisk_v2.py` | Signal + Telegram alert |
| 23:40 평일 | `kis_trader.py` | KIS order + kis_snapshot.json |
| 09:00 일요일 | `weekly_report.py` | Gemini report → Telegram |

## Key Files
- `~/georisk/kis_snapshot.json` — KIS real account snapshots (90-day rolling)
- `~/georisk/paper_log.json` — paper trading log (baseline: 2026-04-30)
- `~/georisk/.georisk_env` — env vars (never commit)
- `~/georisk/backtest/venv/bin/python3` — always use this, not system python

## KIS API (모의투자)
- Account: `50184581-01`
- Base URL: `https://openapivts.koreainvestment.com:29443`
- TR_IDs (모의): `VTTS3012R` (holdings), `VTRP6504R` (total assets), `VTTS3307R` (psamount)
- Market hours: ET 09:30–16:00 = KST 23:30–06:00

## georisk-proxy Endpoints
`/api/macro` `/api/sectors` `/api/heatmap` `/api/feargreed` `/api/chart` `/api/credit`
`/api/putcall` `/api/yieldcurve` `/api/oref` `/api/rss` `/api/news` `/api/outages`
`/api/quote` `/api/paper` `/api/regime`

## Data Sources
- Macro prices (DXY, Gold, Oil, VIX, yields): Yahoo Finance via `fetchYahoo()`
- Sector ETFs: Yahoo Finance fallback when no Finnhub key
- FX (USDKRW, USDJPY): Frankfurter API
- Fear & Greed: CNN → VIX-derived fallback

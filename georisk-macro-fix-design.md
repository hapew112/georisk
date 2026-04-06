# GeoRisk Terminal — 매크로 레이더 실데이터 연동 설계도

## 현황 요약

매크로 레이더의 지수 카드, 티커바, 차트, 히트맵이 **가짜 데이터**를 표시 중.
`/api/macro`는 실데이터를 반환하지만, 프론트엔드의 `v6init`/`v6tick`이 이를 무시하고
하드코딩된 `base` 값 + `Math.random()`으로 시뮬레이션함.

---

## 수정 대상 3건

### 수정 1: v6init/v6tick을 /api/macro 실데이터로 교체

**현재 코드 (index.html 라인 1509~1528)**
```js
function v6init(){
  const all = Object.values(IDX_DATA).flat();
  all.forEach(item => {
    const n = () => (Math.random()-0.49)*0.003;
    v6prices[item.sym] = {val: item.base*(1+n()), chg: (Math.random()-0.48)*3};
    v6history[item.sym] = Array.from({length:60}, () => item.base*(1+(Math.random()-0.5)*0.015));
  });
  hmapData.us.forEach(h => {h.chg = (Math.random()-0.48)*2.5;});
  hmapData.kr.forEach(h => {h.chg = (Math.random()-0.48)*2.5;});
}

function v6tick(){
  Object.keys(v6prices).forEach(sym => {
    const p = v6prices[sym];
    p.val *= 1+(Math.random()-0.5)*0.0015;
    p.chg += (Math.random()-0.5)*0.04;
    ...
  });
  hmapData.us.forEach(h => {h.chg += (Math.random()-0.5)*0.06; ...});
  hmapData.kr.forEach(h => {h.chg += (Math.random()-0.5)*0.06; ...});
}
```

**교체 설계:**

#### 1-1. IDX_DATA에 `macroKey` 필드 추가

`IDX_DATA` 각 항목에 `/api/macro` 응답의 key를 매핑하는 필드 추가.
`/api/macro`에 없는 심볼은 `/api/heatmap`이나 별도 호출 필요.

```js
const IDX_DATA = {
  americas: [
    {sym:'SPY',  name:'S&P 500',    flag:'🇺🇸', tv:'AMEX:SPY',        base:655, macroKey:'SPX'},
    {sym:'QQQ',  name:'NASDAQ 100', flag:'🇺🇸', tv:'NASDAQ:QQQ',      base:492, macroKey:'NASDAQ'},
    {sym:'DIA',  name:'Dow Jones',  flag:'🇺🇸', tv:'AMEX:DIA',        base:465, macroKey:'DJI'},
    {sym:'IWM',  name:'Russell 2K', flag:'🇺🇸', tv:'AMEX:IWM',        base:205, macroKey:'RUT'},
    {sym:'EWC',  name:'Canada',     flag:'🇨🇦', tv:'AMEX:EWC',        base:38,  macroKey:null},
    {sym:'EWZ',  name:'Brazil',     flag:'🇧🇷', tv:'AMEX:EWZ',        base:28,  macroKey:null},
  ],
  asia: [
    {sym:'KOSPI', name:'KOSPI',      flag:'🇰🇷', tv:'KRX:KOSPI',       base:2540, macroKey:'KOSPI'},
    {sym:'KOSDAQ',name:'KOSDAQ',     flag:'🇰🇷', tv:'KRX:KOSDAQ',      base:755,  macroKey:null},
    {sym:'N225',  name:'Nikkei 225', flag:'🇯🇵', tv:'TVC:NI225',       base:38400, macroKey:'N225'},
    {sym:'HSI',   name:'Hang Seng',  flag:'🇭🇰', tv:'TVC:HSI',         base:21500, macroKey:'HSI'},
    {sym:'CSI300',name:'CSI 300',    flag:'🇨🇳', tv:'SSE:000300',      base:3850, macroKey:null},
    {sym:'TWII',  name:'TAIEX',      flag:'🇹🇼', tv:'TWSE:TAIEX',      base:21200, macroKey:null},
    {sym:'STI',   name:'Singapore',  flag:'🇸🇬', tv:'SGX:STI',         base:3400, macroKey:null},
    {sym:'ASX200',name:'ASX 200',    flag:'🇦🇺', tv:'ASX:XJO',         base:7800, macroKey:null},
    {sym:'NIFTY', name:'NIFTY 50',   flag:'🇮🇳', tv:'NSE:NIFTY',       base:22500, macroKey:null},
  ],
  europe: [
    {sym:'SX5E',  name:'EuroStoxx50',flag:'🇪🇺', tv:'TVC:SX5E',        base:5100, macroKey:'EURO50'},
    {sym:'DAX',   name:'DAX',         flag:'🇩🇪', tv:'XETR:DAX',        base:22000, macroKey:'DAX'},
    {sym:'CAC40', name:'CAC 40',      flag:'🇫🇷', tv:'EURONEXT:PX1',    base:8100, macroKey:null},
    {sym:'FTSE',  name:'FTSE 100',    flag:'🇬🇧', tv:'TVC:UKX',         base:8400, macroKey:'FTSE'},
    {sym:'SMI',   name:'Swiss SMI',   flag:'🇨🇭', tv:'TVC:SMI',         base:12300, macroKey:null},
    {sym:'IBEX',  name:'IBEX 35',     flag:'🇪🇸', tv:'BME:IBC',         base:13200, macroKey:null},
  ],
  commodities: [
    {sym:'BTC',   name:'Bitcoin',    flag:'₿',  tv:'BITSTAMP:BTCUSD', base:68000, macroKey:'BINANCE:BTCUSDT'},
    {sym:'ETH',   name:'Ethereum',   flag:'Ξ',  tv:'BITSTAMP:ETHUSD', base:2400,  macroKey:null},
    {sym:'WTI',   name:'WTI Crude',  flag:'🛢', tv:'TVC:USOIL',       base:110,   macroKey:'CL1!'},
    {sym:'BRENT', name:'Brent',      flag:'🛢', tv:'TVC:UKOIL',       base:109,   macroKey:null},
    {sym:'GOLD',  name:'Gold (XAU)', flag:'🥇', tv:'TVC:GOLD',        base:4680,  macroKey:'GC1!'},
    {sym:'SILVER',name:'Silver',     flag:'🥈', tv:'TVC:SILVER',      base:33.5,  macroKey:'SILVER'},
    {sym:'NG',    name:'Nat. Gas',   flag:'⛽', tv:'TVC:NATURALGAS',  base:2.80,  macroKey:'NG1!'},
    {sym:'COPPER',name:'Copper',     flag:'🔶', tv:'TVC:COPPER',      base:4.6,   macroKey:'HG1!'},
  ],
  fx: [
    {sym:'USDKRW',name:'USD/KRW',   flag:'💱', tv:'FX:USDKRW',       base:1385, macroKey:'USDKRW'},
    {sym:'EURUSD',name:'EUR/USD',   flag:'💶', tv:'FX:EURUSD',       base:1.08, macroKey:null},
    {sym:'USDJPY',name:'USD/JPY',   flag:'¥',  tv:'FX:USDJPY',       base:149,  macroKey:'USDJPY'},
    {sym:'USDCNH',name:'USD/CNH',   flag:'¥',  tv:'FX:USDCNH',       base:7.28, macroKey:null},
    {sym:'DXY',   name:'DXY Index', flag:'📊', tv:'TVC:DXY',         base:100,  macroKey:'DXY'},
    {sym:'VIX',   name:'VIX',       flag:'😱', tv:'CBOE:VIX',        base:24,   macroKey:'VIX'},
  ],
};
```

**주의사항:**
- `base` 값은 2026년 4월 기준 대략치로 업데이트 (API 실패 시 폴백용)
- `macroKey: null`인 항목들은 `/api/macro`에서 데이터가 안 옴 → base 폴백 유지
  - 추후 worker.js의 MACRO_YAHOO 배열에 추가하면 자동으로 실데이터 표시됨

#### 1-2. v6init() 교체

```js
function v6init() {
  // base 값으로 초기화 (API 응답 전 폴백)
  const all = Object.values(IDX_DATA).flat();
  all.forEach(item => {
    v6prices[item.sym] = { val: item.base, chg: 0 };
    v6history[item.sym] = Array(60).fill(item.base);
  });
  hmapData.us.forEach(h => { h.chg = 0; });
  hmapData.kr.forEach(h => { h.chg = 0; });
  // 즉시 실데이터 fetch
  v6fetchReal();
}
```

#### 1-3. v6fetchReal() 신규 함수 — 핵심

```js
async function v6fetchReal() {
  try {
    // 1) /api/macro에서 매크로 데이터 가져오기
    const macroData = WORKERS_URL
      ? await API.get('/api/macro')
      : {};

    // 2) /api/heatmap에서 섹터 ETF 데이터 가져오기
    let heatmapData = {};
    if (WORKERS_URL) {
      try {
        const hRes = await fetch(`${WORKERS_URL}/api/heatmap`, {signal: AbortSignal.timeout(6000)});
        if (hRes.ok) {
          const hJson = await hRes.json();
          (hJson.sectors || []).forEach(s => { heatmapData[s.symbol] = s; });
        }
      } catch {}
    }

    // 3) IDX_DATA 전체를 순회하며 v6prices 업데이트
    const all = Object.values(IDX_DATA).flat();
    all.forEach(item => {
      if (item.macroKey && macroData[item.macroKey]?.c) {
        const d = macroData[item.macroKey];
        v6prices[item.sym] = { val: d.c, chg: d.dp || 0 };
        // 히스토리에 현재 값 push (시간 경과에 따라 축적)
        if (v6history[item.sym]) {
          v6history[item.sym].push(d.c);
          if (v6history[item.sym].length > 80) v6history[item.sym].shift();
        }
      }
      // macroKey 없는 항목은 base 폴백 유지
    });

    // 4) 히트맵 데이터 업데이트 (US 섹터)
    hmapData.us.forEach(h => {
      if (heatmapData[h.sym]) {
        h.chg = heatmapData[h.sym].changePercent || 0;
      }
    });
    // KR 히트맵은 별도 API 없으면 유지 (추후 worker에 /api/heatmap-kr 추가 가능)

  } catch (e) {
    console.error('[v6fetchReal] Error:', e);
  }
}
```

#### 1-4. v6tick() 삭제, v6update() 교체

```js
// v6tick() 함수 전체 삭제

function v6update() {
  v6fetchReal().then(() => {
    renderTicker();
    renderAllIdxGroups();
    updateV6Charts();
    renderHmapTab();
  });
}
```

#### 1-5. DOMContentLoaded 수정

```js
v6init(); // base 값 초기화 + v6fetchReal() 호출

document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    renderTicker();
    renderAllIdxGroups();
    initV6Charts();
    renderHmapTab();
    fetchFGv6();
  }, 200);
  setTimeout(() => fetchOverview(), 800);
  setInterval(v6update, 30000);  // 30초마다 실데이터 갱신
  setInterval(fetchFGv6, 120000);
});
```

---

### 수정 2: 모바일 매크로 패널 갱신

**현재 코드 (index.html 라인 4705~4711)**
```js
} else if (which === 'macro') {
  const src = document.getElementById('right-scroll');
  const dest = document.getElementById('mobMacroContent');
  if (src && dest.children.length === 0) {  // ← 한번만 복사
    dest.innerHTML = src.innerHTML;
  }
  macro.classList.add('open');
}
```

**교체:**
```js
} else if (which === 'macro') {
  const src = document.getElementById('right-scroll');
  const dest = document.getElementById('mobMacroContent');
  if (src) {
    dest.innerHTML = src.innerHTML;  // 열 때마다 항상 최신 복사
  }
  macro.classList.add('open');
}
```

동일하게 countries 패널도:
```js
if (which === 'countries') {
  const src = document.querySelector('.panel .pb');
  const dest = document.getElementById('mobCountryContent');
  if (src) {
    dest.innerHTML = src.innerHTML;  // 열 때마다 항상 최신 복사
  }
  countries.classList.add('open');
}
```

---

### 수정 3: TradingView 심볼 매핑 검증

아래 IDX_DATA의 `tv` 값 중 의심되는 것들의 정확한 매핑.
Gemini에게 각 심볼을 `https://www.tradingview.com/chart/?symbol=XXX`에서
실제로 차트가 로딩되는지 확인 요청.

**검증/교체 필요 목록:**

| sym | 현재 tv | 수정 후 tv | 사유 |
|-----|---------|-----------|------|
| KOSPI | KRX:KOSPI | KRX:KOSPI | 확인 필요 — TradingView에서 KRX:KOSPI 유효한지 |
| KOSDAQ | KRX:KOSDAQ | KRX:KOSDAQ | 확인 필요 |
| CSI300 | SHSE:000300 | SSE:000300 | SHSE는 TradingView에서 안 될 수 있음 |
| TWII | TWSE:TX1! | TWSE:TAIEX | TX1!은 선물, TAIEX가 현물지수 |
| VIX | TVC:VIX | CBOE:VIX | TVC:VIX vs CBOE:VIX 둘 다 확인 |
| DXY | TVC:DXY | TVC:DXY | 확인 필요 |
| EuroStoxx50 | TVC:SX5E | TVC:SX5E | 확인 필요 |
| BRENT | TVC:UKOIL | TVC:UKOIL | 확인 필요 |
| Nikkei | TVC:NI225 | TVC:NI225 | 확인 필요 |
| CAC40 | EURONEXT:PX1 | EURONEXT:PX1 | 확인 필요 |
| IBEX | BME:IBC | BME:IBC | 확인 필요 |
| SMI | TVC:SMI | TVC:SMI | 확인 필요 |

**검증 방법:**
브라우저에서 `https://www.tradingview.com/chart/?symbol=KRX:KOSPI` 등을 직접 열어보고
차트가 뜨면 OK, 안 뜨면 TradingView 검색에서 정확한 심볼 확인.

---

### 수정 4: Yield Curve 하드코딩 교체

**현재 코드 (라인 1615):**
```js
const yieldVals = [4.62, 4.40, 4.25, 4.22, 4.20, 4.28, 4.48];
```
이것도 하드코딩. `/api/macro`에서 `TVC:US10Y`와 `TVC:US02Y`는 이미 오고 있으므로,
`initYieldChart()` → `updateYieldCurve(quotes)`에서 실데이터로 교체되는지 확인 필요.

**라인 3959의 `updateYieldCurve(quotes)` 확인 후:**
- 이미 실데이터로 교체하는 로직이 있다면 OK
- 없다면 `/api/yieldcurve` 엔드포인트 호출로 교체 필요

---

## 작업 순서 (Gemini 전달용)

```
1단계: IDX_DATA base 값 현행화 + macroKey 필드 추가
2단계: v6init() 교체 → base 초기화 + v6fetchReal() 호출
3단계: v6fetchReal() 신규 함수 구현
4단계: v6tick() 삭제, v6update() 교체
5단계: 모바일 패널 갱신 로직 수정
6단계: TradingView tv 심볼 전수 검증 (브라우저 직접 확인)
7단계: Yield Curve 하드코딩 확인/교체
8단계: 배포 후 테스트 — 모든 지수 카드에 실시간 데이터 표시 확인
```

## 테스트 체크리스트

- [ ] 금융탭 SPY 카드: 현재가 ~$650대 표시 (565 아님)
- [ ] 금융탭 KOSPI 카드: 현재가 ~2540대 표시
- [ ] 금융탭 BTC 카드: 현재가 ~$68000대 표시
- [ ] 금융탭 VIX 카드: 현재가 ~22-24대 표시
- [ ] 티커바: 실시간 데이터 표시
- [ ] 주요 지수 차트(S&P 500, KOSPI 등): Chart.js 라인 렌더링
- [ ] 히트맵 US: /api/heatmap 실데이터 반영
- [ ] 모바일 매크로 패널: 열 때마다 최신 데이터
- [ ] TradingView 리다이렉트: 모든 심볼 클릭 시 정상 차트 로딩

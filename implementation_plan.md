# GeoRisk v6 성능 개선 계획

초기 로딩이 느린 4가지 핵심 원인을 수정합니다.

## 문제 분석

| # | 문제 | 원인 | 영향 |
|---|------|------|------|
| 1 | **트리맵 느림** | 빈 `src=""`로 iframe이 페이지 로드 시 즉시 생성됨. `switchTreemap`이 호출되기도 전에 불필요한 네트워크 요청 발생 | 초기 로딩 차단 |
| 2 | **KOSPI 심볼 에러** | `IDX_DATA.asia`에서 `tv:'KRX:KOSPI'` 사용 → TradingView에서 "심볼 제공됨" 에러 | 콘솔 에러 반복 |
| 3 | **뉴스 느림** | [fetchAll()](file:///c:/Users/hapew112/Downloads/index.html.html#1411-1437)이 10개 RSS를 `Promise.allSettled`로 동시 호출하지만, 각 소스가 3중 폴백(Workers→allorigins→corsproxy) 시도. 실패 시 소스 당 최대 27초(9s×3) 블록 가능 | 피드 로딩 지연 |
| 4 | **초기 전체 느림** | [renderMacro()](file:///c:/Users/hapew112/Downloads/index.html.html#907-950) + [fetchAll()](file:///c:/Users/hapew112/Downloads/index.html.html#1411-1437) + [v6init](file:///C:/Users/hapew112/Downloads/Georisk/index%281%29.html#1061-1071) 차트 + 히트맵 탭 + 경제 캘린더가 모두 동시 실행 | UI 렌더 차단 |

## Proposed Changes

### [MODIFY] [index(1).html](file:///C:/Users/hapew112/Downloads/Georisk/index(1).html)

> [!IMPORTANT]
> 수정된 파일을 [georisk-deploy/index.html](file:///C:/Users/hapew112/.gemini/antigravity/scratch/georisk-deploy/index.html)에 배포용으로 복사합니다.

#### 1. 트리맵 Lazy Loading (Lines ~857-867)
- iframe `src=""`를 제거하고, 트리맵 컨테이너를 처음엔 placeholder만 표시
- `switchTreemap()` 호출 시에만 iframe src를 설정
- 우측 패널의 트리맵도 **탭을 처음 볼 때**에만 로드 (Intersection Observer 또는 직접 호출)

```diff
-<iframe id="treemap-frame" src="" ...>
+<iframe id="treemap-frame" data-src="" ...>
```

`switchTreemap()` 함수에서 첫 호출 시에만 iframe src를 설정하고, 로딩 인디케이터를 보여줌.

#### 2. KOSPI TradingView 심볼 수정 (Line ~1002)
- `KRX:KOSPI` → `KRX:KOSPI` 자체는 TradingView에서 유효한 심볼
- 하지만 **Finnhub에서는 'KOSPI'** 심볼을 인식 못함 → ETF 프록시(`AMEX:EWY`)로 교체하거나, TradingView 전용으로만 사용
- IDX_DATA에서 KOSPI/KOSDAQ은 TradingView 링크용이지 Finnhub 데이터 소스가 아님 → v6prices에 시뮬레이션 데이터만 있어서 문제 없음
- **실제 문제**: 차트 분석 탭의 KOSPI 버튼이 `AMEX:EWY`를 올바르게 사용 중 (line 654) → 이 부분은 OK
- idx-card 클릭 시 `KRX:KOSPI`로 TradingView 열리는 것은 정상 → **에러가 나는 곳이 있다면 `treemap-frame`의 TradingView 위젯일 수 있음**

> 사용자에게 확인 필요: "코스피 계속 뜬다"는 게 구체적으로 어디서 에러가 발생하는지

#### 3. 뉴스 피드 로딩 최적화 (Lines ~2470-2494)
- [fetchAll()](file:///c:/Users/hapew112/Downloads/index.html.html#1411-1437)을 **2단계로 분리**: Tier 1 소스(4개)를 먼저 가져와 즉시 렌더, 그 후 Tier 2 소스(6개)를 백그라운드로 가져와 병합
- 각 소스의 타임아웃을 9초→6초로 단축
- Workers 프록시 실패 시 곧바로 다음 폴백으로 넘어가도록 타임아웃 단축

```js
async function fetchAll(){
  // Phase 1: Tier 1 (4개) — 빠르게 렌더
  const tier1 = SOURCES.filter(s => s.tier === 1);
  const tier2 = SOURCES.filter(s => s.tier !== 1);
  
  const r1 = await Promise.allSettled(tier1.map(fetchFeed));
  // ... 즉시 renderFeed
  
  // Phase 2: Tier 2 (6개) — 백그라운드
  const r2 = await Promise.allSettled(tier2.map(fetchFeed));
  // ... 병합 후 re-render
}
```

#### 4. 초기 로딩 순서 최적화 (Lines ~2496-2503)
현재 순서:
```
initBaseline() → renderMacro() → fetchAll() → (동시: v6init + hmRenderTopTabs + caRenderEcoCalendar)
```

개선:
```
initBaseline()
→ 즉시: renderMacro() (매크로 그리드 로딩)
→ 200ms 후: renderTicker + renderAllIdxGroups + initV6Charts (시뮬 데이터로 빠르게)
→ 병렬: fetchAll() Phase 1 (Tier 1 뉴스)
→ Phase 1 완료 후: 렌더 + Phase 2 시작
→ 1초 후: hmRenderTopTabs, caRenderEcoCalendar (사용자가 보지 않는 탭은 지연)
→ 트리맵: 탭 진입 시에만 로드
```

#### 5. 히트맵 탭 / 차트 분석 탭 Lazy Init (Lines ~1614-1619, ~1911-1919)
**이미 구현되어 있음** (line 1911-1919에서 탭 진입 시 초기화). 하지만 `DOMContentLoaded`에서도 [hmRenderTopTabs()](file:///C:/Users/hapew112/Downloads/Georisk/index%281%29.html#1333-1341)와 [caRenderEcoCalendar()](file:///C:/Users/hapew112/Downloads/Georisk/index%281%29.html#1590-1612)를 호출 (line 1614-1619). 이를 제거하고 탭 진입 시에만 초기화.

```diff
-document.addEventListener('DOMContentLoaded', () => {
-  setTimeout(() => {
-    hmRenderTopTabs();
-    caRenderEcoCalendar();
-  }, 300);
-});
+// 탭 진입 시에만 초기화 (switchMainTab에서 처리)
```

## Verification Plan

### Manual Verification
1. 수정된 [index.html](file:///C:/Users/hapew112/.gemini/antigravity/scratch/georisk-deploy/index.html)을 브라우저에서 열기
2. **초기 로딩 속도**: 페이지 오픈 후 뉴스 피드가 이전보다 빠르게 표시되는지 확인
3. **트리맵**: 우측 패널의 트리맵 영역에 "트리맵 탭을 선택하세요" 표시 → 탭 선택 시 로딩
4. **KOSPI 에러**: 브라우저 콘솔에서 TradingView 관련 에러가 없는지 확인
5. **히트맵 탭**: 히트맵 탭 클릭 전까지 iframe이 로드되지 않는지 DevTools Network 탭에서 확인
6. 수정 후 Cloudflare Pages에 배포하여 실제 환경 테스트

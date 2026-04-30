// GeoRisk Dashboard - Cloudflare Workers API Proxy v2.3
// ENV: FINNHUB_KEY (required), CF_RADAR_KEY (optional)

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Content-Type': 'application/json',
};

const TTL = {
  quote: 60, macro: 60, sector: 60,
  feargreed: 300, outages: 600, oref: 30, rss: 300, news: 300, fx: 300,
};

function prevBizDay() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const day = d.getDay();
  if (day === 0) d.setDate(d.getDate() - 2);
  else if (day === 6) d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

const SECTOR_NAMES = {
  XLK:'Technology', XLF:'Financials', XLE:'Energy', XLV:'Health Care',
  XLY:'Cons. Disc.', XLI:'Industrials', XLP:'Cons. Staples', XLU:'Utilities',
  XLB:'Materials', XLRE:'Real Estate', XLC:'Comm. Svcs.', SMH:'Semiconductors',
};

const memCache = new Map();
function getCache(key) {
  const e = memCache.get(key);
  if (!e) return null;
  if (Date.now() > e.exp) { memCache.delete(key); return null; }
  return e.data;
}
function setCache(key, data, ttl) {
  memCache.set(key, { data, exp: Date.now() + ttl * 1000 });
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: CORS });
}
function err(msg, status = 400) {
  return new Response(JSON.stringify({ error: msg }), { status, headers: CORS });
}

async function fetchFinnhub(symbol, apiKey) {
  if (!apiKey) throw new Error('FINNHUB_KEY not set');
  const r = await fetch(
    `https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(symbol)}&token=${apiKey}`,
    { signal: AbortSignal.timeout(8000) }
  );
  if (!r.ok) throw new Error(`Finnhub HTTP ${r.status}`);
  return r.json();
}

const MACRO_MAP = [
  { fetch: 'USO',             key: 'CL1!'            },
  { fetch: 'GLD',             key: 'GC1!'            },
  { fetch: 'UUP',             key: 'DXY'             },
  { fetch: 'VIXY',            key: 'VIX'             },
  { fetch: 'BINANCE:BTCUSDT', key: 'BINANCE:BTCUSDT' },
  { fetch: 'TLT',             key: 'TVC:US10Y'       },
  { fetch: 'SHY',             key: 'TVC:US02Y'       },
  { fetch: 'UNG',             key: 'NG1!'            },
  { fetch: 'CPER',            key: 'HG1!'            },
  { fetch: 'SLV',             key: 'SILVER'          },
];

const SECTOR_ETFS = ['XLK','XLF','XLE','XLV','XLY','XLI','XLP','XLU','XLB','XLRE','XLC','SMH'];

const NEWS_SOURCES = {
  global: [
    { name: 'BBC World',      url: 'https://feeds.bbci.co.uk/news/world/rss.xml',         backup: 'https://feeds.bbci.co.uk/news/rss.xml' },
    { name: 'Guardian',       url: 'https://www.theguardian.com/world/rss',                backup: 'https://www.theguardian.com/international/rss' },
    { name: 'Al Jazeera',     url: 'https://www.aljazeera.com/xml/rss/all.xml',            backup: null },
    { name: 'Der Spiegel',    url: 'https://www.spiegel.de/international/index.rss',       backup: null },
    { name: 'Reuters',        url: 'https://feeds.reuters.com/reuters/worldNews',           backup: null },
  ],
  korea: [
    { name: 'Hankyung',       url: 'https://www.hankyung.com/feed/all-news',               backup: 'https://www.mk.co.kr/rss/30000001/' },
    { name: 'Yonhap',         url: 'https://www.yna.co.kr/rss/news.xml',                   backup: 'https://www.yna.co.kr/rss/economy.xml' },
    { name: 'Chosunbiz',      url: 'https://biz.chosun.com/site/data/rss/rss.xml',         backup: null },
    { name: 'YTN',            url: 'https://www.ytn.co.kr/rss/rss_06.xml',                 backup: null },
    { name: 'JoongAng',       url: 'https://koreajoongangdaily.joins.com/rss/news',         backup: null },
  ],
  macro: [
    { name: 'OilPrice',       url: 'https://oilprice.com/rss/main',                        backup: null },
    { name: 'MarketWatch',    url: 'https://feeds.marketwatch.com/marketwatch/topstories/', backup: null },
    { name: 'Reuters Biz',    url: 'https://feeds.reuters.com/reuters/businessNews',        backup: null },
    { name: 'FT',             url: 'https://www.ft.com/markets?format=rss',                 backup: null },
    { name: 'SeekingAlpha',   url: 'https://seekingalpha.com/market_currents.xml',          backup: null },
  ],
  cyber: [
    { name: 'BleepingComp',   url: 'https://www.bleepingcomputer.com/feed/',               backup: null },
    { name: 'HackerNews',     url: 'https://feeds.feedburner.com/TheHackersNews',           backup: 'https://thehackernews.com/feeds/posts/default' },
    { name: 'ArsTechnica',    url: 'https://feeds.arstechnica.com/arstechnica/security',    backup: null },
    { name: 'Krebs',          url: 'https://krebsonsecurity.com/feed/',                     backup: null },
    { name: 'DarkReading',    url: 'https://www.darkreading.com/rss.xml',                   backup: null },
  ],
};

const IMPACT_KW = {
  macro:       ['fed','interest rate','inflation','gdp','recession','central bank','ecb','boj','fomc','cpi','tariff','trade','opec'],
  cyber:       ['hack','breach','malware','ransomware','vulnerability','exploit','zero-day','ddos','cyber'],
  geopolitical:['war','sanction','missile','military','nato','conflict','airstrike','iran','russia','taiwan','ukraine'],
  energy:      ['oil','gas','crude','opec','pipeline','lng','barrel','wti','brent'],
};

function classifyImpact(title, desc) {
  const t = ((title || '') + ' ' + (desc || '')).toLowerCase();
  for (const [k, kws] of Object.entries(IMPACT_KW)) {
    if (kws.some(w => t.includes(w))) return k;
  }
  return 'general';
}

function parseRSSXML(xml, sourceName) {
  const items = [];
  const itemRegex = /<(?:item|entry)>([\s\S]*?)<\/(?:item|entry)>/gi;
  let match;
  while ((match = itemRegex.exec(xml)) !== null && items.length < 12) {
    const block = match[1];
    const get = (tag) => {
      const m = block.match(new RegExp('<' + tag + '[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?<\\/' + tag + '>', 'i'));
      return m ? m[1].trim().replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"') : '';
    };
    const getLink = () => {
      const m1 = block.match(/<link[^>]*href=["']([^"']+)["']/i);
      if (m1) return m1[1];
      const m2 = block.match(/<link[^>]*>([\s\S]*?)<\/link>/i);
      return m2 ? m2[1].trim() : '';
    };
    const title = get('title');
    const link  = getLink() || get('link');
    const pub   = get('pubDate') || get('published') || get('updated') || new Date().toISOString();
    const desc  = get('description') || get('summary') || get('content');
    const cleanDesc = desc.replace(/<[^>]+>/g,'').slice(0,200);
    if (title.length > 5) {
      items.push({ title, source: sourceName, url: link, pubDate: pub, description: cleanDesc, impact: classifyImpact(title, desc) });
    }
  }
  return items;
}

async function fetchRSS(source) {
  const tryUrl = async (url) => {
    const r = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; GeoRiskBot/2.0)',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
      },
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const text = await r.text();
    return parseRSSXML(text, source.name);
  };
  try {
    const items = await tryUrl(source.url);
    if (items.length > 0) return items;
    throw new Error('empty');
  } catch {
    if (source.backup) {
      try { return await tryUrl(source.backup); } catch {}
    }
    return [];
  }
}

async function fetchNewsCategory(category) {
  const sources = NEWS_SOURCES[category] || [];
  const results = await Promise.allSettled(sources.map(s => fetchRSS(s)));
  const seen = new Set();
  const articles = results
    .filter(r => r.status === 'fulfilled')
    .flatMap(r => r.value)
    .filter(a => {
      const key = a.title.toLowerCase().slice(0, 60);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => new Date(b.pubDate) - new Date(a.pubDate))
    .slice(0, 30);
  return { category, timestamp: new Date().toISOString(), count: articles.length, articles };
}

async function fetchLatestNews() {
  const sample = [
    NEWS_SOURCES.global[0],
    NEWS_SOURCES.global[2],
    NEWS_SOURCES.korea[0],
    NEWS_SOURCES.korea[1],
    NEWS_SOURCES.macro[0],
    NEWS_SOURCES.macro[2],
    NEWS_SOURCES.cyber[0],
    NEWS_SOURCES.cyber[1],
  ].filter(Boolean);
  const results = await Promise.allSettled(sample.map(s => fetchRSS(s)));
  const seen = new Set();
  const articles = results
    .filter(r => r.status === 'fulfilled')
    .flatMap(r => r.value)
    .filter(a => {
      const key = a.title.toLowerCase().slice(0, 60);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => new Date(b.pubDate) - new Date(a.pubDate))
    .slice(0, 25);
  return { category: 'latest', timestamp: new Date().toISOString(), count: articles.length, articles };
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS });
    }

    const url  = new URL(request.url);
    const path = url.pathname;
    const key  = env.FINNHUB_KEY;

    try {

      if (path === '/' || path === '/health') {
        return json({
          service: 'georisk-proxy',
          version: '2.3.0',
          status: 'ok',
          timestamp: new Date().toISOString(),
          env: {
            FINNHUB_KEY:  key             ? 'SET' : 'NOT SET',
            CF_RADAR_KEY: env.CF_RADAR_KEY ? 'SET' : 'NOT SET (optional)',
          },
          endpoints: [
            'GET /api/quote?symbol=AAPL',
            'GET /api/quotes?symbols=XLK,XLF,XLE',
            'GET /api/macro',
            'GET /api/sectors',
            'GET /api/heatmap',
            'GET /api/feargreed',
            'GET /api/outages',
            'GET /api/oref',
            'GET /api/rss?url=RSS_URL',
            'GET /api/news?category=global|korea|macro|cyber|latest',
            'GET /api/regime',
            'GET /api/paper',
          ],
        });
      }

      if (path === '/api/paper') {
        try {
          const kv = env.GEORISK_REGIME || env.GEORISK_KV;
          if (!kv) return err('KV binding missing', 500);
          
          const log = await kv.get('paper_log', 'json');
          const status = await kv.get('paper_status', 'json');
          const metrics = await kv.get('paper_metrics', 'json');
          
          return json({ log, status, metrics });
        } catch(e) {
          return err('Paper data failed: ' + e.message, 500);
        }
      }

      if (path === '/api/regime') {
        try {
          const kv = env.GEORISK_REGIME || env.GEORISK_KV;
          const raw = kv ? await kv.get('latest_regime') : null;
          if (!raw) {
            return new Response(JSON.stringify({
              regime: 'NORMAL', composite_score: 2,
              spy_weight: 0.80, tlt_weight: 0.15, cash_weight: 0.05,
              last_updated: null, source: 'fallback'
            }), { headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' } });
          }
          return new Response(raw, {
            headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
          });
        } catch(e) {
          return new Response(JSON.stringify({ error: e.message }), { status: 500 });
        }
      }

      if (path === '/api/quote') {
        const symbol = url.searchParams.get('symbol');
        if (!symbol) return err('symbol required');
        const cached = getCache('q:' + symbol);
        if (cached) return json(cached);
        const data = await fetchFinnhub(symbol, key);
        setCache('q:' + symbol, data, TTL.quote);
        return json(data);
      }

      if (path === '/api/quotes') {
        const syms = (url.searchParams.get('symbols') || '').split(',').filter(Boolean);
        if (!syms.length) return err('symbols required');
        const results = {};
        await Promise.allSettled(syms.map(async sym => {
          const cached = getCache('q:' + sym);
          if (cached) { results[sym] = cached; return; }
          try {
            const d = await fetchFinnhub(sym, key);
            if (d.c) { results[sym] = d; setCache('q:' + sym, d, TTL.quote); }
          } catch {}
        }));
        return json(results);
      }

      if (path === '/api/macro') {
        const cached = getCache('macro');
        if (cached) return json(cached);
        const results = {};

        if (!key) {
          results.__warning = "FINNHUB_KEY not set — macro/sector data unavailable";
        } else {
          await Promise.allSettled(MACRO_MAP.map(async ({ fetch: sym, key: mapKey }) => {
            try {
              const d = await fetchFinnhub(sym, key);
              if (d.c) {
                results[mapKey] = d;
                setCache('q:' + sym, d, TTL.quote);
              }
            } catch {}
          }));
        }

        // FX 환율 via Frankfurter (무료, 키 불필요)
        try {
          const fxCached = getCache('fx:usdkrw');
          if (fxCached) {
            results['USDKRW'] = fxCached.krw;
            results['USDJPY'] = fxCached.jpy;
          } else {
            const prev = prevBizDay();
            const [todayRes, prevRes] = await Promise.allSettled([
              fetch('https://api.frankfurter.app/latest?from=USD&to=KRW,JPY', { signal: AbortSignal.timeout(6000) }),
              fetch(`https://api.frankfurter.app/${prev}?from=USD&to=KRW,JPY`, { signal: AbortSignal.timeout(6000) }),
            ]);
            if (todayRes.status === 'fulfilled' && todayRes.value.ok) {
              const fx = await todayRes.value.json();
              let fxPrev = null;
              if (prevRes.status === 'fulfilled' && prevRes.value.ok) {
                fxPrev = await prevRes.value.json();
              }
              const makeQ = (curr, prev) => {
                const dp = prev ? parseFloat(((curr - prev) / prev * 100).toFixed(4)) : 0;
                return { c: curr, dp, pc: prev || curr };
              };
              if (fx.rates?.KRW) results['USDKRW'] = makeQ(fx.rates.KRW, fxPrev?.rates?.KRW);
              if (fx.rates?.JPY) results['USDJPY'] = makeQ(fx.rates.JPY, fxPrev?.rates?.JPY);
              setCache('fx:usdkrw', { krw: results['USDKRW'], jpy: results['USDJPY'] }, TTL.fx);
            }
          }
        } catch {}
        setCache('macro', results, TTL.macro);
        return json(results);
      }

      if (path === '/api/sectors') {
        const cached = getCache('sectors');
        if (cached) return json(cached);
        if (!key) return json({ error: "FINNHUB_KEY not configured in CF Workers", sectors: [] });
        const results = {};
        await Promise.allSettled(SECTOR_ETFS.map(async sym => {
          try {
            const d = await fetchFinnhub(sym, key);
            if (d.c) results[sym] = d;
          } catch {}
        }));
        setCache('sectors', results, TTL.sector);
        return json(results);
      }

      if (path === '/api/heatmap') {
        const cached = getCache('heatmap');
        if (cached) return json(cached);
        if (!key) return json({ error: "FINNHUB_KEY not configured in CF Workers", sectors: [] });
        // sectors 캐시 재사용 or 새로 fetch
        let sectorData = getCache('sectors');
        if (!sectorData) {
          sectorData = {};
          await Promise.allSettled(SECTOR_ETFS.map(async sym => {
            try {
              const d = await fetchFinnhub(sym, key);
              if (d.c) sectorData[sym] = d;
            } catch {}
          }));
          setCache('sectors', sectorData, TTL.sector);
        }
        const sectors = Object.entries(sectorData).map(([sym, d]) => ({
          symbol: sym,
          name: SECTOR_NAMES[sym] || sym,
          price: d.c,
          changePercent: d.dp || 0,
        })).sort((a, b) => b.changePercent - a.changePercent);
        const result = { sectors, timestamp: new Date().toISOString() };
        setCache('heatmap', result, TTL.sector);
        return json(result);
      }

      if (path === '/api/feargreed') {
        const cached = getCache('feargreed');
        if (cached) return json(cached);
        try {
          const r = await fetch(
            'https://production.dataviz.cnn.io/index/fearandgreed/graphdata',
            { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(8000) }
          );
          if (!r.ok) throw new Error('CNN HTTP ' + r.status);
          const d = await r.json();
          const result = {
            score:   Math.round(d && d.fear_and_greed ? d.fear_and_greed.score : 0),
            rating:  d && d.fear_and_greed ? d.fear_and_greed.rating : 'neutral',
            source:  'cnn',
            updated: new Date().toISOString(),
          };
          setCache('feargreed', result, TTL.feargreed);
          return json(result);
        } catch (e) {
          const vixCached = getCache('q:VIXY');
          const vixVal = vixCached ? vixCached.c : 20;
          const score = Math.max(5, Math.min(95, Math.round(100 - (vixVal - 10) * 2.5)));
          const rating = score >= 75 ? 'Extreme Greed' : score >= 55 ? 'Greed' : score >= 45 ? 'Neutral' : score >= 25 ? 'Fear' : 'Extreme Fear';
          return json({ score, rating, source: 'vix_derived', vix: vixVal, updated: new Date().toISOString() });
        }
      }

      if (path === '/api/outages') {
        const cached = getCache('outages');
        if (cached) return json(cached);
        const headers = env.CF_RADAR_KEY ? { 'Authorization': 'Bearer ' + env.CF_RADAR_KEY } : {};
        try {
          const r = await fetch(
            'https://api.cloudflare.com/client/v4/radar/annotations/outages?limit=10&dateRange=1d&format=json',
            { headers, signal: AbortSignal.timeout(8000) }
          );
          const d = await r.json();
          setCache('outages', d, TTL.outages);
          return json(d);
        } catch (e) {
          return err('Radar failed: ' + e.message, 502);
        }
      }

      if (path === '/api/oref') {
        const cached = getCache('oref');
        if (cached) return json(cached);
        try {
          const r = await fetch(
            'https://www.oref.org.il/WarningMessages/alert/alerts.json',
            {
              headers: {
                'Referer': 'https://www.oref.org.il/',
                'X-Requested-With': 'XMLHttpRequest',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
              },
              signal: AbortSignal.timeout(8000),
            }
          );
          const text = await r.text();
          const result = { raw: text, status: r.status, updated: new Date().toISOString() };
          setCache('oref', result, TTL.oref);
          return json(result);
        } catch (e) {
          return err('OREF failed: ' + e.message, 502);
        }
      }

      if (path === '/api/rss') {
        const rssUrl = url.searchParams.get('url');
        if (!rssUrl) return err('url required');
        const cacheKey = 'rss:' + rssUrl;
        const cached = getCache(cacheKey);
        if (cached) {
          return new Response(cached, {
            headers: { ...CORS, 'Content-Type': 'text/xml; charset=utf-8', 'X-Cache': 'HIT' }
          });
        }
        try {
          const r = await fetch(rssUrl, {
            headers: {
              'User-Agent': 'Mozilla/5.0 (compatible; GeoRiskBot/2.0)',
              'Accept': 'application/rss+xml, application/xml, text/xml, */*',
            },
            signal: AbortSignal.timeout(8000),
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const text = await r.text();
          setCache(cacheKey, text, TTL.rss);
          return new Response(text, {
            headers: { ...CORS, 'Content-Type': 'text/xml; charset=utf-8' }
          });
        } catch (e) {
          return new Response(
            JSON.stringify({ error: 'RSS failed: ' + e.message }),
            { status: 502, headers: CORS }
          );
        }
      }

      if (path === '/api/news') {
        const category = url.searchParams.get('category') || 'latest';
        const cacheKey = 'news:' + category;
        const cached = getCache(cacheKey);
        if (cached) return json(cached);
        const data = category === 'latest' ? await fetchLatestNews() : await fetchNewsCategory(category);
        setCache(cacheKey, data, TTL.news);
        return json(data);
      }

      return err('Not found. Check GET / for endpoints', 404);

    } catch (e) {
      return err('Server error: ' + e.message, 500);
    }
  },
};

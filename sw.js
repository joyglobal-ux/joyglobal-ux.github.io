/* Polaris 서비스워커 — 루트(/) 스코프라 같은 오리진의 프로젝트 사이트(rs-screener 등)까지 담당한다.
   전략:
   - 페이지(HTML 내비게이션): network-first(3.5초 타임아웃) → 실패/지연 시 캐시. 브리핑·ETF 트래커처럼
     데이터가 HTML에 들어 있는 페이지가 많아서, 온라인이면 항상 최신을 보여주고 오프라인이면 마지막 화면.
   - 셸(아이콘·manifest·CSS·일반 JS·이미지, cdnjs Chart.js): stale-while-revalidate.
   - 데이터(*.json, data*.js, series-*.js, strategy-data.js …): network-first → 실패 시 캐시.
     ?v=/?t= 캐시버스터는 떼고 경로 하나당 1개만 저장. 큰 파일(setups·events·series·data-us/kr)은
     별도 캐시에 최근 BIG_MAX개만 유지.
   배포 후 캐시 구조를 바꾸면 VERSION을 올린다(이전 캐시는 activate 때 삭제). */
const VERSION = 'polaris-v1';   // 캐시 구조·전략을 바꾸면 v2, v3…로 올린다
const SHELL = VERSION + '-shell';
const PAGES = VERSION + '-pages';
const DATA = VERSION + '-data';
const BIG = VERSION + '-big';
const BIG_MAX = 8;   // US·KR 각각 data·setups·events·series = 8개(약 20MB)
const NAV_TIMEOUT = 3500;
const PRECACHE = ['/', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/apple-touch-icon.png'];
const WARM = ['/portfolio-tracker/', '/allocation/', '/rs-screener/'];

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const shell = await caches.open(SHELL);
    await Promise.all(PRECACHE.map(u => shell.add(u).catch(() => {})));
    const pages = await caches.open(PAGES);
    await Promise.all(WARM.map(u => fetch(u).then(r => r.ok && pages.put(u, r)).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (!k.startsWith(VERSION + '-')) await caches.delete(k);
    await self.clients.claim();
  })());
});

const isBig = p => /\/(setups-(us|kr)\.json|setups-events-[^/]*\.json|series-[^/]*\.js|data-(us|kr)\.(js|json))$/.test(p);
const isData = p => /\.json$/.test(p) || /\/(data[^/]*|series-[^/]*|strategy-data)\.js$/.test(p);
const strip = u => { const x = new URL(u); x.search = ''; x.hash = ''; return x.href; };
const cacheable = r => r && r.ok && (r.type === 'basic' || r.type === 'cors');

async function trim(cache, max) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
}

async function networkFirstData(req, path) {
  const name = isBig(path) ? BIG : DATA, key = strip(req.url);
  try {
    const res = await fetch(req);
    if (cacheable(res)) {
      const c = await caches.open(name), copy = res.clone();
      // 삭제 후 put → keys() 순서가 최근 사용 순이 되어 trim이 오래된 것부터 지운다
      c.delete(key).then(() => c.put(key, copy)).then(() => name === BIG && trim(c, BIG_MAX)).catch(() => {});
    }
    if (res.status >= 500) { const hit = await caches.match(key, { cacheName: name }); if (hit) return hit; }
    return res;
  } catch (err) {
    const hit = await caches.match(key, { cacheName: name });
    if (hit) return hit;
    throw err;
  }
}

async function page(req) {
  const key = strip(req.url), c = await caches.open(PAGES);
  const net = fetch(req).then(res => {
    if (cacheable(res) && !res.redirected) c.put(key, res.clone()).catch(() => {});
    return res;
  });
  const timeout = new Promise(r => setTimeout(r, NAV_TIMEOUT, null));
  try {
    const res = await Promise.race([net, timeout]);
    if (res && res.status < 500) return res;   // 5xx(Pages 장애)는 캐시가 있으면 캐시로
  } catch (_) { /* 오프라인 → 아래 캐시 */ }
  const hit = (await c.match(key)) || (await caches.match(key));
  if (hit) return hit;
  try { const res = await net; if (res) return res; } catch (_) {}
  return (await caches.match('/')) || new Response('<meta charset=utf-8><body style="background:#0b0d14;color:#9aa3b2;font:15px -apple-system,sans-serif;padding:40px 20px">오프라인 — 아직 이 화면은 저장된 적이 없습니다.', { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

async function swr(req) {
  const c = await caches.open(SHELL), hit = await c.match(req);
  const net = fetch(req).then(res => { if (cacheable(res)) c.put(req, res.clone()).catch(() => {}); return res; });
  if (hit) { net.catch(() => {}); return hit; }
  return net;
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin === location.origin) {
    if (url.pathname === '/sw.js') return;
    if (req.mode === 'navigate' || /\.html$/.test(url.pathname)) return e.respondWith(page(req));
    if (isData(url.pathname)) return e.respondWith(networkFirstData(req, url.pathname));
    return e.respondWith(swr(req));
  }
  if (url.hostname === 'cdnjs.cloudflare.com') return e.respondWith(swr(req));
});

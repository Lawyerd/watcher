// [v3.0] 휴대폰 푸시 알림 받기 (서비스 워커). remote_server가 /sw.js로 응답한다.
// 화면이 꺼져 있거나 페이지를 닫아도 알람·가공 완료 알림을 띄우고, 누르면 페이지를 연다.
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "CNC Watcher", {
    body: d.body || "", tag: d.tag, renotify: true, icon: "/icon-192.png", badge: "/icon-192.png",
  }));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(ws => {
    for (const w of ws) if ("focus" in w) return w.focus();
    return clients.openWindow("/");
  }));
});

// [v3.3] 페이지를 휴대폰에 저장해 둔다 — Funnel을 거치면 페이지를 받는 데만 5~15초 걸려(실측) 그동안 까만 화면만 보였다.
// 저장된 것을 바로 보여 주고 새 버전은 뒤에서 받아 다음에 켤 때 반영한다. 페이지에는 데이터가 없고, /api/*는 여기서 다루지 않는다.
const CACHE = "cnc-watcher", SHELL = ["/", "/icon-192.png"];

async function refresh(key) {
  const r = await fetch(key, { cache: "no-store" });
  if (r.ok) await (await caches.open(CACHE)).put(key, r.clone());   // 📡가 꺼져 있을 때의 502로 덮어쓰지 않는다
  return r;
}

self.addEventListener("install", e => {
  self.skipWaiting();
  e.waitUntil(Promise.allSettled(SHELL.map(key => refresh(key))));   // 받지 못해도 설치한다 (알림까지 막히지 않게)
});
self.addEventListener("activate", e => e.waitUntil(clients.claim()));

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url), key = url.pathname === "/index.html" ? "/" : url.pathname;
  if (e.request.method !== "GET" || url.origin !== location.origin || !SHELL.includes(key)) return;
  e.respondWith(caches.open(CACHE).then(c => c.match(key)).then(hit => {
    const net = refresh(key);
    if (!hit) return net;
    e.waitUntil(net.catch(() => {}));
    return hit;
  }));
});

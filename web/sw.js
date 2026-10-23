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

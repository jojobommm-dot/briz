// Service worker кафе «Бриз». Отдаётся с корня (/sw.js), поэтому управляет всем сайтом.
// Шаблон: версия кеша и список файлов подставляются сервером, так что любая
// правка CSS/JS меняет версию — браузер ставит новый воркер и чистит старый кеш.
"use strict";

const VERSION = "{{ version }}";
const SHELL = `briz-shell-${VERSION}`;
const PAGES = `briz-pages-${VERSION}`;
const IMAGES = "briz-images";  // фото не зависят от версии кода
const OFFLINE_URL = "/offline";

// Без чего приложение не откроется без сети: стили, скрипт, иконки и главные страницы
const PRECACHE = {{ precache|tojson }};

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== SHELL && k !== PAGES && k !== IMAGES).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// Сколько фото держать в кеше: на телефоне место не бесконечное
const MAX_IMAGES = 60;
async function trimImages() {
  const cache = await caches.open(IMAGES);
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - MAX_IMAGES; i++) await cache.delete(keys[i]);
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;  // заявки и заказы — только по сети
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // шрифты Google и карта — как браузер решит
  // Служебные разделы и API не кешируем никогда: там живые данные
  if (url.pathname.startsWith("/manage") || url.pathname.startsWith("/api")) return;

  // Страницы: сначала сеть (меню и цены должны быть свежими), без сети — из кеша
  if (req.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        if (fresh.ok) {
          const cache = await caches.open(PAGES);
          cache.put(url.pathname, fresh.clone());
        }
        return fresh;
      } catch {
        return (await caches.match(url.pathname)) || (await caches.match(OFFLINE_URL));
      }
    })());
    return;
  }

  // Фото: сразу из кеша, в фоне обновляем
  if (url.pathname.startsWith("/static/img/")) {
    event.respondWith((async () => {
      const cache = await caches.open(IMAGES);
      const cached = await cache.match(req);
      const network = fetch(req).then((res) => {
        if (res.ok) cache.put(req, res.clone()).then(trimImages);
        return res;
      }).catch(() => cached);
      return cached || network;
    })());
    return;
  }

  // Остальная статика (CSS, JS, иконки): адреса с ?v=…, поэтому кеш навсегда
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req).then((res) => {
        if (res.ok) caches.open(SHELL).then((c) => c.put(req, res.clone()));
        return res;
      }))
    );
  }
});

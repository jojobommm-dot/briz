// Кафе «Бриз»: мобильное меню, слайдер, меню недели, кнопка чата,
// калькулятор банкета, разделы меню.
"use strict";

(function () {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // --- мобильное меню ---
  const burger = document.querySelector(".burger");
  const nav = document.getElementById("nav");
  if (burger && nav) {
    burger.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      burger.setAttribute("aria-expanded", String(open));
    });
  }

  // --- слайдер первого экрана: чёрточки внизу, автопрокрутка, свайп ---
  const slider = document.querySelector("[data-slider]");
  if (slider) {
    const slides = [...slider.querySelectorAll(".hero__slide")];
    const dots = [...slider.querySelectorAll("[data-go]")];
    const SLIDE_MS = 7000;
    let index = 0;
    let timer = null;

    const show = (i) => {
      const prev = slides[index];
      prev.classList.remove("is-active");
      prev.setAttribute("aria-hidden", "true");
      prev.querySelectorAll("a").forEach((a) => a.setAttribute("tabindex", "-1"));
      dots[index].classList.remove("is-active");
      index = (i + slides.length) % slides.length;
      slides[index].classList.add("is-active");
      slides[index].removeAttribute("aria-hidden");
      slides[index].querySelectorAll("a").forEach((a) => a.removeAttribute("tabindex"));
      dots[index].classList.add("is-active");
    };
    const play = () => {
      if (reducedMotion || slides.length < 2) return;
      clearInterval(timer);
      timer = setInterval(() => show(index + 1), SLIDE_MS);
    };
    const pause = () => { clearInterval(timer); timer = null; };

    dots.forEach((d) => d.addEventListener("click", () => { show(Number(d.dataset.go)); play(); }));
    slider.addEventListener("focusin", pause);
    slider.addEventListener("focusout", play);
    let startX = null;
    slider.addEventListener("touchstart", (e) => { startX = e.touches[0].clientX; }, { passive: true });
    slider.addEventListener("touchend", (e) => {
      if (startX === null) return;
      const dx = e.changedTouches[0].clientX - startX;
      if (Math.abs(dx) > 50) { show(index + (dx < 0 ? 1 : -1)); play(); }
      startX = null;
    });
    document.addEventListener("visibilitychange", () => (document.hidden ? pause() : play()));
    play();
  }

  // --- меню недели: стрелки, счётчик 01/05 и полоса ---
  const week = document.querySelector("[data-week]");
  if (week) {
    const slides = [...week.querySelectorAll(".week__slide")];
    const current = week.querySelector("[data-week-current]");
    const bar = week.querySelector("[data-week-bar]");
    // Открываем на сегодняшнем дне недели (пн–пт), в выходные — на понедельнике
    const today = new Date().getDay();  // 0 — воскресенье
    let index = today >= 1 && today <= slides.length ? today - 1 : 0;
    const show = (i) => {
      slides.forEach((s, k) => {
        s.classList.toggle("is-active", k === i);
        if (k === i) s.removeAttribute("aria-hidden"); else s.setAttribute("aria-hidden", "true");
      });
      index = i;
      current.textContent = String(i + 1).padStart(2, "0");
      bar.style.width = `${((i + 1) / slides.length) * 100}%`;
    };
    week.querySelector("[data-week-prev]").addEventListener("click", () => show((index - 1 + slides.length) % slides.length));
    week.querySelector("[data-week-next]").addEventListener("click", () => show((index + 1) % slides.length));
    show(index);
  }

  // Прошедшие даты в календарях не предлагаем
  document.querySelectorAll("[data-min-today]").forEach((el) => {
    const d = new Date();
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    el.min = d.toISOString().slice(0, 10);
  });

  // --- кнопка чата (сам чат — шаг 4) ---
  const chat = document.querySelector("[data-chat]");
  if (chat) {
    const toggle = chat.querySelector(".chat__toggle");
    const panel = chat.querySelector(".chat__panel");
    const setOpen = (open) => {
      panel.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
    };
    toggle.addEventListener("click", () => setOpen(panel.hidden));
    chat.querySelector(".chat__close").addEventListener("click", () => setOpen(false));
    document.querySelectorAll("[data-chat-open]").forEach((btn) => btn.addEventListener("click", () => setOpen(true)));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
  }

  // --- калькулятор банкета ---
  const calc = document.querySelector("[data-calc]");
  if (calc) {
    const guests = calc.querySelector("#guests");
    const totalEl = calc.querySelector("[data-total]");
    const hintEl = calc.querySelector("[data-total-hint]");
    const dateEl = calc.querySelector("#event_date");
    const min = Number(guests.min) || 1;
    const max = Number(guests.max) || 35;
    const rub = (n) => n.toLocaleString("ru-RU") + " ₽";

    // Прошедшие даты в календаре не предлагаем
    const today = new Date();
    today.setMinutes(today.getMinutes() - today.getTimezoneOffset());
    dateEl.min = today.toISOString().slice(0, 10);

    const recalc = () => {
      const picked = calc.querySelector('input[name="package"]:checked');
      const n = Math.round(Number(guests.value));
      if (!picked || !(n >= min && n <= max)) {
        totalEl.textContent = "—";
        hintEl.textContent = `Укажите от ${min} до ${max} гостей`;
        return;
      }
      const price = Number(picked.dataset.price);
      totalEl.textContent = rub(price * n);
      hintEl.textContent = `${n} × ${rub(price)}, без алкоголя и доп. услуг`;
    };

    calc.querySelectorAll("[data-step]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const n = (Number(guests.value) || 0) + Number(btn.dataset.step);
        guests.value = Math.min(max, Math.max(min, n));
        recalc();
      });
    });
    calc.addEventListener("input", recalc);
    calc.addEventListener("change", recalc);
    recalc();
  }

  // --- разделы меню: подсвечиваем тот, что сейчас на экране ---
  const chips = document.querySelector("[data-chips]");
  if (chips && "IntersectionObserver" in window) {
    const row = chips.querySelector(".chips__row");
    const links = new Map();
    chips.querySelectorAll("a").forEach((a) => links.set(a.hash.slice(1), a));
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        links.forEach((a) => a.classList.remove("is-active"));
        const active = links.get(entry.target.id);
        if (active) {
          active.classList.add("is-active");
          // Крутим только ленту разделов: scrollIntoView дёргал бы и страницу
          row.scrollTo({ left: active.offsetLeft - (row.clientWidth - active.offsetWidth) / 2, behavior: "smooth" });
        }
      });
    }, { rootMargin: "-140px 0px -60% 0px" });
    links.forEach((_, id) => {
      const section = document.getElementById(id);
      if (section) observer.observe(section);
    });
  }
  // --- PWA: service worker и предложение установить приложение ---
  // В статичной копии на GitHub Pages воркера нет: там нет сервера, который его отдаёт
  if ("serviceWorker" in navigator && !("static" in document.documentElement.dataset)) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js")
        .then(() => console.log("[briz] service worker зарегистрирован"))
        .catch((err) => console.warn("[briz] service worker не зарегистрирован", err));
    });
  }

  const install = document.querySelector("[data-install]");
  if (install) {
    const DISMISS_KEY = "briz-install-dismissed";
    const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
    // localStorage в приватном режиме может бросить исключение — тогда просто показываем
    const dismissedRecently = () => {
      try { return Date.now() - Number(localStorage.getItem(DISMISS_KEY) || 0) < 14 * 864e5; } catch { return false; }
    };
    const hide = (remember) => {
      install.hidden = true;
      if (remember) { try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch { /* ничего */ } }
    };
    install.querySelector("[data-install-close]").addEventListener("click", () => hide(true));

    if (!standalone && !dismissedRecently()) {
      // Android и Chrome на компьютере: браузер сам предлагает установку, мы ловим момент
      let deferred = null;
      window.addEventListener("beforeinstallprompt", (e) => {
        e.preventDefault();
        deferred = e;
        setTimeout(() => { install.hidden = false; }, 4000);  // не с порога, а когда гость осмотрелся
      });
      install.querySelector("[data-install-btn]").addEventListener("click", async () => {
        if (!deferred) return hide(true);
        deferred.prompt();
        const { outcome } = await deferred.userChoice;
        deferred = null;
        hide(outcome !== "accepted");
      });
      window.addEventListener("appinstalled", () => hide(false));

      // iPhone/iPad в Safari: кнопки установки нет, показываем подсказку
      const ua = navigator.userAgent;
      const isIOS = /iPhone|iPad|iPod/.test(ua) || (ua.includes("Macintosh") && "ontouchend" in document);
      const isSafari = /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|YaBrowser/.test(ua);
      if (isIOS && isSafari) {
        install.querySelector("[data-install-hint]").textContent = "Нажмите «Поделиться», затем «На экран Домой»";
        install.querySelector("[data-install-btn]").textContent = "Понятно";
        setTimeout(() => { install.hidden = false; }, 4000);
      }
    }
  }
})();

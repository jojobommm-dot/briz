// Кафе «Бриз»: мобильное меню, кнопка чата, калькулятор банкета, разделы меню.
"use strict";

(function () {
  // --- мобильное меню ---
  const burger = document.querySelector(".burger");
  const nav = document.getElementById("nav");
  if (burger && nav) {
    burger.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      burger.setAttribute("aria-expanded", String(open));
    });
  }

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
})();

// «Бриз»: стол ко времени (/stol) и статус брони (/stol/<token>).
// Данные экрана сервер кладёт в <script id="booking-data">; время, гостей и итог
// предзаказа он проверяет и пересчитывает сам — здесь только предпросмотр.
"use strict";

(function () {
  const rub = (n) => n.toLocaleString("ru-RU") + " ₽";
  const store = {
    get(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* приватный режим */ } },
  };
  const PROFILE_KEY = "briz-profile";  // общий с заказом обедов: имя и телефон
  const BOOKINGS_KEY = "briz-bookings";
  const plural = (n, one, few, many) => {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  };
  const people = (n) => `${n} ${plural(n, "человека", "человека", "человек")}`;

  // ================= экран брони =================
  const root = document.querySelector("[data-booking]");
  if (root) {
    const data = JSON.parse(document.getElementById("booking-data").textContent);
    const $ = (sel) => root.querySelector(sel);
    const dishes = new Map(data.menu.flatMap((c) => c.dishes.map((d) => [d.key, d])));
    // editing — бронь, которую гость сейчас меняет (вместо второй брони)
    const state = { day: null, time: null, guests: 2, cat: data.menu[0].slug, qty: {}, editing: null };
    let mine = [];  // активные брони этого гостя с сервера (/api/my)

    const currentDay = () => data.days.find((d) => d.date === state.day);
    const cart = () => Object.entries(state.qty).filter(([, q]) => q > 0).map(([key, qty]) => ({ dish: dishes.get(key), key, qty }));
    const total = () => cart().reduce((s, c) => s + c.dish.price * c.qty, 0);
    const count = () => cart().reduce((s, c) => s + c.qty, 0);

    function renderDays() {
      const nav = $("[data-days]");
      nav.innerHTML = "";
      data.days.forEach((d) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "day";
        b.disabled = !d.times.length;
        b.setAttribute("aria-pressed", String(d.date === state.day));
        b.innerHTML = `<b>${d.label}</b><span>${d.times.length ? d.short : "бронь закрыта"}</span>`;
        b.addEventListener("click", () => { state.day = d.date; render(); });
        nav.appendChild(b);
      });
    }

    function renderTimes() {
      const times = currentDay().times;
      if (!times.includes(state.time)) state.time = times.find((t) => t >= "18:00") || times[0] || null;
      const box = $("[data-times]");
      box.innerHTML = "";
      times.forEach((t) => {
        const label = document.createElement("label");
        label.className = "choice";
        label.innerHTML = `<input type="radio" name="time" value="${t}" ${t === state.time ? "checked" : ""}><span>${t}</span>`;
        label.querySelector("input").addEventListener("change", () => { state.time = t; renderBar(); });
        box.appendChild(label);
      });
      $("[data-no-times]").hidden = times.length > 0;
      // Выбранное время — в поле зрения ленты, страницу при этом не двигаем
      const on = box.querySelector("input:checked");
      if (on) {
        const r = on.parentElement.getBoundingClientRect(), b = box.getBoundingClientRect();
        box.scrollLeft += r.left - b.left - (b.width - r.width) / 2;
      }
    }

    function renderCats() {
      const nav = $("[data-cats]");
      nav.innerHTML = "";
      data.menu.forEach((c) => {
        const picked = c.dishes.reduce((n, d) => n + (state.qty[d.key] || 0), 0);
        const b = document.createElement("button");
        b.type = "button";
        b.className = "book-cat";
        b.setAttribute("aria-pressed", String(c.slug === state.cat));
        b.innerHTML = c.title + (picked ? ` <i>${picked}</i>` : "");
        b.addEventListener("click", () => { state.cat = c.slug; renderCats(); renderDishes(); });
        nav.appendChild(b);
      });
    }

    function renderDishes() {
      const cat = data.menu.find((c) => c.slug === state.cat);
      const ul = $("[data-dishes]");
      ul.innerHTML = "";
      cat.dishes.forEach((d) => {
        const q = state.qty[d.key] || 0;
        const li = document.createElement("li");
        li.className = "opt" + (q ? " is-picked" : "");
        li.innerHTML = `
          <div class="opt__info">
            <h3 class="opt__title"></h3>
            <p class="opt__parts"></p>
          </div>
          <div class="opt__buy">
            <span class="opt__price">${rub(d.price)}</span>
            ${q
              ? `<div class="qty"><button type="button" data-dec aria-label="Меньше">−</button><span>${q}</span><button type="button" data-inc aria-label="Больше">+</button></div>`
              : `<button type="button" class="opt__add" data-inc>Добавить</button>`}
          </div>`;
        // Названия и состав — текстом: в них кавычки «» и прочее, не HTML
        li.querySelector(".opt__title").textContent = d.name;
        li.querySelector(".opt__parts").textContent = [d.weight, d.note].filter(Boolean).join(" · ");
        li.querySelectorAll("[data-inc]").forEach((b) => b.addEventListener("click", () => {
          state.qty[d.key] = Math.min(data.maxQty, q + 1); renderCats(); renderDishes(); renderBar();
        }));
        li.querySelectorAll("[data-dec]").forEach((b) => b.addEventListener("click", () => {
          state.qty[d.key] = Math.max(0, q - 1); renderCats(); renderDishes(); renderBar();
        }));
        ul.appendChild(li);
      });
    }

    function renderBar() {
      const d = currentDay();
      $("[data-bar-when]").textContent = state.time
        ? `Стол на ${state.guests} · ${d.label.toLowerCase()}, ${state.time}`
        : "Выберите день и время";
      const n = count();
      $("[data-bar-sum]").textContent = n ? `Предзаказ ${rub(total())}` : "Без предзаказа";
      $("[data-checkout]").disabled = !state.time;
      $("[data-checkout]").textContent = state.editing ? "Сохранить" : "Оформить";
    }

    function render() { renderDays(); renderTimes(); renderCats(); renderDishes(); renderBar(); }

    // ---- гости ----
    const guestsInput = $("[data-guests]");
    const setGuests = (n) => {
      state.guests = Math.min(data.maxGuests, Math.max(1, Number(n) || 1));
      guestsInput.value = state.guests;
      renderBar();
    };
    $("[data-guests-dec]").addEventListener("click", () => setGuests(state.guests - 1));
    $("[data-guests-inc]").addEventListener("click", () => setGuests(state.guests + 1));
    guestsInput.addEventListener("change", () => setGuests(guestsInput.value));

    // ---- оформление ----
    const sheet = $("[data-sheet]");
    const form = $("[data-form]");
    const showErrors = (errors) => {
      root.querySelectorAll("[data-err]").forEach((el) => {
        const msg = errors[el.dataset.err];
        el.hidden = !msg;
        el.textContent = msg || "";
      });
    };

    // Плашка «уже есть заказ»: текст и кнопки [подпись, главная ли, действие]
    function renderDup(text, actions) {
      $("[data-dup-text]").textContent = text;
      const box = $("[data-dup-actions]");
      box.innerHTML = "";
      actions.forEach(([label, primary, act]) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = primary ? "opt__add" : "linklike";
        b.textContent = label;
        b.addEventListener("click", act);
        box.appendChild(b);
      });
      $("[data-dup]").hidden = false;
      $("[data-dup]").scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    // Сервер нашёл незавершённую бронь на этот номер и день — спрашиваем, что делать
    function showDuplicate(d) {
      const what = `бронь №${d.number} на ${d.dayLabel}, ${d.time}, стол на ${people(d.guests)} — «${d.statusLabel}»`;
      const text = (d.token ? `У вас уже есть ${what}.` : `На номер ${d.phone} уже есть ${what}.`) +
        (d.canReplace ? "" : " Изменить её можно по телефону.");
      const actions = [];
      if (d.token && d.canReplace) {
        actions.push(["Изменить её", true, async () => {
          const b = await (await fetch(`/api/bookings/${d.token}`)).json();
          sheet.close();
          startEdit(b);
        }]);
      } else if (d.canReplace) {
        actions.push(["Заменить её этой бронью", true, () => send({ replace: d.number })]);
      } else if (d.token) {
        actions.push(["Открыть её", true, () => { location.href = `/stol/${d.token}`; }]);
      }
      actions.push(["Это другая бронь — забронировать ещё стол", false, () => send({ duplicate: "new" })]);
      renderDup(text, actions);
    }
    let me = { loggedIn: false };

    function renderSheet() {
      const d = currentDay();
      const ed = state.editing;
      $("[data-sheet-title]").textContent = ed ? `Изменение брони №${ed.number}` : "Бронь стола";
      // Уже есть своя бронь на этот день — сразу предлагаем изменить её, а не бронировать второй стол
      const dup = !ed && mine.find((b) => b.day === state.day && b.canEdit);
      $("[data-dup]").hidden = true;
      if (dup) {
        renderDup(`На ${d.label.toLowerCase()} у вас уже есть бронь №${dup.number}: ${dup.time}, стол на ${people(dup.guests)}.`,
          [["Изменить её", true, () => { sheet.close(); startEdit(dup); }]]);
      }
      $("[data-summary]").textContent = `${d.label}, ${d.short}, ${state.time} · стол на ${people(state.guests)}`;
      const pre = $("[data-pre]");
      pre.innerHTML = "";
      cart().forEach((c) => {
        const li = document.createElement("li");
        li.innerHTML = `<span></span><b>${rub(c.dish.price * c.qty)}</b>`;
        li.querySelector("span").textContent = c.dish.name + (c.qty > 1 ? ` × ${c.qty}` : "");
        pre.appendChild(li);
      });
      if (cart().length) {
        const li = document.createElement("li");
        li.className = "book-pre__total";
        li.innerHTML = `<span>Предзаказ к ${state.time}</span><b>${rub(total())}</b>`;
        pre.appendChild(li);
      }
      pre.hidden = !cart().length;
      const p = me.loggedIn ? { name: me.name, phone: me.phone } : store.get(PROFILE_KEY, {});
      ["name", "phone"].forEach((k) => { if (p[k] && !form[k].value) form[k].value = p[k]; });
      $("[data-login-hint]").hidden = me.loggedIn;
      $("[data-submit]").textContent = submitLabel();
      showErrors({});
    }

    const submitLabel = () => {
      if (state.editing) return cart().length ? `Сохранить · ${rub(total())}` : "Сохранить изменения";
      return cart().length ? `Забронировать · ${rub(total())}` : "Забронировать стол";
    };
    $("[data-checkout]").addEventListener("click", () => { if (state.time) { renderSheet(); sheet.showModal(); } });
    $("[data-close]").addEventListener("click", () => sheet.close());
    sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.close(); });

    async function send(extra = {}) {
      const btn = $("[data-submit]");
      btn.disabled = true;
      btn.textContent = "Отправляем…";
      const payload = {
        ...extra,
        known: store.get(BOOKINGS_KEY, []).map((m) => m.token).slice(0, 20),
        day: state.day, time: state.time, guests: state.guests,
        name: form.name.value, phone: form.phone.value, comment: form.comment.value,
        items: cart().map((c) => ({ key: c.key, qty: c.qty })),
      };
      try {
        const ed = state.editing;
        const res = await fetch(ed ? `/api/bookings/${ed.token}` : "/api/bookings", {
          method: ed ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
        });
        const body = await res.json();
        if (res.status === 409 && body.duplicate) { showErrors({}); showDuplicate(body.duplicate); return; }
        if (!res.ok) { showErrors(body.errors || { form: "Не получилось отправить — попробуйте ещё раз" }); return; }
        const prev = store.get(PROFILE_KEY, {});
        store.set(PROFILE_KEY, { ...prev, name: payload.name, phone: payload.phone });
        const known = store.get(BOOKINGS_KEY, []).filter((m) => m.token !== body.token);
        store.set(BOOKINGS_KEY, [{ token: body.token, at: Date.now() }, ...known].slice(0, 20));
        location.href = body.url;
      } catch {
        showErrors({ form: "Нет связи с кафе. Проверьте интернет или позвоните нам." });
      } finally {
        btn.disabled = false;
        btn.textContent = submitLabel();
      }
    }
    form.addEventListener("submit", (e) => { e.preventDefault(); send(); });

    // ---- ваши брони: активные — изменить вместо второй брони ----
    async function loadMine() {
      const tokens = store.get(BOOKINGS_KEY, []).map((m) => m.token).slice(0, 20).join(",");
      try {
        const r = await fetch(`/api/my?tokens=${encodeURIComponent(tokens)}`);
        mine = r.ok ? (await r.json()).bookings : [];
      } catch { mine = []; }
      renderMine();
    }

    function renderMine() {
      const list = $("[data-mine-list]");
      list.innerHTML = "";
      mine.forEach((b) => {
        const li = document.createElement("li");
        li.className = "mine__item" + (state.editing && state.editing.token === b.token ? " is-editing" : "");
        li.innerHTML = `
          <a href="/stol/${b.token}"><b>№${b.number} · ${b.dayLabel}, ${b.time}</b><span></span></a>
          <span class="mine__status mine__status--${b.status}">${b.statusLabel}</span>
          ${b.canEdit ? `<button type="button" class="opt__add" data-edit>Изменить</button>` : ""}`;
        li.querySelector("a span").textContent = `Стол на ${people(b.guests)} · ` +
          (b.items.length ? `предзаказ ${rub(b.total)}` : "без предзаказа");
        const e = li.querySelector("[data-edit]");
        if (e) e.addEventListener("click", () => startEdit(b));
        list.appendChild(li);
      });
      $("[data-mine]").hidden = !mine.length;
    }

    function startEdit(b) {
      state.editing = b;
      if (data.days.some((d) => d.date === b.day && d.times.length)) state.day = b.day;
      state.time = b.time;
      state.qty = {};
      b.items.forEach((i) => { if (dishes.has(i.key)) state.qty[i.key] = i.qty; });
      ["name", "phone", "comment"].forEach((k) => { form[k].value = b[k] || ""; });
      setGuests(b.guests);
      const again = b.status === "confirmed" ? " После сохранения менеджер подтвердит бронь заново." : "";
      $("[data-editing-text]").textContent = `Изменяете бронь №${b.number} на ${b.dayLabel}, ${b.time}.${again}`;
      $("[data-editing]").hidden = false;
      render();
      renderMine();
      window.scrollTo({ top: $("[data-editing]").getBoundingClientRect().top + scrollY - 110, behavior: "smooth" });
    }

    $("[data-edit-cancel]").addEventListener("click", () => {
      state.editing = null;
      state.qty = {};
      form.comment.value = "";
      $("[data-editing]").hidden = true;
      history.replaceState(null, "", "/stol");
      render();
      renderMine();
    });

    state.day = (data.days.find((d) => d.times.length) || data.days[0]).date;
    render();
    loadMine();
    fetch("/api/me").then((r) => r.json()).then((d) => { me = d; }).catch(() => {});
    // «Изменить бронь» со страницы брони ведёт сюда с ?edit=<token>
    const editToken = new URLSearchParams(location.search).get("edit");
    if (editToken) {
      fetch(`/api/bookings/${encodeURIComponent(editToken)}`).then((r) => (r.ok ? r.json() : null)).then((b) => {
        if (b && b.canEdit) startEdit(b); else if (b) location.replace(`/stol/${b.token}`);
      }).catch(() => {});
    }
  }

  // ================= статус брони =================
  const status = document.querySelector("[data-booking-status]");
  if (status) {
    const token = status.dataset.token;
    const apply = (b) => {
      status.querySelector("[data-st-label]").textContent = b.statusLabel;
      const keys = b.flow.map((f) => f.key);
      const at = keys.indexOf(b.status);
      status.querySelectorAll("[data-step]").forEach((li, i) => {
        li.classList.toggle("is-done", at >= 0 && i < at);
        li.classList.toggle("is-current", i === at);
      });
      status.querySelector("[data-cancelled]").hidden = b.status !== "cancelled";
      status.querySelector("[data-cancel]").hidden = !b.canCancel;
      status.querySelector("[data-edit]").hidden = !b.canEdit;
      return b.status === "done" || b.status === "cancelled";
    };
    const mine = store.get(BOOKINGS_KEY, []);
    if (!mine.some((m) => m.token === token)) store.set(BOOKINGS_KEY, [{ token, at: Date.now() }, ...mine].slice(0, 20));

    let finished = apply(JSON.parse(document.getElementById("booking-status").textContent));
    // Бронь подтверждает менеджер — опрашиваем раз в 30 секунд, пока она не закрыта
    const timer = setInterval(async () => {
      if (finished || document.hidden) return;
      try {
        const r = await fetch(`/api/bookings/${token}`);
        if (r.ok) finished = apply(await r.json());
      } catch { /* нет связи — попробуем в следующий раз */ }
      if (finished) clearInterval(timer);
    }, 30000);

    status.querySelector("[data-cancel]").addEventListener("click", async () => {
      if (!confirm("Отменить бронь?")) return;
      const r = await fetch(`/api/bookings/${token}/cancel`, { method: "POST" });
      const body = await r.json();
      if (r.ok) finished = apply(body); else alert(body.error || "Не получилось отменить — позвоните в кафе");
    });
  }
})();

// Приложение «Бриз»: заказ обедов (/zakaz) и статус заказа (/zakaz/<token>).
// Данные экрана сервер кладёт в <script id="order-data">, цены и итог
// пересчитывает сам при оформлении — здесь только предпросмотр.
"use strict";

(function () {
  const rub = (n) => n.toLocaleString("ru-RU") + " ₽";
  const store = {
    get(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* приватный режим */ } },
  };
  const ORDERS_KEY = "briz-orders";    // мои заказы: [{token, at}]
  const PROFILE_KEY = "briz-profile";  // имя, телефон, адрес — чтобы не вводить заново
  const plural = (n, one, few, many) => {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  };

  // ================= экран заказа =================
  const root = document.querySelector("[data-order]");
  if (root) {
    const data = JSON.parse(document.getElementById("order-data").textContent);
    const $ = (sel) => root.querySelector(sel);
    const state = { mode: "delivery", day: null, qty: {}, slot: null };

    const firstOpenDay = (mode) => data.days.find((d) => d.open[mode]) || data.days.find((d) => d.menu);
    // Что сегодня: обедов нет (выходной), приём закрыт или до скольки ещё можно
    const todayNote = () => {
      const t = data.days[0];
      if (!t.menu) return "Сегодня выходной — комплексные обеды по будням, заказ на ближайший рабочий день.";
      if (!t.open[state.mode]) return "На сегодня приём уже закрыт — выберите другой день.";
      return `На сегодня — до ${data.cutoff[state.mode]}.`;
    };
    const currentDay = () => data.days.find((d) => d.date === state.day);
    const priceOf = (opt) => opt.price[state.mode];
    const cart = () => data.options.filter((o) => state.qty[o.kind] > 0).map((o) => ({ opt: o, qty: state.qty[o.kind] }));
    const total = () => cart().reduce((s, c) => s + priceOf(c.opt) * c.qty, 0);
    const count = () => cart().reduce((s, c) => s + c.qty, 0);

    // Подписи способов получения: заголовок, пояснение, время, оплата
    const MODE_TEXT = {
      delivery: {
        label: "Доставка", title: "с доставкой", legend: "Время доставки", pay: "Оплата курьеру — наличными или картой.",
        hint: "Позвонить на ресепшн, без лука…",
        about: "Привезём к выбранному времени — закажите минимум за час.",
      },
      pickup: {
        label: "Самовывоз", title: "с собой", legend: "Когда заберёте", pay: "Оплата при получении — наличными или картой.",
        hint: "Без лука, суп отдельно…",
        about: "Заберите в кафе с собой: соберём к выбранному времени, закажите минимум за полчаса.",
      },
      hall: {
        label: "В кафе<br>ко времени", title: "ко времени", legend: "Во сколько придёте", pay: "Оплата в кафе после обеда — наличными или картой.",
        hint: "Столик у окна, детский стул, без лука…",
        about: "Придёте — а обед уже на столе. Закажите минимум за полчаса.",
      },
    };
    const text = () => MODE_TEXT[state.mode];
    const slotsOpen = () => currentDay().slots[state.mode];

    function renderMode() {
      root.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.mode === state.mode)));
      $("[data-cutoff]").textContent = `${text().about} ${todayNote()}`;
      $(".app__title span:last-child").textContent = text().title;
      if (!currentDay() || !currentDay().open[state.mode]) state.day = firstOpenDay(state.mode).date;
    }

    function renderDays() {
      const nav = $("[data-days]");
      nav.innerHTML = "";
      data.days.forEach((d) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "day";
        b.disabled = !d.open[state.mode];
        b.setAttribute("aria-pressed", String(d.date === state.day));
        b.innerHTML = `<b>${d.label}</b><span>${d.open[state.mode] ? d.short : d.menu ? "приём закрыт" : "обедов нет"}</span>`;
        b.addEventListener("click", () => { state.day = d.date; render(); });
        nav.appendChild(b);
      });
    }

    function renderToday() {
      const d = currentDay();
      $("[data-today-img]").src = `/static/img/${d.image}`;
      $("[data-today-label]").textContent = `${d.label} · ${d.short}`;
      root.querySelectorAll("[data-dish]").forEach((el) => { el.textContent = d.menu[el.dataset.dish]; });
    }

    function renderOptions() {
      const d = currentDay();
      const ul = $("[data-options]");
      ul.innerHTML = "";
      data.options.forEach((o) => {
        const q = state.qty[o.kind] || 0;
        const li = document.createElement("li");
        li.className = "opt" + (q ? " is-picked" : "");
        li.innerHTML = `
          <div class="opt__info">
            <h3 class="opt__title">${o.title}</h3>
            <p class="opt__parts">${o.parts.map((p) => d.menu[p]).join(" · ")}</p>
          </div>
          <div class="opt__buy">
            <span class="opt__price">${rub(priceOf(o))}</span>
            ${q
              ? `<div class="qty"><button type="button" data-dec aria-label="Меньше">−</button><span>${q}</span><button type="button" data-inc aria-label="Больше">+</button></div>`
              : `<button type="button" class="opt__add" data-inc>В заказ</button>`}
          </div>`;
        li.querySelectorAll("[data-inc]").forEach((b) => b.addEventListener("click", () => {
          state.qty[o.kind] = Math.min(data.maxQty, q + 1); render();
        }));
        li.querySelectorAll("[data-dec]").forEach((b) => b.addEventListener("click", () => {
          state.qty[o.kind] = Math.max(0, q - 1); render();
        }));
        ul.appendChild(li);
      });
    }

    function renderCart() {
      const n = count();
      $("[data-cartbar]").hidden = n === 0;
      $("[data-cart-count]").textContent = `${n} ${plural(n, "позиция", "позиции", "позиций")} · ${currentDay().label.toLowerCase()}`;
      $("[data-cart-sum]").textContent = rub(total());
    }

    function render() { renderMode(); renderDays(); renderToday(); renderOptions(); renderCart(); }

    const setMode = (m) => { state.mode = m; state.slot = null; render(); };
    root.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));

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

    function renderSheet() {
      // Способ получения — и здесь: шапку страницы легко проскроллить и не заметить
      const modes = $("[data-sheet-modes]");
      modes.innerHTML = "";
      Object.keys(MODE_TEXT).forEach((m) => {  // порядок — как в шапке; JSON с сервера ключи сортирует
        const label = document.createElement("label");
        label.className = "choice";
        label.innerHTML = `<input type="radio" name="mode" value="${m}" ${m === state.mode ? "checked" : ""}><span>${MODE_TEXT[m].label}</span>`;
        label.querySelector("input").addEventListener("change", () => { setMode(m); renderSheet(); });
        modes.appendChild(label);
      });
      const d = currentDay();
      $("[data-summary]").textContent =
        `${d.label}, ${d.short} · ` +
        cart().map((c) => c.opt.title + (c.qty > 1 ? ` × ${c.qty}` : "")).join(", ");
      $("[data-slot-legend]").textContent = text().legend;
      $("[data-pay]").textContent = text().pay;
      form.comment.placeholder = text().hint;
      // На сегодня — только время, к которому кухня ещё успеет
      const open = slotsOpen();
      if (!open.includes(state.slot)) state.slot = open[0] || null;
      const slots = $("[data-slots]");
      slots.innerHTML = "";
      open.forEach((s) => {
        const label = document.createElement("label");
        label.className = "choice";
        label.innerHTML = `<input type="radio" name="slot" value="${s}" ${s === state.slot ? "checked" : ""}><span>${s}</span>`;
        label.querySelector("input").addEventListener("change", () => { state.slot = s; });
        slots.appendChild(label);
      });
      $("[data-address-field]").hidden = state.mode !== "delivery";
      $("[data-guests-field]").hidden = state.mode !== "hall";
      // Гостей по умолчанию — сколько обедов с супом или вторым: обычно один на человека
      if (!guestsTouched) form.guests.value = Math.min(data.maxGuests, Math.max(1, cart()
        .filter((c) => c.opt.parts.includes("main") || c.opt.parts.includes("soup")).reduce((n, c) => n + c.qty, 0)));
      $("[data-submit]").textContent = `Заказать за ${rub(total())}`;
      // Вошедший гость — данные из кабинета; иначе — что запомнил этот телефон
      const p = me.loggedIn ? { name: me.name, phone: me.phone, address: me.addresses[0] } : store.get(PROFILE_KEY, {});
      ["name", "phone", "address"].forEach((k) => { if (p[k] && !form[k].value) form[k].value = p[k]; });
      $("[data-login-hint]").hidden = me.loggedIn;
      const chips = $("[data-addr-chips]");
      chips.innerHTML = "";
      (me.addresses || []).forEach((a) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "addr-chip" + (form.address.value === a ? " is-on" : "");
        b.textContent = a;
        b.addEventListener("click", () => {
          form.address.value = a;
          chips.querySelectorAll(".addr-chip").forEach((x) => x.classList.toggle("is-on", x === b));
        });
        chips.appendChild(b);
      });
      chips.hidden = !(me.addresses || []).length;
      showErrors({});
    }

    let guestsTouched = false;
    const setGuests = (n) => {
      guestsTouched = true;
      form.guests.value = Math.min(data.maxGuests, Math.max(1, Number(n) || 1));
    };
    $("[data-guests-dec]").addEventListener("click", () => setGuests(Number(form.guests.value) - 1));
    $("[data-guests-inc]").addEventListener("click", () => setGuests(Number(form.guests.value) + 1));
    form.guests.addEventListener("change", () => setGuests(form.guests.value));

    $("[data-checkout]").addEventListener("click", () => { renderSheet(); sheet.showModal(); });
    $("[data-close]").addEventListener("click", () => sheet.close());
    sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.close(); });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = $("[data-submit]");
      btn.disabled = true;
      btn.textContent = "Отправляем…";
      const payload = {
        mode: state.mode, day: state.day, slot: state.slot,
        name: form.name.value, phone: form.phone.value, address: form.address.value, comment: form.comment.value,
        guests: state.mode === "hall" ? Number(form.guests.value) : 0,
        items: cart().map((c) => ({ kind: c.opt.kind, qty: c.qty })),
      };
      try {
        const res = await fetch("/api/orders", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
        });
        const body = await res.json();
        if (!res.ok) { showErrors(body.errors || { form: "Не получилось отправить — попробуйте ещё раз" }); return; }
        store.set(PROFILE_KEY, { name: payload.name, phone: payload.phone, address: payload.address || store.get(PROFILE_KEY, {}).address });
        store.set(ORDERS_KEY, [{ token: body.token, at: Date.now() }, ...store.get(ORDERS_KEY, [])].slice(0, 20));
        location.href = body.url;
      } catch {
        showErrors({ form: "Нет связи с кафе. Проверьте интернет или позвоните нам." });
      } finally {
        btn.disabled = false;
        btn.textContent = `Заказать за ${rub(total())}`;
      }
    });

    // ---- мои заказы: последние три, с кнопкой «Повторить» ----
    async function renderMine() {
      const mine = store.get(ORDERS_KEY, []).slice(0, 3);
      if (!mine.length) return;
      const list = $("[data-mine-list]");
      const results = await Promise.all(mine.map((m) =>
        fetch(`/api/orders/${m.token}`).then((r) => (r.ok ? r.json() : null)).catch(() => null)));
      results.filter(Boolean).forEach((o) => {
        const li = document.createElement("li");
        li.className = "mine__item";
        li.innerHTML = `
          <a href="/zakaz/${o.token}"><b>№${o.number} · ${o.dayLabel}</b>
            <span>${o.items.map((i) => i.title + (i.qty > 1 ? " × " + i.qty : "")).join(", ")} · ${rub(o.total)}</span></a>
          <span class="mine__status mine__status--${o.status}">${o.statusLabel}</span>
          <button type="button" class="opt__add" data-repeat>Повторить</button>`;
        li.querySelector("[data-repeat]").addEventListener("click", () => repeat(o));
        list.appendChild(li);
      });
      $("[data-mine]").hidden = !list.children.length;
    }

    // Повтор заказа: тот же способ получения и те же позиции, день — ближайший открытый
    function repeat(o) {
      state.mode = o.mode;
      state.qty = {};
      o.items.forEach((i) => { state.qty[i.kind] = i.qty; });
      render();
      window.scrollTo({ top: $("[data-options]").offsetTop - 120, behavior: "smooth" });
    }

    let me = { loggedIn: false, addresses: [] };
    state.day = firstOpenDay(state.mode).date;
    render();
    renderMine();
    fetch("/api/me").then((r) => r.json()).then((d) => { me = d; }).catch(() => {});
    // «Повторить» из кабинета ведёт сюда с ?repeat=<token>
    const repeatToken = new URLSearchParams(location.search).get("repeat");
    if (repeatToken) {
      fetch(`/api/orders/${encodeURIComponent(repeatToken)}`).then((r) => (r.ok ? r.json() : null)).then((o) => { if (o) repeat(o); }).catch(() => {});
    }
  }

  // ================= кабинет: подтянуть заказы, сделанные с этого телефона до входа =================
  const cabinet = document.querySelector("[data-cabinet]");
  if (cabinet) {
    const tokens = store.get(ORDERS_KEY, []).map((m) => m.token);
    if (tokens.length) {
      fetch("/api/me/claim", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tokens }) })
        .then((r) => r.json())
        .then((d) => { if (d.claimed > 0) location.reload(); })
        .catch(() => {});
    }
  }

  // ================= статус заказа =================
  const status = document.querySelector("[data-status]");
  if (status) {
    const token = status.dataset.token;
    const apply = (o) => {
      status.querySelector("[data-st-label]").textContent = o.statusLabel;
      const keys = o.flow.map((f) => f.key);
      const at = keys.indexOf(o.status);
      status.querySelectorAll("[data-step]").forEach((li, i) => {
        li.classList.toggle("is-done", at >= 0 && i < at);
        li.classList.toggle("is-current", i === at);
      });
      status.querySelector("[data-cancelled]").hidden = o.status !== "cancelled";
      status.querySelector("[data-cancel]").hidden = !o.canCancel;
      return o.status === "done" || o.status === "cancelled";
    };
    // Если заказ открыли по ссылке не с этого телефона — запомним его здесь
    const mine = store.get(ORDERS_KEY, []);
    if (!mine.some((m) => m.token === token)) store.set(ORDERS_KEY, [{ token, at: Date.now() }, ...mine].slice(0, 20));

    let finished = apply(JSON.parse(document.getElementById("status-data").textContent));
    // Статус меняет менеджер — опрашиваем раз в 20 секунд, пока заказ не закрыт
    const timer = setInterval(async () => {
      if (finished || document.hidden) return;
      try {
        const r = await fetch(`/api/orders/${token}`);
        if (r.ok) finished = apply(await r.json());
      } catch { /* нет связи — попробуем в следующий раз */ }
      if (finished) clearInterval(timer);
    }, 20000);

    status.querySelector("[data-cancel]").addEventListener("click", async () => {
      if (!confirm("Отменить заказ?")) return;
      const r = await fetch(`/api/orders/${token}/cancel`, { method: "POST" });
      const body = await r.json();
      if (r.ok) finished = apply(body); else alert(body.error || "Не получилось отменить — позвоните в кафе");
    });
  }
})();

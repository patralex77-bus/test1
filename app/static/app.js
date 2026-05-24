(() => {
  // ✅ HARD STOP на legacy app.js на страници, където имаш нов custom скрипт
  if (window.__DISABLE_LEGACY_APP_JS__) {
    console.log("legacy app.js disabled on this page ✅");
    return;
  }

  /* =========================
   * ===== API helpers =====
   * ========================= */

  async function fetchPassengers(tripId) {
    const res = await fetch(`/api/trips/${tripId}/passengers`, { credentials: "same-origin" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data?.detail || `fetchPassengers failed: ${res.status}`);
    }
    return await res.json();
  }

  async function patchPassenger(id, payload) {
    const res = await fetch(`/api/passengers/${id}`, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data?.detail || `patchPassenger failed: ${res.status}`);
    }
  }

  async function setBlacklist(passengerId, makeBad) {
    if (makeBad) {
      const reason = prompt("Причина (пример: no-show, abusive, spam):", "no-show");
      if (reason === null) return { ok: false, cancelled: true };

      const res = await fetch(`/api/passengers/${passengerId}/blacklist`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: String(reason || "").trim() || null }),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) return { ok: false, error: data?.detail || res.status };
      return { ok: true };
    }

    if (!confirm("Да махна ли този клиент от черния списък?")) return { ok: false, cancelled: true };

    const res = await fetch(`/api/passengers/${passengerId}/blacklist`, {
      method: "DELETE",
      credentials: "same-origin",
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) return { ok: false, error: data?.detail || res.status };
    return { ok: true };
  }

  /* =========================
   * ===== UI helpers =====
   * ========================= */

  function matchesFilter(p, q, onlyUnchecked, onlyUnpaid) {
    if (onlyUnchecked && p.checkedIn) return false;
    if (onlyUnpaid && p.paid) return false;
    if (!q) return true;

    const s = `${p.fullName ?? ""} ${p.phone ?? ""} ${p.seatNo ?? ""} ${p.passengerNo ?? ""} ${p.voucherRaw ?? ""} ${p.badReason ?? ""}`.toLowerCase();
    return s.includes(q.toLowerCase());
  }

  function el(tag, attrs = {}, children = []) {
    const e = document.createElement(tag);

    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null) continue;

      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = String(v);
      else if (k === "html") e.innerHTML = String(v);
      else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, String(v));
    }

    for (const c of children) {
      e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return e;
  }

  /* =========================
   * ===== money + currency =====
   * ========================= */

  function parseMoney(v) {
    if (v === null || v === undefined) return null;
    if (typeof v === "number") return Number.isFinite(v) ? v : null;

    let s = String(v).trim();
    if (!s) return null;

    s = s.replace(/[^\d.,-]/g, "");
    s = s.replace(/\s+/g, "");
    if (s.includes(",") && s.includes(".")) s = s.replace(/\./g, ""); // 1.200,50 -> 1200,50
    s = s.replace(/,/g, ".");

    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }

  function inferCurrencyFromRaw(raw) {
    const s = String(raw ?? "").toLowerCase();
    if (/(грн|uah|₴|гривн(?:а|и)?)/i.test(s)) return "UAH";
    if (/(євро|евро|eur|€)/i.test(s)) return "EUR";
    return "EUR";
  }

  /**
   * Expected fallback parser:
   * 1) ако има валута -> EUR/UAH
   * 2) ако НЯМА валута: приемаме САМО 1..4 цифри + (.0/.00 или ,0/,00) и <=2000 => EUR
   */
  function parseExpectedFromInfo(raw) {
    const s = String(raw ?? "").trim();
    if (!s) return { due: null, cur: null };
    const low = s.toLowerCase();

    // EUR token
    if (/(€|eur|євро|евро)/iu.test(low)) {
      const m = low.match(/(\d[\d\s]*([.,]\d{1,2})?)/);
      const n = m ? parseMoney(m[1]) : null;
      if (n != null && n > 0 && n <= 2000) return { due: n, cur: "EUR" };
      return { due: null, cur: "EUR" };
    }

    // UAH token
    if (/(uah|грн|гривн(?:а|и)?|₴)/iu.test(low)) {
      const m = low.match(/(\d[\d\s]*([.,]\d{1,2})?)/);
      const n = m ? parseMoney(m[1]) : null;
      if (n != null && n > 0) return { due: n, cur: "UAH" };
      return { due: null, cur: "UAH" };
    }

    // no currency: strict numeric-only EUR
    const m2 = s.match(/^\s*(\d{1,4})(?:[.,](\d{1,2}))?\s*$/);
    if (!m2) return { due: null, cur: null };

    const intPart = m2[1];       // 1..4 digits
    const decPart = m2[2] || ""; // 0..2 digits
    if (decPart && !/^0{1,2}$/.test(decPart)) return { due: null, cur: null };

    const n2 = Number(intPart + (decPart ? "." + decPart : ""));
    if (!Number.isFinite(n2) || n2 <= 0 || n2 > 2000) return { due: null, cur: null };

    return { due: n2, cur: "EUR" };
  }

  /* =========================
   * ===== Summary =====
   * ========================= */

  function renderSummary(list) {
    const fromEl = document.getElementById("sumFrom");
    const toEl = document.getElementById("sumTo");
    const expEUR = document.getElementById("expEUR");
    const expUAH = document.getElementById("expUAH");
    const actEUR = document.getElementById("actEUR");
    const actUAH = document.getElementById("actUAH");
    if (!fromEl || !toEl || !expEUR || !expUAH || !actEUR || !actUAH) return;

    const fromCnt = new Map();
    const toCnt = new Map();

    let expectedEUR = 0, expectedUAH = 0;
    let actualEUR = 0, actualUAH = 0;

    for (const p of list) {
      const f = (p.fromCity ?? "").trim() || "—";
      const t = (p.toCity ?? "").trim() || "—";
      fromCnt.set(f, (fromCnt.get(f) || 0) + 1);
      toCnt.set(t, (toCnt.get(t) || 0) + 1);

      // ✅ EXPECTED:
      // 1) amountDue ако има
      const due = parseMoney(p.amountDue);
      const curDue = String(p.currency || inferCurrencyFromRaw(p.voucherRaw) || "EUR").toUpperCase();

      if (due != null) {
        if (curDue === "UAH") expectedUAH += due;
        else expectedEUR += due;
      } else {
        // 2) fallback от voucherRaw (вкл. 110.00 / 80.00 без валута)
        const ex = parseExpectedFromInfo(p.voucherRaw);
        if (ex.due != null && ex.cur) {
          if (ex.cur === "UAH") expectedUAH += ex.due;
          else expectedEUR += ex.due;
        }
      }

      // ✅ ACTUAL:
      const curAct = String(p.currency || inferCurrencyFromRaw(p.voucherRaw) || "EUR").toUpperCase();
      const paid = parseMoney(p.amount);
      if (paid != null) {
        if (curAct === "UAH") actualUAH += paid;
        else actualEUR += paid;
      }
    }

    const sortMap = (m) => [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

    fromEl.innerHTML =
      sortMap(fromCnt)
        .map(([city, c]) => `<tr><td>${city}</td><td style="text-align:right;font-weight:800">${c}</td></tr>`)
        .join("") || `<tr><td colspan="2" style="color:#999">Няма</td></tr>`;

    toEl.innerHTML =
      sortMap(toCnt)
        .map(([city, c]) => `<tr><td>${city}</td><td style="text-align:right;font-weight:800">${c}</td></tr>`)
        .join("") || `<tr><td colspan="2" style="color:#999">Няма</td></tr>`;

    const fmt = (x) => (Math.round(x * 100) / 100).toFixed(2);

    expEUR.textContent = fmt(expectedEUR);
    expUAH.textContent = fmt(expectedUAH);
    actEUR.textContent = fmt(actualEUR);
    actUAH.textContent = fmt(actualUAH);
  }

  /* =========================
   * ===== Render Table / Cards =====
   * ========================= */

  function renderTable(passengers, onChange, refresh) {
    const tbody = document.getElementById("rows");
    if (!tbody) return;
    tbody.innerHTML = "";

    function td(label, childOrText) {
      return el("td", { "data-label": label }, [childOrText]);
    }

    passengers.forEach((p) => {
      const checked = el("input", { type: "checkbox" });
      checked.checked = !!p.checkedIn;
      checked.addEventListener("change", async () => {
        try {
          await patchPassenger(p.id, { checkedIn: checked.checked });
          p.checkedIn = checked.checked;
          onChange?.();
        } catch (e) {
          checked.checked = !checked.checked;
          alert(String(e?.message || e));
        }
      });

      const paid = el("input", { type: "checkbox" });
      paid.checked = !!p.paid;
      paid.addEventListener("change", async () => {
        try {
          await patchPassenger(p.id, { paid: paid.checked });
          p.paid = paid.checked;
          onChange?.();
        } catch (e) {
          paid.checked = !paid.checked;
          alert(String(e?.message || e));
        }
      });

      const amount = el("input", { type: "number", step: "0.01" });
      amount.className = "amt-input";
      amount.style.width = "90px";
      amount.style.textAlign = "center";
      amount.value = p.amount ?? "";
      amount.addEventListener("change", async () => {
        try {
          const next = amount.value === "" ? null : Number(amount.value);
          await patchPassenger(p.id, { amount: next });
          p.amount = next;
          onChange?.();
        } catch (e) {
          amount.value = p.amount ?? "";
          alert(String(e?.message || e));
        }
      });

      const curSel = el("select", { class: "cur-select" }, [
        el("option", { value: "EUR" }, ["EUR"]),
        el("option", { value: "UAH" }, ["UAH"]),
      ]);
      curSel.value = String(p.currency ?? inferCurrencyFromRaw(p.voucherRaw) ?? "EUR").toUpperCase();
      curSel.addEventListener("change", async () => {
        try {
          await patchPassenger(p.id, { currency: curSel.value });
          p.currency = curSel.value;
          onChange?.();
        } catch (e) {
          curSel.value = String(p.currency ?? "EUR").toUpperCase();
          alert(String(e?.message || e));
        }
      });

      // ✅ ⚠ blacklist cell
      const bl = el("input", { type: "checkbox", class: "bl-check" });
      bl.checked = !!p.badClient;

      const badge = el("span", { class: "warnBadge" + (p.badClient ? " on" : "") }, [p.badClient ? "⚠" : ""]);
      const tipParts = [];
      if (p.badReason) tipParts.push(String(p.badReason));
      if (Number.isFinite(p.badCount) && p.badCount > 0) tipParts.push(`бр. no-show: ${p.badCount}`);
      if (p.badMatchedBy) tipParts.push(`match: ${p.badMatchedBy}`);
      if (tipParts.length) badge.title = tipParts.join(" • ");

      const cnt = el("span", { class: "warnCount" }, [
        (Number.isFinite(p.badCount) && p.badCount > 0) ? `×${p.badCount}` : ""
      ]);

      const warnWrap = el("div", { class: "warnCell" }, [bl, badge, cnt]);

      bl.addEventListener("change", async () => {
        const target = bl.checked;
        bl.disabled = true;

        const r = await setBlacklist(p.id, target);

        if (!r.ok) {
          bl.checked = !target;
          bl.disabled = false;
          if (r.cancelled) return;

          const msg = String(r.error ?? "unknown");
          alert("Грешка: " + msg + (msg.includes("401") ? "\n(Логни се: /admin/login)" : ""));
          return;
        }

        await refresh?.();
        bl.disabled = false;
      });

      const tr = el("tr", {}, [
        td("№", p.passengerNo ?? ""),
        td("От", p.fromCity ?? ""),
        td("До", p.toCity ?? ""),
        td("Име", p.fullName ?? ""),
        td("Телефон", p.phone ?? ""),
        td("Място", p.seatNo ?? ""),
        td("Инфо", p.voucherRaw ?? ""),
        td("Регистр.", checked),
        td("Заплатил", paid),
        td("⚠", warnWrap),
        td("Сума", el("div", { class: "sum-wrap" }, [curSel, amount])),
      ]);

      if (p.badClient) tr.classList.add("badRow");

      tbody.appendChild(tr);
    });
  }

  function renderCards(passengers, onChange, refresh) {
    const root = document.getElementById("cardView");
    if (!root) return;
    root.innerHTML = "";

    passengers.forEach((p) => {
      const checked = el("input", { type: "checkbox" });
      checked.checked = !!p.checkedIn;
      checked.addEventListener("change", async () => {
        try {
          await patchPassenger(p.id, { checkedIn: checked.checked });
          p.checkedIn = checked.checked;
          onChange?.();
        } catch (e) {
          checked.checked = !checked.checked;
          alert(String(e?.message || e));
        }
      });

      const paid = el("input", { type: "checkbox" });
      paid.checked = !!p.paid;
      paid.addEventListener("change", async () => {
        try {
          await patchPassenger(p.id, { paid: paid.checked });
          p.paid = paid.checked;
          onChange?.();
        } catch (e) {
          paid.checked = !paid.checked;
          alert(String(e?.message || e));
        }
      });

      const amount = el("input", { type: "number", step: "0.01" });
      amount.className = "amt-input";
      amount.value = p.amount ?? "";
      amount.addEventListener("change", async () => {
        try {
          const next = amount.value === "" ? null : Number(amount.value);
          await patchPassenger(p.id, { amount: next });
          p.amount = next;
          onChange?.();
        } catch (e) {
          amount.value = p.amount ?? "";
          alert(String(e?.message || e));
        }
      });

      const curSel = el("select", { class: "cur-select" }, [
        el("option", { value: "EUR" }, ["EUR"]),
        el("option", { value: "UAH" }, ["UAH"]),
      ]);
      curSel.value = String(p.currency ?? inferCurrencyFromRaw(p.voucherRaw) ?? "EUR").toUpperCase();
      curSel.addEventListener("change", async () => {
        try {
          await patchPassenger(p.id, { currency: curSel.value });
          p.currency = curSel.value;
          onChange?.();
        } catch (e) {
          curSel.value = String(p.currency ?? "EUR").toUpperCase();
          alert(String(e?.message || e));
        }
      });

      // ⚠ in cards (малък checkbox)
      const bl = el("input", { type: "checkbox", class: "bl-check" });
      bl.checked = !!p.badClient;
      bl.addEventListener("change", async () => {
        const target = bl.checked;
        bl.disabled = true;

        const r = await setBlacklist(p.id, target);
        if (!r.ok) {
          bl.checked = !target;
          bl.disabled = false;
          if (r.cancelled) return;

          const msg = String(r.error ?? "unknown");
          alert("Грешка: " + msg + (msg.includes("401") ? "\n(Логни се: /admin/login)" : ""));
          return;
        }

        await refresh?.();
        bl.disabled = false;
      });

      const warnLine = el("div", { class: "p-sub muted" }, [
        el("span", { class: "warnCell" }, [
          bl,
          el("span", { class: "warnBadge" + (p.badClient ? " on" : "") }, [p.badClient ? "⚠" : ""]),
          el("span", { class: "warnCount" }, [
            (Number.isFinite(p.badCount) && p.badCount > 0) ? `×${p.badCount}` : ""
          ]),
          el("span", { class: "muted" }, [p.badReason ? ` ${p.badReason}` : ""]),
        ])
      ]);

      root.appendChild(
        el("div", { class: "p-card" }, [
          el("div", { class: "p-title" }, [(p.fullName ?? "—") + (p.seatNo ? ` • място ${p.seatNo}` : "")]),
          el("div", { class: "p-sub" }, [`${p.fromCity ?? ""} → ${p.toCity ?? ""}`]),
          el("div", { class: "p-sub" }, [p.phone ?? ""]),
          el("div", { class: "p-sub muted" }, [p.voucherRaw ?? ""]),
          warnLine,
          el("div", { class: "p-actions" }, [
            el("label", {}, [checked, " Регистр."]),
            el("label", {}, [paid, " Заплатил"]),
            el("label", {}, ["Сума ", el("span", { class: "sum-wrap" }, [curSel, amount])]),
          ]),
        ])
      );
    });
  }

  /* =========================
   * ===== Main =====
   * ========================= */

  async function main() {
    const tripId = window.TRIP_ID;
    if (!tripId) return;

    const search = document.getElementById("search");
    const onlyUnchecked = document.getElementById("onlyUnchecked");
    const onlyUnpaid = document.getElementById("onlyUnpaid");
    const toggle = document.getElementById("toggleView");
    const printBtn = document.getElementById("printBtn");
    const tableView = document.getElementById("tableView");
    const cardView = document.getElementById("cardView");

    const importForm = document.getElementById("importForm");
    const status = document.getElementById("importStatus");

    const renumberBtn = document.getElementById("renumber");
    const saveBtn = document.getElementById("saveBtn");
    const saveStatus = document.getElementById("saveStatus");

    let view = "table";
    let passengers = [];

    const refreshPassengers = async () => {
      passengers = await fetchPassengers(tripId);
      rerender();
    };

    const rerender = () => {
      const q = (search?.value ?? "").trim();
      const filtered = passengers.filter((p) =>
        matchesFilter(p, q, !!onlyUnchecked?.checked, !!onlyUnpaid?.checked)
      );

      const onRowChange = () => {
        // ✅ totals винаги за всички (по-стабилно)
        renderSummary(passengers);
      };

      if (view === "table") renderTable(filtered, onRowChange, refreshPassengers);
      else renderCards(filtered, onRowChange, refreshPassengers);

      renderSummary(passengers);
    };

    // initial load
    try {
      passengers = await fetchPassengers(tripId);
    } catch (e) {
      alert(String(e?.message || e));
      return;
    }

    // finalize
    saveBtn?.addEventListener("click", async () => {
      if (!confirm("Да финализирам ли курса? (Запиши)")) return;

      saveBtn.disabled = true;
      if (saveStatus) saveStatus.textContent = "Записване...";

      const res = await fetch(`/api/trips/${tripId}/finalize`, { method: "POST", credentials: "same-origin" });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        if (saveStatus) saveStatus.textContent = "Грешка при записване.";
        alert("Грешка: " + (data?.detail || res.status));
        saveBtn.disabled = false;
        return;
      }

      if (saveStatus) saveStatus.textContent = `Записано (финализирано): ${data.finalizedAt ?? ""}`;
      saveBtn.textContent = "Записано";
    });

    // filters
    search?.addEventListener("input", rerender);
    onlyUnchecked?.addEventListener("change", rerender);
    onlyUnpaid?.addEventListener("change", rerender);

    // view toggle
    toggle?.addEventListener("click", () => {
      view = view === "table" ? "cards" : "table";
      if (toggle) toggle.textContent = view === "table" ? "Card view" : "Table view";
      tableView?.classList.toggle("hidden", view !== "table");
      cardView?.classList.toggle("hidden", view !== "cards");
      rerender();
    });

    // print / PDF
    printBtn?.addEventListener("click", () => {
      view = "table";
      if (toggle) toggle.textContent = "Card view";
      tableView?.classList.remove("hidden");
      cardView?.classList.add("hidden");
      rerender();
      setTimeout(() => window.print(), 50);
    });

    // import (optional)
    importForm?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(importForm);
      if (status) status.textContent = "Импортиране...";
      if (!confirm("Този импорт ще презапише текущата таблица за курса. Продължаваме?")) return;

      const res = await fetch(`/api/trips/${tripId}/passengers/import`, {
        method: "POST",
        credentials: "same-origin",
        body: fd,
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        if (status) status.textContent = "Грешка при импорт.";
        alert("Грешка: " + (data?.detail || res.status));
        return;
      }

      if (status) status.textContent = `Готово: ${data.inserted ?? "?"} реда`;
      await refreshPassengers();
    });

    // renumber
    renumberBtn?.addEventListener("click", async () => {
      if (!confirm("Да преномерирам ли пасажирите по текущия passenger_no (Excel) и да ги направя 1..N?")) return;
      await fetch(`/api/trips/${tripId}/passengers/renumber`, { method: "POST", credentials: "same-origin" });
      await refreshPassengers();
    });

    rerender();
  }

  document.addEventListener("DOMContentLoaded", main);
})();

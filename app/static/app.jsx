async function fetchPassengers(tripId) {
  const res = await fetch(`/api/trips/${tripId}/passengers`);
  return await res.json();
}

function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "class") e.className = v;
    else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  });
  children.forEach(c => e.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
  return e;
}

async function patchPassenger(id, payload) {
  await fetch(`/api/passengers/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function matchesFilter(p, q, onlyUnchecked, onlyUnpaid) {
  if (onlyUnchecked && p.checkedIn) return false;
  if (onlyUnpaid && p.paid) return false;
  if (!q) return true;
  const s = (p.fullName + " " + p.phone + " " + p.seatNo + " " + (p.passengerNo||"")).toLowerCase();
  return s.includes(q.toLowerCase());
}

function renderTable(passengers) {
  const tbody = document.getElementById("rows");
  tbody.innerHTML = "";

  passengers.forEach(p => {
    const checked = el("input", { type: "checkbox" });
    checked.checked = !!p.checkedIn;
    checked.addEventListener("change", async () => {
      await patchPassenger(p.id, { checkedIn: checked.checked });
      p.checkedIn = checked.checked;
    });

    const paid = el("input", { type: "checkbox" });
    paid.checked = !!p.paid;
    paid.addEventListener("change", async () => {
      await patchPassenger(p.id, { paid: paid.checked });
      p.paid = paid.checked;
    });

    const amount = el("input", { type: "number", step: "0.01", value: p.amount ?? "" });
    amount.addEventListener("change", async () => {
      await patchPassenger(p.id, { amount: amount.value });
    });

    const tr = el("tr", {}, [
      el("td", {}, [p.passengerNo ?? ""]),
      el("td", {}, [p.fullName ?? ""]),
      el("td", {}, [p.phone ?? ""]),
      el("td", {}, [p.seatNo ?? ""]),
      el("td", {}, [p.fromCity ?? ""]),
      el("td", {}, [p.toCity ?? ""]),
      el("td", {}, [p.voucherRaw ?? ""]),
      el("td", {}, [checked]),
      el("td", {}, [paid]),
      el("td", {}, [amount]),
    ]);
    tbody.appendChild(tr);
  });
}

function renderCards(passengers) {
  const root = document.getElementById("cardView");
  root.innerHTML = "";

  passengers.forEach(p => {
    const checked = el("input", { type: "checkbox" });
    checked.checked = !!p.checkedIn;
    checked.addEventListener("change", async () => {
      await patchPassenger(p.id, { checkedIn: checked.checked });
      p.checkedIn = checked.checked;
    });

    const paid = el("input", { type: "checkbox" });
    paid.checked = !!p.paid;
    paid.addEventListener("change", async () => {
      await patchPassenger(p.id, { paid: paid.checked });
      p.paid = paid.checked;
    });

    const amount = el("input", { type: "number", step: "0.01", value: p.amount ?? "" });
    amount.addEventListener("change", async () => {
      await patchPassenger(p.id, { amount: amount.value });
    });

    root.appendChild(
      el("div", { class: "p-card" }, [
        el("div", { class: "p-title" }, [ (p.fullName ?? "—") + (p.seatNo ? ` • място ${p.seatNo}` : "") ]),
        el("div", { class: "p-sub" }, [ `${p.fromCity ?? ""} → ${p.toCity ?? ""}` ]),
        el("div", { class: "p-sub" }, [ p.phone ?? "" ]),
        el("div", { class: "p-sub muted" }, [ p.voucherRaw ?? "" ]),
        el("div", { class: "p-actions" }, [
          el("label", {}, [checked, " Чекиран"]),
          el("label", {}, [paid, " Платил"]),
          el("label", {}, ["Сума ", amount]),
        ]),
      ])
    );
  });
}

async function main() {
  const tripId = window.TRIP_ID;
  if (!tripId) return;

  const search = document.getElementById("search");
  const onlyUnchecked = document.getElementById("onlyUnchecked");
  const onlyUnpaid = document.getElementById("onlyUnpaid");
  const toggle = document.getElementById("toggleView");
  const tableView = document.getElementById("tableView");
  const cardView = document.getElementById("cardView");

  let view = "table";
  let passengers = await fetchPassengers(tripId);

  function rerender() {
    const q = search.value.trim();
    const filtered = passengers.filter(p => matchesFilter(p, q, onlyUnchecked.checked, onlyUnpaid.checked));
    if (view === "table") renderTable(filtered);
    else renderCards(filtered);
  }

  [search, onlyUnchecked, onlyUnpaid].forEach(x => x.addEventListener("input", rerender));
  toggle.addEventListener("click", () => {
    view = view === "table" ? "cards" : "table";
    toggle.textContent = view === "table" ? "Card view" : "Table view";
    tableView.classList.toggle("hidden", view !== "table");
    cardView.classList.toggle("hidden", view !== "cards");
    rerender();
  });

  // import
  const importForm = document.getElementById("importForm");
  const status = document.getElementById("importStatus");
  importForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(importForm);
    status.textContent = "Импортиране...";
    const res = await fetch(`/api/trips/${tripId}/passengers/import`, { method: "POST", body: fd });
    const data = await res.json();
    status.textContent = `Готово: ${data.inserted} реда`;
    passengers = await fetchPassengers(tripId);
    rerender();
  });

  rerender();
}

document.addEventListener("DOMContentLoaded", main);

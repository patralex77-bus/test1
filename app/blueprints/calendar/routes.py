# -*- coding: utf-8 -*-
from __future__ import annotations
import json, time, datetime as dt
from pathlib import Path
from typing import Any, Dict, List
from flask import render_template, request, jsonify, Response, stream_with_context
from . import bp

# --- данни / пътища ---
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
ORDERS_FILE = DATA_DIR / "orders.json"
DRIVERS_FILE = DATA_DIR / "drivers.json"

def _load_json(path: Path, default):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _date(s: Any) -> dt.date | None:
    if not s: return None
    try: return dt.date.fromisoformat(str(s)[:10])
    except Exception: return None

def _iso(d: dt.date | None) -> str:
    return d.isoformat() if d else ""

def _overlaps(a_start: dt.date, a_end: dt.date, b_start: dt.date, b_end: dt.date) -> bool:
    return not (a_end < b_start or b_end < a_start)

def _driver_label(d: dict) -> str:
    fn = (d.get("first_name") or "").strip()
    ln = (d.get("last_name") or "").strip()
    full = (ln + " " + fn).strip()
    return full or f"Шофьор #{d.get('id')}"

def _get_window():
    q_from = request.args.get("from", type=str) or ""
    q_to   = request.args.get("to",   type=str) or ""
    try_from = _date(q_from)
    try_to   = _date(q_to)
    if not try_from or not try_to:
        today = dt.date.today()
        try_from = today - dt.timedelta(days=2)
        try_to   = today + dt.timedelta(days=28)
    if try_from > try_to:
        try_from, try_to = try_to, try_from
    return try_from, try_to

# ---------- Pages ----------
@bp.route("/", endpoint="index")
def page_index():
    # Оригинален календар по автобуси
    return render_template("calendar/index.html", page="calendar")

@bp.route("/drivers", endpoint="drivers")
def page_drivers():
    # Огледален календар по ШОФЬОРИ
    return render_template("calendar/drivers.html", page="calendar_drivers")

# ---------- API ----------
@bp.get("/api/snapshot", endpoint="api_snapshot")
def api_snapshot():
    win_from, win_to = _get_window()
    orders_store  = _load_json(ORDERS_FILE,  {"orders": [], "next_id": 1})
    drivers_store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})

    drivers_raw = (drivers_store.get("drivers") or [])
    drivers_sorted = sorted(
        drivers_raw,
        key=lambda d: (str(d.get("last_name") or "").lower(),
                       str(d.get("first_name") or "").lower(),
                       int(d.get("id") or 0))
    )
    drivers = [{"id": int(d.get("id")), "name": _driver_label(d)}
               for d in drivers_sorted if d.get("id") is not None]
    drivers_by_id = {int(d.get("id")): _driver_label(d)
                     for d in drivers_sorted if d.get("id") is not None}

    out_orders: List[Dict[str, Any]] = []
    for o in (orders_store.get("orders") or []):
        sd = _date(o.get("start_date") or o.get("date"))
        ed = _date(o.get("end_date") or o.get("start_date") or o.get("date")) or sd
        if not sd: 
            continue
        if not _overlaps(sd, ed, win_from, win_to):
            continue
        did = o.get("driver_id")
        try:
            did = int(did) if did is not None else None
        except Exception:
            did = None
        out_orders.append({
            "id": o.get("id"),
            "title": o.get("title")
                      or ((o.get("origin") and o.get("destination"))
                          and f"{o.get('origin')} → {o.get('destination')}")
                      or f"Поръчка #{o.get('id')}",
            "start_date": _iso(sd),
            "end_date":   _iso(ed),
            "start_time": o.get("start_time") or "08:00",
            "end_time":   o.get("end_time")   or "18:00",
            "status":     o.get("status")     or "Планирана",
            "bus_plate":  o.get("bus_plate")  or o.get("vehicle_plate") or "",
            "driver_id":  did,
            "driver_name": (o.get("driver_name") or drivers_by_id.get(did, "")) if did is not None else "",
            "price": o.get("price"),
        })

    return jsonify({
        "from": _iso(win_from),
        "to":   _iso(win_to),
        "drivers": drivers,
        "orders":  out_orders,
    })

# ---------- SSE (live reload между двата календара) ----------
@bp.get("/events/orders", endpoint="events_orders")
def events_orders():
    def _mtime_safe(p: Path) -> float:
        try: return p.stat().st_mtime
        except Exception: return 0.0

    @stream_with_context
    def gen():
        files = [ORDERS_FILE, DRIVERS_FILE]
        last_ts = max(_mtime_safe(f) for f in files)
        yield f"event: ping\ndata: {{\"ts\": {int(time.time())}}}\n\n"
        while True:
            time.sleep(2.0)
            cur = max(_mtime_safe(f) for f in files)
            yield f"event: ping\ndata: {{\"ts\": {int(time.time())}}}\n\n"
            if cur > last_ts:
                last_ts = cur
                yield f"event: reload\ndata: {{\"ts\": {int(time.time())}}}\n\n"

    headers = {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return Response(gen(), headers=headers)

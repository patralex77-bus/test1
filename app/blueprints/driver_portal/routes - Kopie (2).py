# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import datetime as dt
from pathlib import Path
import urllib.parse

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

bp = Blueprint(
    "driver_portal",
    __name__,
    url_prefix="/driver-portal",
)

# =========================================================
# Пътища към данни (аналогично на drivers)
# =========================================================
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"

DRIVERS_FILE = DATA_DIR / "drivers.json"
LOGS_FILE = DATA_DIR / "driver_logs.json"
ORDERS_FILE = DATA_DIR / "orders.json"
TELEMETRY_FILE = DATA_DIR / "telemetry.json"

SESSION_KEY_DRIVER_ID = "driver_portal_driver_id"


# =========================================================
# Helpers: I/O
# =========================================================
def _load_json(path: Path, default):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(default, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        path.write_text(
            json.dumps(default, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# =========================================================
# Helpers: дати/числа
# =========================================================
def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _ymd(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def _now_local_date() -> dt.date:
    return dt.date.today()


def _fnum(v, default=0.0):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return default


# =========================================================
# Helpers: drivers / orders / telemetry
# =========================================================
def _get_driver(drivers_store, did):
    sid = str(did)
    for d in drivers_store.get("drivers", []) or []:
        if str(d.get("id")) == sid:
            return d
    return None


def _norm_plate(obj_or_str):
    if isinstance(obj_or_str, str):
        return obj_or_str.strip().upper()
    if isinstance(obj_or_str, dict):
        for k in ("reg_no", "reg", "plate", "bus_plate", "number", "registration", "regnum"):
            v = obj_or_str.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip().upper()
    return ""


def _load_telemetry() -> list:
    if not TELEMETRY_FILE.exists():
        TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        TELEMETRY_FILE.write_text("[]", encoding="utf-8")
        return []
    try:
        data = json.loads(TELEMETRY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        TELEMETRY_FILE.write_text("[]", encoding="utf-8")
        return []


# =========================================================
# Helpers: период на поръчка (опростена версия)
# =========================================================
def _order_dates(o: dict) -> tuple[dt.date | None, dt.date | None]:
    """
    Връща (start_date, end_date) като date обекти или (None, None).

    Поддържани полета (в ред на приоритет):
      - start_date / end_date
      - date_from / date_to
      - date (еднодневна)
    """
    start_raw = (
        o.get("start_date")
        or o.get("date_from")
        or o.get("date")
        or o.get("from_date")
    )
    end_raw = (
        o.get("end_date")
        or o.get("date_to")
        or o.get("date")
        or o.get("to_date")
    )

    sd = _d(start_raw) if start_raw else None
    ed = _d(end_raw) if end_raw else None
    return sd, ed


# =========================================================
# Статистики – копие на логиката от drivers._compute_driver_stats_for_month
# (опростено за портала, но със същата идея)
# =========================================================
def _compute_driver_stats_for_month(driver_id: int, month_start: dt.date, month_end: dt.date):
    """
    Връща:
      - totals: { hours, km, costs }
      - stats_day: списък по дни в месеца
      - stats_week: списък по календарни седмици (Пн–Нд)
    (логика, съвместима с бекенд отчетите)
    """
    logs_store = _load_json(LOGS_FILE, {"logs": []})
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    try:
        telemetry = _load_telemetry()
        if not isinstance(telemetry, list):
            telemetry = []
    except Exception:
        telemetry = []

    orders_map = {str(o.get("id")): o for o in (orders_store.get("orders") or [])}

    # дневна решетка
    daily = {}
    d_cur = month_start
    while d_cur <= month_end:
        ymd = _ymd(d_cur)
        iso_year, iso_week, iso_wday = d_cur.isocalendar()
        daily[ymd] = {
            "date": ymd,
            "date_obj": d_cur,
            "iso_year": iso_year,
            "iso_week": iso_week,
            "hours": 0.0,
            "km": 0.0,
            "costs": 0.0,
            "buses": set(),
        }
        d_cur += dt.timedelta(days=1)

    def _in_month_range(date_str):
        dd = _d(date_str)
        if not dd:
            return False
        return month_start <= dd <= month_end

    # 1) LOGS – време + разходи + автобуси
    for L in logs_store.get("logs", []) or []:
        if str(L.get("driver_id")) != str(driver_id):
            continue
        if not _in_month_range(L.get("date")):
            continue

        d_obj = _d(L.get("date"))
        if not d_obj:
            continue
        ymd = _ymd(d_obj)
        rec = daily.get(ymd)
        if not rec:
            continue

        worked_hours = float(L.get("worked_hours") or 0.0)
        rec["hours"] += worked_hours

        fuel_amount = _fnum(L.get("fuel_amount"), 0.0)
        tolls = _fnum(L.get("tolls"), 0.0)
        parking = _fnum(L.get("parking"), 0.0)
        ferry = _fnum(L.get("ferry"), 0.0)
        other_expenses = _fnum(L.get("other_expenses"), 0.0)
        rec["costs"] += fuel_amount + tolls + parking + ferry + other_expenses

        oid = L.get("order_id")
        if oid is not None:
            o = orders_map.get(str(oid))
            if o:
                plate = _norm_plate(o)
                if plate:
                    rec["buses"].add(plate)

    # 2) TELEMETRY – км + разходи + автобус
    for x in telemetry:
        if str(x.get("driver_id")) != str(driver_id):
            continue
        if not _in_month_range(x.get("date")):
            continue

        d_obj = _d(x.get("date"))
        if not d_obj:
            continue
        ymd = _ymd(d_obj)
        rec = daily.get(ymd)
        if not rec:
            continue

        km_val = _fnum(x.get("km"), 0.0)
        rec["km"] += km_val

        fuel_total = _fnum(x.get("fuel_total"), 0.0)
        rec["costs"] += fuel_total

        if x.get("bus_reg_no"):
            plate = _norm_plate(x.get("bus_reg_no"))
            if plate:
                rec["buses"].add(plate)

    # Totals
    totals_hours = totals_km = totals_costs = 0.0
    for rec in daily.values():
        totals_hours += rec["hours"]
        totals_km += rec["km"]
        totals_costs += rec["costs"]

    totals = {
        "hours": round(totals_hours, 2),
        "km": round(totals_km, 1),
        "costs": round(totals_costs, 2),
    }

    # Групиране по календарни седмици
    weeks = {}
    for rec in daily.values():
        iso_year = rec["iso_year"]
        iso_week = rec["iso_week"]
        key = (iso_year, iso_week)

        if key not in weeks:
            week_start = dt.date.fromisocalendar(iso_year, iso_week, 1)
            week_end = dt.date.fromisocalendar(iso_year, iso_week, 7)
            weeks[key] = {
                "year": iso_year,
                "week": iso_week,
                "week_start": week_start,
                "week_end": week_end,
                "hours": 0.0,
                "km": 0.0,
                "costs": 0.0,
                "buses": set(),
            }

        bucket = weeks[key]
        bucket["hours"] += rec["hours"]
        bucket["km"] += rec["km"]
        bucket["costs"] += rec["costs"]
        for b in rec["buses"]:
            bucket["buses"].add(b)

    sorted_weeks = sorted(weeks.values(), key=lambda w: w["week_start"])

    week_index = {}
    for idx, w in enumerate(sorted_weeks, start=1):
        week_index[(w["year"], w["week"])] = idx

    # stats_day
    stats_day = []
    for ymd in sorted(daily.keys()):
        rec = daily[ymd]
        d_obj = rec["date_obj"]
        w_in_month = week_index.get((rec["iso_year"], rec["iso_week"]), 0)
        stats_day.append({
            "date": rec["date"],
            "date_human": d_obj.strftime("%d.%m.%Y"),
            "week_in_month": w_in_month,
            "hours": round(rec["hours"], 2),
            "km": round(rec["km"], 1),
            "costs": round(rec["costs"], 2),
            "buses": sorted(b for b in rec["buses"] if b),
        })

    # stats_week
    stats_week = []
    for w in sorted_weeks:
        ws = w["week_start"]
        we = w["week_end"]
        idx = week_index.get((w["year"], w["week"]), 0)
        stats_week.append({
            "year": w["year"],
            "week": w["week"],
            "week_in_month": idx,
            "range_start": ws.strftime("%d.%m"),
            "range_end": we.strftime("%d.%m"),
            "hours": round(w["hours"], 2),
            "km": round(w["km"], 1),
            "costs": round(w["costs"], 2),
            "buses": sorted(b for b in w["buses"] if b),
        })

    return totals, stats_day, stats_week


# =========================================================
# Helpers: текущ шофьор от "кабинета"
# =========================================================
def _get_current_driver():
    store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    drivers = store.get("drivers", []) or []
    if not drivers:
        return None

    did = session.get(SESSION_KEY_DRIVER_ID)
    if did is not None:
        d = _get_driver(store, did)
        if d:
            return d

    # fallback – първият шофьор
    first = drivers[0]
    try:
        session[SESSION_KEY_DRIVER_ID] = int(first.get("id"))
    except Exception:
        pass
    return first


def _require_driver():
    driver = _get_current_driver()
    if not driver:
        flash("Няма въведени шофьори.", "info")
        return None, redirect(url_for("driver_portal.select_driver"))
    return driver, None


# =========================================================
# КАЛЕНДАР – седмица / месец
# =========================================================
def _today_bg_label(d: dt.date) -> str:
    """Връща 'Понеделник, 01.12.2025' на български."""
    weekdays = {
        0: "Понеделник",
        1: "Вторник",
        2: "Сряда",
        3: "Четвъртък",
        4: "Петък",
        5: "Събота",
        6: "Неделя",
    }
    name = weekdays.get(d.weekday(), d.strftime("%A"))
    return f"{name}, {d.strftime('%d.%m.%Y')}"


def _parse_time_any(o: dict) -> tuple[str | None, str | None]:
    """
    Опитва да вземе начален/краен час от поръчката.
    Върща (start_str, end_str) във формат 'HH:MM' или (None, None).
    """
    cand_start = (
        o.get("start_time")
        or o.get("time_from")
        or o.get("departure_time")
        or ""
    )
    cand_end = (
        o.get("end_time")
        or o.get("time_to")
        or o.get("arrival_time")
        or ""
    )
    s = str(cand_start).strip()[:5] if cand_start else None
    e = str(cand_end).strip()[:5] if cand_end else None
    return (s or None, e or None)


def _hhmm_to_time(t_str: str | None) -> dt.time | None:
    if not t_str:
        return None
    try:
        return dt.datetime.strptime(t_str.strip(), "%H:%M").time()
    except Exception:
        return None


def _compute_order_status(sd: dt.date | None,
                          ed: dt.date | None,
                          start_str: str | None,
                          end_str: str | None,
                          today: dt.date,
                          now_time: dt.time) -> str:
    """
    Връща текстов статус:
      - 'Планирана'
      - 'В ход'
      - 'Приключена'
    спрямо датите и часа.
    """
    if not sd:
        return "Планирана"

    if ed is None:
        ed = sd

    # Изцяло в миналото
    if ed < today:
        return "Приключена"

    # Изцяло в бъдещето
    if sd > today:
        return "Планирана"

    # Днес е в интервала [sd, ed]
    st = _hhmm_to_time(start_str) if start_str else None
    en = _hhmm_to_time(end_str) if end_str else None

    if st and now_time < st:
        return "Планирана"
    if en and now_time > en:
        return "Приключена"

    return "В ход"


@bp.get("/calendar", endpoint="calendar")
def calendar():
    """
    Календар на поръчките за текущия шофьор.

    Режими:
      - view=week  → показва седмицата на избрания ден (Понеделник–Неделя)
      - view=month → показва целия месец
    """
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    driver_id = int(driver.get("id"))
    today = _now_local_date()

    view_mode = (request.args.get("view") or "week").lower()
    if view_mode not in ("week", "month"):
        view_mode = "week"

    date_param = (request.args.get("date") or "").strip()
    selected_date: dt.date | None = None
    if date_param:
        try:
            selected_date = dt.date.fromisoformat(date_param)
        except Exception:
            selected_date = None
    if not selected_date:
        selected_date = today
    selected_date_str = selected_date.isoformat()

    month_param = (request.args.get("month") or "").strip()
    if view_mode == "month" and month_param:
        try:
            year, month = month_param.split("-")
            year = int(year)
            month = int(month)
            month_start = dt.date(year, month, 1)
        except Exception:
            month_start = dt.date(selected_date.year, selected_date.month, 1)
    else:
        month_start = dt.date(selected_date.year, selected_date.month, 1)

    next_month = (month_start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    month_end = next_month - dt.timedelta(days=1)
    prev_month_start = (month_start - dt.timedelta(days=1)).replace(day=1)

    month_value = f"{month_start.year:04d}-{month_start.month:02d}"
    prev_month_value = f"{prev_month_start.year:04d}-{prev_month_start.month:02d}"
    next_month_value = f"{next_month.year:04d}-{next_month.month:02d}"
    month_label = month_start.strftime("%B %Y")

    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    logs_store = _load_json(LOGS_FILE, {"logs": []})

    all_orders = orders_store.get("orders", []) or []

    logs_index = set()
    for L in logs_store.get("logs", []) or []:
        if str(L.get("driver_id")) != str(driver_id):
            continue
        d_obj = _d(L.get("date"))
        if not d_obj:
            continue
        ymd = _ymd(d_obj)
        oid = L.get("order_id")
        if oid is not None:
            logs_index.add((str(oid), ymd))

    days_map = {}
    d_cur = month_start
    while d_cur <= month_end:
        ymd = _ymd(d_cur)
        days_map[ymd] = {
            "date": d_cur,
            "date_str": ymd,
            "day_num": d_cur.day,
            "weekday": d_cur.weekday(),  # 0=Пн
            "orders": [],
        }
        d_cur += dt.timedelta(days=1)

    for o in all_orders:
        if str(o.get("driver_id")) != str(driver_id):
            continue

        sd, ed = _order_dates(o)
        if not sd:
            continue
        if ed is None:
            ed = sd

        start = max(sd, month_start)
        end = min(ed, month_end)
        if start > end:
            continue

        order_id = o.get("id")
        s_str, e_str = _parse_time_any(o)
        time_range = None
        if s_str and e_str:
            time_range = f"{s_str} – {e_str}"
        elif s_str:
            time_range = s_str
        elif e_str:
            time_range = e_str

        origin = (
            o.get("from_city")
            or o.get("origin")
            or o.get("start_place")
            or o.get("from_name")
            or ""
        )
        destination = (
            o.get("to_city")
            or o.get("destination")
            or o.get("end_place")
            or o.get("to_name")
            or ""
        )
        client = (
            o.get("client_name")
            or o.get("group_name")
            or o.get("customer")
            or ""
        )

        has_docs = bool(o.get("has_unread_docs") or o.get("docs_unread"))

        d_loop = start
        while d_loop <= end:
            ymd = _ymd(d_loop)
            day_bucket = days_map.get(ymd)
            if day_bucket is not None:
                has_log = (str(order_id), ymd) in logs_index
                day_bucket["orders"].append({
                    "id": order_id,
                    "date_str": ymd,
                    "time_range": time_range,
                    "start_time": s_str,
                    "end_time": e_str,
                    "origin": origin,
                    "destination": destination,
                    "client": client,
                    "has_log": has_log,
                    "has_docs": has_docs,
                })
            d_loop += dt.timedelta(days=1)

    days_month = sorted(days_map.values(), key=lambda d: d["date"])

    selected_ymd = _ymd(selected_date)
    selected_day = days_map.get(selected_ymd)
    selected_orders = selected_day["orders"] if selected_day else []

    monday = selected_date - dt.timedelta(days=selected_date.weekday())
    week_days = []
    for i in range(7):
        d = monday + dt.timedelta(days=i)
        ymd = _ymd(d)
        if ymd in days_map:
            bucket = days_map[ymd]
        else:
            bucket = {
                "date": d,
                "date_str": ymd,
                "day_num": d.day,
                "weekday": d.weekday(),
                "orders": [],
            }
        week_days.append(bucket)

    prev_week_date = selected_date - dt.timedelta(days=7)
    next_week_date = selected_date + dt.timedelta(days=7)
    prev_week_date_str = prev_week_date.isoformat()
    next_week_date_str = next_week_date.isoformat()

    if view_mode == "month":
        days_visible = days_month
    else:
        days_visible = week_days

    return render_template(
        "drivers/calendar.html",
        current_driver=driver,
        today=today,
        month_label=month_label,
        month_value=month_value,
        prev_month_value=prev_month_value,
        next_month_value=next_month_value,
        view_mode=view_mode,
        days=days_visible,
        days_month=days_month,
        days_week=week_days,
        selected_date=selected_date,
        selected_date_str=selected_date_str,
        selected_orders=selected_orders,
        prev_week_date_str=prev_week_date_str,
        next_week_date_str=next_week_date_str,
    )


# =========================================================
# ORDERS LIST – списък с поръчки за шофьора
# =========================================================
@bp.get("/orders", endpoint="orders_list")
def orders_list():
    """
    Списък с поръчки в кабинета на шофьора.

    Филтър scope:
      - today     → само днес
      - tomorrow  → само утре
      - next7     → от днес + следващите 7 дни
      - past      → минали (крайна дата < днес)
    """
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    driver_id = int(driver.get("id"))
    today = _now_local_date()
    now_time = dt.datetime.now().time()

    scope = (request.args.get("scope") or "today").lower()
    if scope not in ("today", "tomorrow", "next7", "past"):
        scope = "today"

    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    logs_store = _load_json(LOGS_FILE, {"logs": []})

    all_orders = orders_store.get("orders", []) or []

    logs_has_order = set()
    for L in logs_store.get("logs", []) or []:
        if str(L.get("driver_id")) != str(driver_id):
            continue
        oid = L.get("order_id")
        if oid is not None:
            logs_has_order.add(str(oid))

    if scope == "today":
        range_start = today
        range_end = today
    elif scope == "tomorrow":
        range_start = today + dt.timedelta(days=1)
        range_end = range_start
    elif scope == "next7":
        range_start = today
        range_end = today + dt.timedelta(days=7)
    else:
        range_start = None
        range_end = None

    def _intersects(start: dt.date, end: dt.date,
                    r_start: dt.date, r_end: dt.date) -> bool:
        return not (end < r_start or start > r_end)

    rows = []
    for o in all_orders:
        if str(o.get("driver_id")) != str(driver_id):
            continue

        sd, ed = _order_dates(o)
        if not sd:
            continue
        if ed is None:
            ed = sd

        if scope == "past":
            if ed >= today:
                continue
        else:
            if not _intersects(sd, ed, range_start, range_end):
                continue

        s_str, e_str = _parse_time_any(o)
        time_range = None
        if s_str and e_str:
            time_range = f"{s_str} – {e_str}"
        elif s_str:
            time_range = s_str
        elif e_str:
            time_range = e_str

        origin = (
            o.get("from_city")
            or o.get("origin")
            or o.get("start_place")
            or o.get("from_name")
            or ""
        )
        destination = (
            o.get("to_city")
            or o.get("destination")
            or o.get("end_place")
            or o.get("to_name")
            or ""
        )
        client = (
            o.get("client_name")
            or o.get("group_name")
            or o.get("customer")
            or ""
        )

        has_docs = bool(o.get("has_unread_docs") or o.get("docs_unread"))
        has_log = str(o.get("id")) in logs_has_order

        status = _compute_order_status(sd, ed, s_str, e_str, today, now_time)

        if sd == ed:
            date_label = sd.strftime("%d.%m.%Y")
        else:
            date_label = f"{sd.strftime('%d.%m')} – {ed.strftime('%d.%m.%Y')}"

        rows.append({
            "id": o.get("id"),
            "date_from": sd,
            "date_to": ed,
            "date_label": date_label,
            "time_range": time_range,
            "origin": origin,
            "destination": destination,
            "client": client,
            "status": status,
            "has_log": has_log,
            "has_docs": has_docs,
        })

    def _sort_key(r):
        base = r["date_from"] or today
        return base

    rows = sorted(rows, key=_sort_key, reverse=(scope == "past"))

    return render_template(
        "drivers/orders_list.html",
        current_driver=driver,
        today=today,
        scope=scope,
        orders=rows,
    )


# =========================================================
# SELECT екран – избор на шофьор (демо логин без токени)
# =========================================================
@bp.get("/select")
def select_driver():
    store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    drivers = store.get("drivers", []) or []

    def _key(d):
        return (
            str(d.get("last_name") or "").lower(),
            str(d.get("first_name") or "").lower(),
            int(d.get("id") or 0),
        )

    drivers = sorted(drivers, key=_key)

    return render_template(
        "drivers/portal_select.html",
        drivers=drivers,
    )


@bp.get("/demo/<int:driver_id>")
def demo_login(driver_id: int):
    store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    d = _get_driver(store, driver_id)
    if not d:
        flash("Шофьорът не е намерен.", "warning")
        return redirect(url_for("driver_portal.select_driver"))

    session[SESSION_KEY_DRIVER_ID] = int(driver_id)
    flash(
        f"Отворен е кабинет за {d.get('first_name', '')} {d.get('last_name', '')}.",
        "success",
    )
    return redirect(url_for("driver_portal.dashboard"))


@bp.get("/logout")
def logout():
    session.pop(SESSION_KEY_DRIVER_ID, None)
    flash("Излезе от шофьорския кабинет.", "info")
    return redirect(url_for("driver_portal.select_driver"))


# =========================================================
# Статуси на изпълнение на поръчка в кабинета
# =========================================================
STATUS_STEPS = [
    ("planned", "Планирана"),
    ("departed", "Тръгнах"),
    ("arrived", "Пристигнах"),
    ("return_departed", "Тръгнах обратно"),
    ("finished", "Завършена"),
]


def _load_orders_store():
    """Чете orders.json и връща store = { 'orders': [...], 'next_id': ... }."""
    return _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})


def _save_orders_store(store):
    _save_json(ORDERS_FILE, store)


def _find_driver_order(store, order_id, driver_id):
    """
    Намира поръчка по id, ограничена до дадения driver_id.
    Ако не искаш ограничение – махни проверката за driver_id.
    """
    sid = str(order_id)
    sdriver = str(driver_id)
    for o in store.get("orders", []) or []:
        if str(o.get("id")) != sid:
            continue
        if str(o.get("driver_id")) not in ("", "0", sdriver):
            continue
        return o
    return None


# =========================================================
# DASHBOARD "Днес" – табло с поръчките за текущия ден
# =========================================================
@bp.get("/dashboard")
def dashboard():
    """
    'Табло Днес' за шофьора.
    Работи с драйвър от сесията (демо вход през /select или /demo/<id>).
    """
    driver_id_param = (request.args.get("driver_id") or "").strip()
    if driver_id_param:
        try:
            session[SESSION_KEY_DRIVER_ID] = int(driver_id_param)
        except Exception:
            pass

    driver, resp = _require_driver()
    if resp is not None:
        return resp

    drivers_store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    all_drivers = drivers_store.get("drivers", []) or []
    drivers_list = [
        {
            "id": d.get("id"),
            "name": f"{d.get('last_name','')} {d.get('first_name','')}".strip(),
        }
        for d in all_drivers
    ]

    driver_id = int(driver.get("id"))
    today = dt.date.today()
    today_label = _today_bg_label(today)

    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    all_orders = orders_store.get("orders", []) or []

    today_orders = []
    for o in all_orders:
        if str(o.get("driver_id")) != str(driver_id):
            continue
        sd, ed = _order_dates(o)
        if not sd:
            continue
        if ed is None:
            ed = sd
        if sd <= today <= ed:
            s_str, e_str = _parse_time_any(o)
            today_orders.append({
                "raw": o,
                "start_time": s_str,
                "end_time": e_str,
            })

    if today_orders:
        cnt = len(today_orders)
        valid_starts = [
            _hhmm_to_time(x["start_time"]) for x in today_orders if x["start_time"]
        ]
        valid_ends = [
            _hhmm_to_time(x["end_time"]) for x in today_orders if x["end_time"]
        ]

        first_start = min(valid_starts).strftime("%H:%M") if valid_starts else None
        last_end = max(valid_ends).strftime("%H:%M") if valid_ends else None

        today_stats = {
            "count": cnt,
            "first_start": first_start,
            "last_end": last_end,
        }
    else:
        today_stats = {
            "count": 0,
            "first_start": None,
            "last_end": None,
        }

    now_time = dt.datetime.now().time()

    def _order_sort_key(item):
        t = _hhmm_to_time(item["start_time"])
        return t or dt.time(23, 59)

    upcoming = []
    for item in today_orders:
        t = _hhmm_to_time(item["start_time"])
        if t and t >= now_time:
            upcoming.append(item)
    upcoming_sorted = sorted(upcoming, key=_order_sort_key)

    next_order = upcoming_sorted[0] if upcoming_sorted else (today_orders[0] if today_orders else None)

    next_order_ctx = None
    if next_order:
        o = next_order["raw"]
        s_str = next_order["start_time"]
        e_str = next_order["end_time"]

        origin = (
            o.get("from_city")
            or o.get("origin")
            or o.get("start_place")
            or o.get("from_name")
            or ""
        )
        destination = (
            o.get("to_city")
            or o.get("destination")
            or o.get("end_place")
            or o.get("to_name")
            or ""
        )
        client = (
            o.get("client_name")
            or o.get("group_name")
            or o.get("customer")
            or ""
        )
        title = o.get("title") or ""
        order_id = o.get("id")

        nav_query = destination or origin

        next_order_ctx = {
            "id": order_id,
            "start_time": s_str,
            "end_time": e_str,
            "origin": origin,
            "destination": destination,
            "client": client,
            "title": title,      # <<< добавено
            "nav_query": nav_query,
        }


    dispatcher_phone = "+359888000000"

    return render_template(
        "drivers/dashboard.html",
        current_driver=driver,
        drivers_list=drivers_list,
        today_label=today_label,
        today_orders=today_orders,
        today_stats=today_stats,
        next_order=next_order_ctx,
        dispatcher_phone=dispatcher_phone,
        page="drivers",
        active_page="dashboard",
    )


# =========================================================
# LOGS LIST – реални дневници за шофьора
# =========================================================
@bp.get("/logs", endpoint="logs_list")
def logs_list():
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    logs_store = _load_json(LOGS_FILE, {"logs": []})
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    telemetry = _load_telemetry()

    orders_map = {str(o.get("id")): o for o in (orders_store.get("orders") or [])}

    driver_id = int(driver.get("id"))
    rows = []

    tel_index = {}
    for t in telemetry or []:
        key = (str(t.get("driver_id")), str(t.get("order_id")), str(t.get("date")))
        tel_index[key] = t

    for L in logs_store.get("logs", []) or []:
        if str(L.get("driver_id")) != str(driver_id):
            continue

        date_obj = _d(L.get("date"))
        if not date_obj:
            continue

        oid = L.get("order_id")
        order = orders_map.get(str(oid)) if oid is not None else None
        order_title = order.get("title") if order else (f"Поръчка #{oid}" if oid else "")

        plate = ""
        if order:
            plate = _norm_plate(order)

        key = (str(driver_id), str(oid), str(L.get("date")))
        t = tel_index.get(key, {})

        km_val = _fnum(t.get("km"), 0.0)
        fuel_l = _fnum(t.get("fuel_liters"), 0.0)
        fuel_total = _fnum(t.get("fuel_total"), 0.0)

        rows.append({
            "date": date_obj,
            "date_str": date_obj.strftime("%d.%m.%Y"),
            "order_id": oid,
            "order_title": order_title,
            "plate": plate,
            "worked_hours": float(L.get("worked_hours") or 0.0),
            "km": km_val,
            "fuel_liters": fuel_l,
            "fuel_total": fuel_total,
            "other_expenses": _fnum(L.get("other_expenses"), 0.0),
            "tolls": _fnum(L.get("tolls"), 0.0),
            "parking": _fnum(L.get("parking"), 0.0),
            "ferry": _fnum(L.get("ferry"), 0.0),
        })

    rows = sorted(rows, key=lambda r: r["date"], reverse=True)

    return render_template(
        "drivers/logs_list.html",
        current_driver=driver,
        rows=rows,
        page="drivers",
        active_page="logs",
    )


# =========================================================
# REPORTS – месечни отчети в кабинета (същите данни като бекенд)
# =========================================================
@bp.get("/reports")
def reports():
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    month_param = (request.args.get("month") or "").strip()
    today = _now_local_date()
    if month_param:
        try:
            year, month = month_param.split("-")
            year = int(year)
            month = int(month)
            month_start = dt.date(year, month, 1)
        except Exception:
            month_start = dt.date(today.year, today.month, 1)
    else:
        month_start = dt.date(today.year, today.month, 1)

    next_month = (month_start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    month_end = next_month - dt.timedelta(days=1)

    prev_month_start = (month_start - dt.timedelta(days=1)).replace(day=1)
    next_month_start = next_month

    month_value = f"{month_start.year:04d}-{month_start.month:02d}"
    prev_month_value = f"{prev_month_start.year:04d}-{prev_month_start.month:02d}"
    next_month_value = f"{next_month_start.year:04d}-{next_month_start.month:02d}"
    month_label = month_start.strftime("%B %Y")

    totals, stats_day, stats_week = _compute_driver_stats_for_month(
        driver_id=int(driver.get("id")),
        month_start=month_start,
        month_end=month_end,
    )

    class TotalsObj:
        def __init__(self, d):
            self.hours = d.get("hours", 0.0)
            self.km = d.get("km", 0.0)
            self.costs = d.get("costs", 0.0)

    return render_template(
        "drivers/portal_reports.html",
        current_driver=driver,
        month_label=month_label,
        month_value=month_value,
        prev_month_value=prev_month_value,
        next_month_value=next_month_value,
        totals=TotalsObj(totals),
        stats_day=stats_day,
        stats_week=stats_week,
        page="drivers",
        active_page="reports",
    )

# =========================================================
# ORDER DETAIL – детайлна страница за поръчка в кабинета
# =========================================================
@bp.get("/orders/<int:order_id>", endpoint="order_detail")
def order_detail(order_id: int):
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    driver_id = int(driver.get("id"))

    # --- 1) Четем поръчката от orders.json ---
    store = _load_orders_store()
    order = _find_driver_order(store, order_id, driver_id=driver_id)
    if not order:
        flash("Поръчката не е намерена или не е за този шофьор.", "warning")
        return redirect(url_for("driver_portal.dashboard"))

    # --- 2) ACK – маркиране като 'видяна' ---
    ack = order.get("ack") or {}
    now_iso = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "current_version" not in ack:
        ack["current_version"] = 1
    ack["seen_at"] = now_iso
    if "last_seen_version" not in ack:
        ack["last_seen_version"] = ack.get("current_version", 1)
    order["ack"] = ack
    _save_orders_store(store)

    # --- 3) Основна информация за поръчката (дати, часове, текстове) ---
    today = _now_local_date()
    now_time = dt.datetime.now().time()

    sd, ed = _order_dates(order)
    if not sd:
        sd = today
    if ed is None:
        ed = sd

    start_time_str, end_time_str = _parse_time_any(order)

    # етикет за дати
    if sd == ed:
        date_label = sd.strftime("%d.%m.%Y")
    else:
        date_label = f"{sd.strftime('%d.%m.%Y')} – {ed.strftime('%d.%m.%Y')}"

    # статус по време (планирана / в ход / приключена)
    status_label = _compute_order_status(
        sd, ed, start_time_str, end_time_str, today, now_time
    )

    # заглавие, програма, изисквания, специални нужди
    title = order.get("title") or order.get("program") or f"Поръчка #{order_id}"
    program = order.get("program") or ""
    client_requirements = order.get("client_requirements") or ""
    special_needs = order.get("special_needs") or ""
    pax = order.get("pax") or order.get("passengers") or ""

    # клиент, маршрут
    origin = (
        order.get("from_city")
        or order.get("origin")
        or order.get("start_place")
        or order.get("from_name")
        or ""
    )
    destination = (
        order.get("to_city")
        or order.get("destination")
        or order.get("end_place")
        or order.get("to_name")
        or ""
    )
    client = (
        order.get("client_name")
        or order.get("group_name")
        or order.get("customer")
        or ""
    )

    # договор / номер
    contract_no = (
        order.get("contract_no")
        or order.get("agreement_no")
        or order.get("order_no")
        or ""
    )

    notes = order.get("notes") or order.get("driver_notes") or ""

    # Автобус
    bus_plate = (
        order.get("bus_plate")
        or order.get("vehicle_plate")
        or order.get("reg_no")
        or ""
    )

    # Телефони
    dispatcher_phone = "+359888000000"  # TODO: вземи от настройки при нужда
    client_phone = (
        order.get("client_phone")
        or order.get("phone")
        or order.get("contact_phone")
        or ""
    )

    # Навигация
    nav_query = destination or origin
    if nav_query:
        google_maps_url = (
            "https://www.google.com/maps/search/?api=1&query="
            + urllib.parse.quote(nav_query)
        )
    else:
        google_maps_url = None

    # Документи към поръчката – адаптирай ако структурата ти е друга
    documents = order.get("documents") or order.get("docs") or []

    # --- 4) Проверка на отчетите (driver_logs.json) ---
    logs_store = _load_json(LOGS_FILE, {"logs": []})
    logs_for_order = []
    start_report_done = False
    end_report_done = False

    for L in logs_store.get("logs", []) or []:
        if str(L.get("driver_id")) != str(driver_id):
            continue
        if str(L.get("order_id")) != str(order_id):
            continue

        d_obj = _d(L.get("date"))
        date_str = d_obj.strftime("%d.%m.%Y") if d_obj else ""

        # събираме за таблица / справка
        logs_for_order.append(
            {
                "date": date_str,
                "worked_hours": float(L.get("worked_hours") or 0.0),
                "km": _fnum(L.get("km"), 0.0),
                "fuel_amount": _fnum(L.get("fuel_amount"), 0.0),
                "tolls": _fnum(L.get("tolls"), 0.0),
                "parking": _fnum(L.get("parking"), 0.0),
                "ferry": _fnum(L.get("ferry"), 0.0),
                "other_expenses": _fnum(L.get("other_expenses"), 0.0),
            }
        )

        # флагове за начало/край – ако има някакви реални данни
        if L.get("work_start") or L.get("odo_start"):
            start_report_done = True
        if L.get("work_end") or L.get("odo_end"):
            end_report_done = True

    has_any_log = len(logs_for_order) > 0

    # --- 5) EXECUTION – статуси "Тръгнах / Пристигнах /..." ---
    execution = order.get("execution") or {}
    current_status = execution.get("current", "planned")
    status_keys = [k for (k, _label) in STATUS_STEPS]
    status_index_map = {k: i for i, k in enumerate(status_keys)}
    current_status_index = status_index_map.get(current_status, 0)

    # --- 6) Контекст към шаблона ---
    # Форматирани дати за показване
    start_date_str = sd.strftime("%d.%m.%Y") if sd else ""
    end_date_str = ed.strftime("%d.%m.%Y") if ed else ""

    order_view = {
        "id": order_id,
        "title": title,
        # период
        "start_date": start_date_str,
        "end_date": end_date_str,
        "start_time": start_time_str,
        "end_time": end_time_str,
        # маршрут / клиент
        "origin": origin,
        "destination": destination,
        "client": client,
        "pax": pax,
        # договор и бележки
        "contract_no": contract_no,
        "notes": notes,
        # допълнителни текстови полета
        "program": program,
        "client_requirements": client_requirements,
        "special_needs": special_needs,
        # автобус
        "bus_plate": bus_plate,
        # статус по време
        "status_time": status_label,
    }

    return render_template(
        "drivers/order_detail.html",
        current_driver=driver,
        order=order_view,          # "изчистен" контекст за шаблона
        order_raw=order,           # оригиналният запис от JSON (ако ти потрябва)
        ack=ack,
        execution=execution,
        status_steps=STATUS_STEPS,
        current_status=current_status,
        current_status_index=current_status_index,
        dispatcher_phone=dispatcher_phone,
        client_phone=client_phone,
        google_maps_url=google_maps_url,
        documents=documents,
        logs=logs_for_order,
        has_log=has_any_log,
        start_report_done=start_report_done,
        end_report_done=end_report_done,
        page="drivers",
        active_page="orders",
    )

@bp.get("/orders/<int:order_id>/log", endpoint="order_log")
def order_log(order_id: int):
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    driver_id = int(driver.get("id"))

    # 1) намираме поръчката за този шофьор
    store_orders = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    order = next(
        (o for o in store_orders.get("orders", []) or []
         if str(o.get("id")) == str(order_id)
         and str(o.get("driver_id")) == str(driver_id)),
        None,
    )
    if not order:
        flash("Поръчката не е намерена или не е за този шофьор.", "warning")
        return redirect(url_for("driver_portal.orders_list"))

    # 2) диапазон дни на поръчката
    sd, ed = _order_dates(order)
    if not sd:
        sd = _now_local_date()
    if ed is None:
        ed = sd

    days = []
    d_cur = sd
    while d_cur <= ed:
        days.append(_ymd(d_cur))
        d_cur += dt.timedelta(days=1)

    # 3) логове за този driver + order
    logs_store = _load_json(LOGS_FILE, {"logs": []})
    logs_map = {}
    for L in logs_store.get("logs", []) or []:
        if str(L.get("driver_id")) != str(driver_id):
            continue
        if str(L.get("order_id")) != str(order_id):
            continue
        ds = str(L.get("date"))[:10]
        logs_map[ds] = L

    return render_template(
        "drivers/order_log.html",  # нов шаблон, базиран 1:1 на този, който даде
        current_driver=driver,
        order=order,
        days=days,
        logs=logs_map,
        # тук НЯМА token – формата ще сочи към driver_portal.order_log_save
    )

@bp.post("/orders/<int:order_id>/log/save", endpoint="order_log_save")
def order_log_save(order_id: int):
    driver, resp = _require_driver()
    if resp is not None:
        # тук все пак връщаме JSON, защото JS очаква {ok: true}
        return {"ok": False, "error": "Няма шофьор в сесията"}, 400

    driver_id = int(driver.get("id"))
    date_str = (request.form.get("date") or "").strip()
    if not date_str:
        return {"ok": False, "error": "Липсва дата."}, 400

    # тук можеш да провериш дали date_str е в диапазона на поръчката, ако искаш
    logs_store = _load_json(LOGS_FILE, {"logs": []})
    logs = logs_store.get("logs", []) or []

    # търсим запис за (driver_id, order_id, date)
    target = None
    for L in logs:
        if (str(L.get("driver_id")) == str(driver_id)
                and str(L.get("order_id")) == str(order_id)
                and str(L.get("date"))[:10] == date_str):
            target = L
            break

    if not target:
        target = {
            "driver_id": driver_id,
            "order_id": order_id,
            "date": date_str,  # ВНИМАНИЕ: да остане СТРОК, не date-обект!
        }
        logs.append(target)

    # полета от формата – само тези, които ползваш в шаблона
    fields = [
        "bus_start",
        "work_start",
        "odo_start",
        "bus_condition",
        "notes_start",
        "bus_end",
        "work_end",
        "odo_end",
        "diesel_amount",
        "diesel_liters",
        "notes_end",
    ]

    for f in fields:
        if f in request.form:
            target[f] = request.form.get(f) or ""

    # други разходи – ще ги съберем в списък [{amount, desc}, ...]
    other_amounts = request.form.getlist("other_amount[]")
    other_descs = request.form.getlist("other_desc[]")
    others = []
    for a, dsc in zip(other_amounts, other_descs):
        a = (a or "").strip()
        dsc = (dsc or "").strip()
        if not a and not dsc:
            continue
        others.append({
            "amount": a,
            "desc": dsc,
        })
    target["other_expenses"] = others

    target["updated_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    logs_store["logs"] = logs
    _save_json(LOGS_FILE, logs_store)

    return {"ok": True}


# =========================================================
# Потвърждение на поръчка – "Потвърждавам поръчката"
# =========================================================
@bp.post("/orders/<int:order_id>/confirm", endpoint="order_confirm")
def order_confirm(order_id: int):
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    store = _load_orders_store()
    order = _find_driver_order(store, order_id, driver_id=int(driver.get("id")))
    if not order:
        flash("Поръчката не е намерена или не е за този шофьор.", "warning")
        return redirect(url_for("driver_portal.dashboard"))

    ack = order.get("ack") or {}
    now_iso = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ack["confirmed_at"] = now_iso
    ack["last_seen_version"] = ack.get("current_version", 1)
    order["ack"] = ack

    _save_orders_store(store)
    flash("Поръчката е потвърдена.", "success")
    return redirect(url_for("driver_portal.order_detail", order_id=order_id))


# =========================================================
# Смяна на статус на изпълнение – "Тръгнах / Пристигнах / ..."
# =========================================================
@bp.post("/orders/<int:order_id>/status", endpoint="order_set_status")
def order_set_status(order_id: int):
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    new_status = (request.form.get("status") or "").strip()
    allowed_keys = [k for (k, _label) in STATUS_STEPS]
    if new_status not in allowed_keys:
        flash("Невалиден статус.", "warning")
        return redirect(url_for("driver_portal.order_detail", order_id=order_id))

    store = _load_orders_store()
    order = _find_driver_order(store, order_id, driver_id=int(driver.get("id")))
    if not order:
        flash("Поръчката не е намерена или не е за този шофьор.", "warning")
        return redirect(url_for("driver_portal.dashboard"))

    execution = order.get("execution") or {}
    current_status = execution.get("current", "planned")

    status_index_map = {k: i for i, k in enumerate(allowed_keys)}
    cur_idx = status_index_map.get(current_status, 0)
    new_idx = status_index_map.get(new_status, cur_idx)

    if new_idx <= cur_idx:
        flash("Не може да върнеш статус назад.", "info")
        return redirect(url_for("driver_portal.order_detail", order_id=order_id))
    if new_idx != cur_idx + 1:
        flash("Статусите трябва да се минават последователно.", "info")
        return redirect(url_for("driver_portal.order_detail", order_id=order_id))

    now_iso = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timeline = execution.get("timeline") or []
    timeline.append(
        {
            "status": new_status,
            "changed_at": now_iso,
        }
    )
    execution["current"] = new_status
    execution["timeline"] = timeline
    order["execution"] = execution

    _save_orders_store(store)
    flash("Статусът на поръчката е обновен.", "success")
    return redirect(url_for("driver_portal.order_detail", order_id=order_id))

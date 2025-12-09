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
    Статистики за месечните отчети в кабинета.

    Всичко се чете САМО от driver_logs.json:
      - worked_hours
      - km (km или от odo_start/odo_end)
      - разходи: гориво, тол, паркинг, фери, други
    """
    logs = _load_logs_raw()
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
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

    # Обхождаме всички логове за шофьора и за месеца
    for L in logs:
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

        # ЧАСОВЕ
        worked_hours = float(L.get("worked_hours") or 0.0)
        rec["hours"] += worked_hours

        # КМ – km или от одометър
        odo_start = _fnum(L.get("odo_start"), 0.0)
        odo_end = _fnum(L.get("odo_end"), 0.0)
        km_val = _fnum(L.get("km"), 0.0)
        if km_val <= 0 and odo_end > 0 and odo_end > odo_start:
            km_val = odo_end - odo_start
        rec["km"] += km_val

        # РАЗХОДИ
        fuel_liters = _fnum(L.get("diesel_liters") or L.get("fuel_liters"), 0.0)
        fuel_total = _fnum(L.get("diesel_amount") or L.get("fuel_total"), 0.0)
        tolls = _fnum(L.get("tolls"), 0.0)
        parking = _fnum(L.get("parking"), 0.0)
        ferry = _fnum(L.get("ferry"), 0.0)

        other_expenses_raw = L.get("other_expenses")
        other_expenses = 0.0
        if isinstance(other_expenses_raw, list):
            # формат [{amount, desc}, ...]
            for item in other_expenses_raw:
                if not isinstance(item, dict):
                    continue
                other_expenses += _fnum(item.get("amount"), 0.0)
        else:
            other_expenses = _fnum(other_expenses_raw, 0.0)

        rec["costs"] += fuel_total + tolls + parking + ferry + other_expenses

        # Автобус (по поръчка)
        oid = L.get("order_id")
        if oid is not None:
            o = orders_map.get(str(oid))
            if o:
                plate = _norm_plate(o)
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

    # --- режим на изглед: седмица / месец ---
    view_mode = (request.args.get("view") or "week").lower()
    if view_mode not in ("week", "month"):
        view_mode = "week"

    # --- избрана дата ---
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

    # --- избран месец (за month view) ---
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

    # край на месеца
    next_month = (month_start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    month_end = next_month - dt.timedelta(days=1)
    prev_month_start = (month_start - dt.timedelta(days=1)).replace(day=1)

    month_value = f"{month_start.year:04d}-{month_start.month:02d}"
    prev_month_value = f"{prev_month_start.year:04d}-{prev_month_start.month:02d}"
    next_month_value = f"{next_month.year:04d}-{next_month.month:02d}"
    month_label = month_start.strftime("%B %Y")

    # --- данни ---
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    logs_store = _load_json(LOGS_FILE, {"logs": []})

    all_orders = orders_store.get("orders", []) or []

    # индекс: (order_id, date_str) → има ли дневник
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

    # --- всички дни в месеца ---
    days_map: dict[str, dict] = {}
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

    # --- обхождаме всички поръчки на този шофьор и ги разпределяме по дни ---
    for o in all_orders:
        if str(o.get("driver_id")) != str(driver_id):
            continue

        sd, ed = _order_dates(o)
        if not sd:
            continue
        if ed is None:
            ed = sd

        # пресичане с текущия месец
        start = max(sd, month_start)
        end = min(ed, month_end)
        if start > end:
            continue

        order_id = o.get("id")

        # часове
        s_str, e_str = _parse_time_any(o)
        time_range = None
        if s_str and e_str:
            time_range = f"{s_str} – {e_str}"
        elif s_str:
            time_range = s_str
        elif e_str:
            time_range = e_str

        # маршрут
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

        # клиент (ако ти трябва в бъдеще)
        client = (
            o.get("client_name")
            or o.get("group_name")
            or o.get("customer")
            or ""
        )

        # НОВО: заглавие и автобус
        raw_title = o.get("title") or o.get("description") or ""
        if raw_title:
            title = raw_title
        elif origin or destination:
            title = f"{origin} → {destination}"
        else:
            title = f"Поръчка #{order_id}"

        plate_norm = _norm_plate(o)
        bus_plate = plate_norm or (o.get("bus_plate") or "")

        has_docs = bool(o.get("has_unread_docs") or o.get("docs_unread"))

        # разпределяне по всеки ден от периода
        d_loop = start
        while d_loop <= end:
            ymd = _ymd(d_loop)
            day_bucket = days_map.get(ymd)
            if day_bucket is not None:
                has_log = (str(order_id), ymd) in logs_index
                day_bucket["orders"].append(
                    {
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
                        # НОВО:
                        "title": title,
                        "bus_plate": bus_plate,
                    }
                )
            d_loop += dt.timedelta(days=1)

    # --- списък дни в месеца (за month view) ---
    days_month = sorted(days_map.values(), key=lambda d: d["date"])

    # --- избран ден ---
    selected_ymd = _ymd(selected_date)
    selected_day = days_map.get(selected_ymd)
    selected_orders = selected_day["orders"] if selected_day else []

    # --- седмица на избрания ден (Пн–Нд) за week view ---
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

    # кой набор дни да се показва в горната лента
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


def _load_logs_raw() -> list:
    """
    Унифицирано четене на driver_logs.json.

    Поддържа два варианта на файла:
      1) { "logs": [ ... ] }
      2) [ ... ]
    Винаги връща списък от лог-обекти.
    """
    data = _load_json(LOGS_FILE, {"logs": []})

    if isinstance(data, dict):
        logs = data.get("logs", [])
        return logs if isinstance(logs, list) else []
    elif isinstance(data, list):
        return data
    else:
        return []


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
    Табло за шофьора:
      - поръчки за ДНЕС
      - поръчки за УТРЕ
      - обобщение за днес
      - бутон за потвърждение / отмяна на потвърждение (ACK)
    """
    # ако има driver_id в query – сменяме активния шофьор в сесията
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
    tomorrow = today + dt.timedelta(days=1)
    today_label = _today_bg_label(today)
    tomorrow_label = _today_bg_label(tomorrow)

    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    all_orders = orders_store.get("orders", []) or []

    def _orders_for_day(day: dt.date):
        rows = []
        for o in all_orders:
            if str(o.get("driver_id")) != str(driver_id):
                continue
            sd, ed = _order_dates(o)
            if not sd:
                continue
            if ed is None:
                ed = sd
            if not (sd <= day <= ed):
                continue

            s_str, e_str = _parse_time_any(o)

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
            title = o.get("title") or ""

            ack = o.get("ack") or {}
            is_confirmed = bool(ack.get("confirmed_at"))

            rows.append({
                "id": o.get("id"),
                "start_time": s_str,
                "end_time": e_str,
                "origin": origin,
                "destination": destination,
                "title": title,
                "is_confirmed": is_confirmed,
            })
        # сортиране по начален час
        def _sort_key(item):
            t = _hhmm_to_time(item["start_time"])
            return t or dt.time(23, 59)
        return sorted(rows, key=_sort_key)

    today_orders = _orders_for_day(today)
    tomorrow_orders = _orders_for_day(tomorrow)

    # --- Обобщение за днес ---
    if today_orders:
        cnt = len(today_orders)
        valid_starts = [_hhmm_to_time(x["start_time"]) for x in today_orders if x["start_time"]]
        valid_ends = [_hhmm_to_time(x["end_time"]) for x in today_orders if x["end_time"]]
        first_start = min(valid_starts).strftime("%H:%M") if valid_starts else None
        last_end = max(valid_ends).strftime("%H:%M") if valid_ends else None
        today_stats = {
            "count": cnt,
            "first_start": first_start,
            "last_end": last_end,
        }
    else:
        today_stats = {"count": 0, "first_start": None, "last_end": None}

    dispatcher_phone = "+359888000000"

    return render_template(
        "drivers/dashboard.html",
        current_driver=driver,
        drivers_list=drivers_list,
        today_label=today_label,
        tomorrow_label=tomorrow_label,
        today_orders=today_orders,
        tomorrow_orders=tomorrow_orders,
        today_stats=today_stats,
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

    logs = _load_logs_raw()
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    orders_map = {str(o.get("id")): o for o in (orders_store.get("orders") or [])}

    driver_id = int(driver.get("id"))
    rows = []

    for L in logs:
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

        # км – km или от одометър
        odo_start = _fnum(L.get("odo_start"), 0.0)
        odo_end = _fnum(L.get("odo_end"), 0.0)
        km_val = _fnum(L.get("km"), 0.0)
        if km_val <= 0 and odo_end > 0 and odo_end > odo_start:
            km_val = odo_end - odo_start

        # гориво
        fuel_l = _fnum(L.get("diesel_liters") or L.get("fuel_liters"), 0.0)
        fuel_total = _fnum(L.get("diesel_amount") or L.get("fuel_total"), 0.0)

        # други разходи
        other_expenses_raw = L.get("other_expenses")
        other_expenses = 0.0
        if isinstance(other_expenses_raw, list):
            for item in other_expenses_raw:
                if not isinstance(item, dict):
                    continue
                other_expenses += _fnum(item.get("amount"), 0.0)
        else:
            other_expenses = _fnum(other_expenses_raw, 0.0)

        tolls = _fnum(L.get("tolls"), 0.0)
        parking = _fnum(L.get("parking"), 0.0)
        ferry = _fnum(L.get("ferry"), 0.0)

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
            "other_expenses": other_expenses,
            "tolls": tolls,
            "parking": parking,
            "ferry": ferry,
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
    """
    Детайлна страница за поръчка в кабинета на шофьора.
    - ACK: маркираме, че шофьорът е видял поръчката
    - EXECUTION: статуси на изпълнение (Тръгнах, Пристигнах, ...)
    - LOGS: флагове и дневни данни от driver_logs.json
    """
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    driver_id = int(driver.get("id"))

    # === 1) Намираме поръчката за този шофьор ===
    store = _load_orders_store()
    order = _find_driver_order(store, order_id, driver_id=driver_id)
    if not order:
        flash("Поръчката не е намерена или не е за този шофьор.", "warning")
        return redirect(url_for("driver_portal.dashboard"))

    # === 2) ACK – виждане / потвърждаване на поръчката ===
    ack = order.get("ack") or {}
    now_iso = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if "current_version" not in ack:
        ack["current_version"] = 1

    # маркираме, че е видяна
    ack["seen_at"] = now_iso
    if "last_seen_version" not in ack:
        ack["last_seen_version"] = ack.get("current_version", 1)

    order["ack"] = ack

    # === 3) EXECUTION – статуси на изпълнение ===
    execution = order.get("execution") or {}
    current_status = execution.get("current", "planned")

    status_keys = [k for (k, _label) in STATUS_STEPS]
    status_index_map = {k: i for i, k in enumerate(status_keys)}
    current_index = status_index_map.get(current_status, 0)

    # === 4) LOGS – четем driver_logs.json и смятаме has_log_start / has_log_end + числа за таблицата ===
    logs_store = _load_json(LOGS_FILE, {"logs": []})
    raw_logs = logs_store.get("logs", []) or []

    logs_for_order = []
    has_log_start = False
    has_log_end = False

    for L in raw_logs:
        if str(L.get("driver_id")) != str(driver_id):
            continue
        if str(L.get("order_id")) != str(order_id):
            continue

        d_obj = _d(L.get("date"))
        date_str = d_obj.strftime("%d.%m.%Y") if d_obj else str(L.get("date") or "")

        # --- одометър / км ---
        odo_start = _fnum(L.get("odo_start"), 0.0)
        odo_end   = _fnum(L.get("odo_end"), 0.0)

        km_val = _fnum(L.get("km"), 0.0)
        if km_val <= 0.0 and odo_end > 0 and odo_end > odo_start:
            km_val = odo_end - odo_start

        # --- разходи ---
        fuel_amount = _fnum(L.get("fuel_amount") or L.get("diesel_amount"), 0.0)
        tolls       = _fnum(L.get("tolls"), 0.0)
        parking     = _fnum(L.get("parking"), 0.0)
        ferry       = _fnum(L.get("ferry"), 0.0)

        other_expenses_raw = L.get("other_expenses")
        other_expenses = 0.0
        if isinstance(other_expenses_raw, list):
            # формат [{amount, desc}, ...]
            for item in other_expenses_raw:
                if not isinstance(item, dict):
                    continue
                other_expenses += _fnum(item.get("amount"), 0.0)
        else:
            other_expenses = _fnum(other_expenses_raw, 0.0)

        # флагове начало / край – за плочките
        start_present = any(
            (
                L.get("bus_start"),
                L.get("work_start"),
                L.get("odo_start"),
                L.get("bus_condition"),
                L.get("notes_start"),
            )
        )
        end_present = any(
            (
                L.get("bus_end"),
                L.get("work_end"),
                L.get("odo_end"),
                L.get("diesel_amount"),
                L.get("diesel_liters"),
                L.get("notes_end"),
                L.get("other_expenses"),
            )
        )

        if start_present:
            has_log_start = True
        if end_present:
            has_log_end = True

        logs_for_order.append(
            {
                "date": date_str,
                "work_start": L.get("work_start") or "",
                "work_end": L.get("work_end") or "",
                "odo_start": odo_start if odo_start > 0 else None,
                "odo_end": odo_end if odo_end > 0 else None,
                "km": km_val if km_val > 0 else None,
                "fuel_amount": fuel_amount,
                "tolls": tolls,
                "parking": parking,
                "ferry": ferry,
                "other_expenses": other_expenses,
            }
        )

    # Записваме обратно store (само ack / execution са променени и са чисти стрингове)
    _save_orders_store(store)

    dispatcher_phone = "+359888000000"  # TODO: вземи от settings.json, ако решиш

    return render_template(
        "drivers/order_detail.html",
        current_driver=driver,
        order=order,
        ack=ack,
        execution=execution,
        status_steps=STATUS_STEPS,
        current_status=current_status,
        current_status_index=current_index,
        dispatcher_phone=dispatcher_phone,
        logs=logs_for_order,
        has_log_start=has_log_start,
        has_log_end=has_log_end,
        page="drivers",
        active_page="orders",
    )

# =========================================================
# ORDER LOG – страница за въвеждане на дневник по поръчка
# =========================================================
@bp.get("/orders/<int:order_id>/log", endpoint="order_log")
def order_log(order_id: int):
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    driver_id = int(driver.get("id"))

    # 1) намираме поръчката за този шофьор
    store_orders = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    order = next(
        (
            o
            for o in (store_orders.get("orders") or [])
            if str(o.get("id")) == str(order_id)
            and str(o.get("driver_id")) == str(driver_id)
        ),
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
        "drivers/order_log.html",
        current_driver=driver,
        order=order,
        days=days,
        logs=logs_map,
    )


# =========================================================
# ORDER LOG SAVE – запис на дневник по поръчка (AJAX JSON)
# =========================================================
@bp.post("/orders/<int:order_id>/log/save", endpoint="order_log_save")
def order_log_save(order_id: int):
    driver, resp = _require_driver()
    if resp is not None:
        # връщаме JSON, защото JS очаква {ok: true/false}
        return {"ok": False, "error": "Няма шофьор в сесията"}, 400

    driver_id = int(driver.get("id"))
    date_str = (request.form.get("date") or "").strip()
    if not date_str:
        return {"ok": False, "error": "Липсва дата."}, 400

    logs_store = _load_json(LOGS_FILE, {"logs": []})
    logs = logs_store.get("logs", []) or []

    # търсим запис за (driver_id, order_id, date)
    target = None
    for L in logs:
        if (
            str(L.get("driver_id")) == str(driver_id)
            and str(L.get("order_id")) == str(order_id)
            and str(L.get("date"))[:10] == date_str
        ):
            target = L
            break

    if not target:
        target = {
            "driver_id": driver_id,
            "order_id": order_id,
            "date": date_str,  # да остане СТРОК, не date-обект!
        }
        logs.append(target)

    # полета от формата – тези, които ползваш в order_log.html
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

    # други разходи – [{amount, desc}, ...]
    other_amounts = request.form.getlist("other_amount[]")
    other_descs = request.form.getlist("other_desc[]")
    others = []
    for a, dsc in zip(other_amounts, other_descs):
        a = (a or "").strip()
        dsc = (dsc or "").strip()
        if not a and not dsc:
            continue
        others.append(
            {
                "amount": a,
                "desc": dsc,
            }
        )
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
    """
    AJAX endpoint от таблото:
      - action = 'confirm'   → насилствено потвърждаване
      - action = 'unconfirm' → насилствено отменяне
      - action липсва или 'toggle' → превключване според текущото състояние

    Връща JSON: { ok: true, is_confirmed: bool, confirmed_at: 'YYYY-MM-DD HH:MM:SS'|null }
    """
    driver, resp = _require_driver()
    if resp is not None:
        return {"ok": False, "error": "no driver in session"}, 400

    driver_id = int(driver.get("id"))
    store = _load_orders_store()
    order = _find_driver_order(store, order_id, driver_id=driver_id)
    if not order:
        return {"ok": False, "error": "order not found or not for this driver"}, 404

    ack = order.get("ack") or {}
    action = (request.form.get("action") or "toggle").strip().lower()

    # текущо състояние
    currently_confirmed = bool(ack.get("confirmed_at"))

    if action == "confirm":
        now_iso = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ack["confirmed_at"] = now_iso
    elif action == "unconfirm":
        ack.pop("confirmed_at", None)
    else:  # toggle
        if currently_confirmed:
            ack.pop("confirmed_at", None)
        else:
            now_iso = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ack["confirmed_at"] = now_iso

    order["ack"] = ack
    _save_orders_store(store)

    is_confirmed = bool(ack.get("confirmed_at"))
    return {
        "ok": True,
        "is_confirmed": is_confirmed,
        "confirmed_at": ack.get("confirmed_at") if is_confirmed else None,
    }



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



@bp.get("/fahrer", endpoint="fahrer")
def fahrer():
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    return render_template(
        "drivers/fahrer.html",
        current_driver=driver,
        active_page="fahrer"
    )

@bp.get("/profile", endpoint="profile")
def profile():
    """
    Профил на шофьора – базова страница.
    """
    driver, resp = _require_driver()
    if resp is not None:
        return resp

    return render_template(
        "drivers/profile.html",
        current_driver=driver,
        active_page="fahrer",   # да остане осветен табът "Fahrer"
    )


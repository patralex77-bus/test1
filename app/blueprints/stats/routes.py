# app/blueprints/stats/routes.py
# -*- coding: utf-8 -*-
import json
import os
from datetime import date, datetime, timedelta

from flask import current_app, redirect, render_template, request, url_for

from . import bp


# ======================== ОБЩИ ХЕЛПЪРИ ========================

def _proj_and_app_paths():
    """
    Връща (proj_root, app_root), където:
      app_root  = .../test1/app
      proj_root = .../test1
    """
    app_root = current_app.root_path
    proj_root = os.path.abspath(os.path.join(app_root, os.pardir))
    return proj_root, app_root


def _load_json_list(path, preferred_key=None):
    """
    Чете JSON файл и връща СПИСЪК.
    - Ако е list -> директно.
    - Ако е dict -> търси preferred_key (напр. "orders", "logs", "buses"),
      иначе първия value, който е list.
    При грешка -> [].
    """
    if not path or not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        if preferred_key and isinstance(data.get(preferred_key), list):
            return data[preferred_key]
        for v in data.values():
            if isinstance(v, list):
                return v

    return []


def _to_float(x, default=0.0):
    try:
        if x is None:
            return float(default)
        if isinstance(x, (int, float)):
            return float(x)
        return float(str(x).replace(",", ".").strip())
    except Exception:
        return float(default)


def _parse_date(s):
    """
    Очаква 'YYYY-MM-DD' или ISO 'YYYY-MM-DDTHH:MM...' – взима първите 10 символа.
    """
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


# ======================== ЧЕТЕНЕ НА ДАННИ ========================

def _load_orders():
    """
    Чете orders.json от ПРОЕКТНАТА папка /data.
    При теб: .../test1/data/orders.json
    """
    proj_root, app_root = _proj_and_app_paths()
    candidates = [
        os.path.join(proj_root, "data", "orders.json"),
        os.path.join(app_root, "..", "data", "orders.json"),
        os.path.join(app_root, "data", "orders.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return _load_json_list(p, preferred_key="orders")
    return []


def _load_buses():
    """
    Чете buses.json от APP /data.
    При теб: .../test1/app/data/buses.json
    """
    proj_root, app_root = _proj_and_app_paths()
    candidates = [
        os.path.join(app_root, "data", "buses.json"),
        os.path.join(proj_root, "app", "data", "buses.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            data = _load_json_list(p, preferred_key="buses")
            return data
    return []


def _load_telemetry():
    """
    Чете driver_logs / telemetry от /data:
      - proj_root/data/driver_logs.json
      - app_root/data/driver_logs.json
      - app_root/data/telemetry.json
      - app_root/data/drivers_logs.json

    Връща списък с логове (dict).
    """
    proj_root, app_root = _proj_and_app_paths()
    candidates = [
        os.path.join(proj_root, "data", "driver_logs.json"),   # C:\...\test1\data\driver_logs.json
        os.path.join(app_root, "data", "driver_logs.json"),
        os.path.join(app_root, "data", "telemetry.json"),
        os.path.join(app_root, "data", "drivers_logs.json"),
        os.path.join(app_root, "data", "driver_logs.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            logs = _load_json_list(p, preferred_key="logs")
            return logs
    return []


# ======================== ОБРАБОТКА НА ORDERS ========================

def _order_bus_reg(order):
    """
    Взима рег. номер на автобус от поръчка.
    """
    if not isinstance(order, dict):
        return ""
    for k in ("bus_plate", "vehicle_plate", "bus", "bus_reg_no"):
        v = order.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    return ""


def _order_dates(order):
    """
    Връща (start_date, end_date) като date().
    """
    sd = _parse_date(order.get("start_date"))
    ed = _parse_date(order.get("end_date") or order.get("start_date"))
    return sd, ed or sd


def _order_staff_total(order):
    """
    Взима разход за труд от staff_payload.total (ако има).
    """
    staff = order.get("staff_payload") or order.get("staff_payload_json") or {}
    if isinstance(staff, str):
        try:
            staff = json.loads(staff)
        except Exception:
            staff = {}
    if isinstance(staff, dict):
        return _to_float(staff.get("total"), 0.0)
    return 0.0


def _order_staff_hours(order):
    """
    Взима общите часове от staff_payload.total_hours (ако има).
    """
    staff = order.get("staff_payload") or order.get("staff_payload_json") or {}
    if isinstance(staff, str):
        try:
            staff = json.loads(staff)
        except Exception:
            staff = {}
    if isinstance(staff, dict):
        return _to_float(staff.get("total_hours"), 0.0)
    return 0.0


def _order_segments_km_and_costs(order):
    """
    Взима от segments:
      - total_km
      - fuel_cost_total (лв.)
      - toll_cost_total
      - fuel_liters_total (ако има fuel_liters / fuel_l в segments – иначе 0)
    """
    total_km = 0.0
    fuel_cost_total = 0.0
    toll_cost_total = 0.0
    fuel_liters_total = 0.0

    segments = order.get("segments") or []
    for s in segments:
        if not isinstance(s, dict):
            continue
        total_km += _to_float(s.get("km"), 0.0)
        fuel_cost_total += _to_float(s.get("fuel_cost"), 0.0)
        toll_cost_total += _to_float(s.get("toll_cost"), 0.0)
        fuel_liters_total += _to_float(
            s.get("fuel_liters") if "fuel_liters" in s else s.get("fuel_l", 0.0),
            0.0,
        )

    return total_km, fuel_cost_total, toll_cost_total, fuel_liters_total


def _order_extras_cost(order):
    """
    Взима сума на extras[].amount (всички като "други разходи").
    """
    total = 0.0
    for e in (order.get("extras") or []):
        if not isinstance(e, dict):
            continue
        total += _to_float(e.get("amount"), 0.0)
    return total


# ======================== ОБРАБОТКА НА TELEMETRY ========================

def _telemetry_stats_by_bus(telemetry, orders_by_id, dfrom, dto):
    """
    От driver_logs/telemetry правим:
      per_bus[reg] = {
        "actual_km": ...,
        "actual_fuel_l": ...,
        "actual_fuel_money": ...,
        "order_ids": set([...])  # кои поръчки реално са карани
      }

    Очакваме в логовете:
      - date
      - order_id
      - odo_start, odo_end, fuel_liters, fuel_amount
    """
    per_bus = {}

    for log in telemetry:
        if not isinstance(log, dict):
            continue

        d = _parse_date(log.get("date"))
        if not d or d < dfrom or d > dto:
            continue

        order_id = log.get("order_id")
        order = None
        if order_id is not None:
            order = orders_by_id.get(str(order_id))

        if not order:
            continue

        reg = _order_bus_reg(order)
        if not reg:
            continue

        odo_start = _to_float(log.get("odo_start"), 0.0)
        odo_end = _to_float(log.get("odo_end"), 0.0)
        km = max(0.0, odo_end - odo_start)
        fuel_l = _to_float(log.get("fuel_liters"), 0.0)
        fuel_money = _to_float(log.get("fuel_amount"), 0.0)

        bus_stats = per_bus.setdefault(
            reg,
            {
                "actual_km": 0.0,
                "actual_fuel_l": 0.0,
                "actual_fuel_money": 0.0,
                "order_ids": set(),
            },
        )
        bus_stats["actual_km"] += km
        bus_stats["actual_fuel_l"] += fuel_l
        bus_stats["actual_fuel_money"] += fuel_money
        if order_id is not None:
            bus_stats["order_ids"].add(str(order_id))

    return per_bus


# ======================== ОБРАБОТКА НА BUSES (техника) ========================

def _bus_reg(b):
    if not isinstance(b, dict):
        return ""
    for k in ("reg_no", "plate", "bus_plate", "reg", "number"):
        v = b.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    if b.get("id") is not None:
        return f"BUS#{b['id']}"
    return ""


def _bus_tech_cost_for_period(b, dfrom, dto):
    """
    Разделяме разходите за техника на:
      - фиксирани: (insurance_cost + monthly_credit) * (days/30)
      - сервиз: service_log[].amount в периода

    Връща (fixed_for_period, service_cost_for_period).
    """
    days = max(1, (dto - dfrom).days + 1)

    insurance = _to_float(b.get("insurance_cost"), 0.0)
    credit = _to_float(b.get("monthly_credit"), 0.0)
    fixed_monthly = insurance + credit
    fixed_for_period = fixed_monthly * (days / 30.0)

    service_cost = 0.0
    for e in b.get("service_log") or []:
        if not isinstance(e, dict):
            continue
        ed = _parse_date(e.get("date"))
        if not ed or ed < dfrom or ed > dto:
            continue
        service_cost += _to_float(e.get("amount"), 0.0)

    return fixed_for_period, service_cost


def _bus_consumption_l_100km(b):
    """
    Ориентировъчен разход на автобуса в l/100km от buses.json.
    Опитваме няколко възможни имена на поле.
    """
    if not isinstance(b, dict):
        return 0.0

    candidate_keys = [
        "consumption_l_100km",
        "fuel_consumption",
        "fuel_l_per_100km",
        "avg_fuel_l_100km",
        "avg_fuel",
        "consumption",
    ]
    for k in candidate_keys:
        if k in b:
            return _to_float(b.get(k), 0.0)
    return 0.0


def _build_buses_context():
    """
    Изчислява всички статистики за автобусите за избрания период
    и връща речник, който директно се подава към render_template.
    """
    today = date.today()
    dfrom = _parse_date(request.args.get("from")) or (today - timedelta(days=30))
    dto = _parse_date(request.args.get("to")) or today
    if dto < dfrom:
        dto = dfrom
    days_count = max(1, (dto - dfrom).days + 1)

    # --- 2) Данни: buses / orders / telemetry ---
    buses_raw = _load_buses()
    orders = _load_orders()
    telemetry = _load_telemetry()

    # мап от рег. номер към запис за автобуса (за разход l/100km и техника)
    buses_by_reg = {_bus_reg(b): b for b in buses_raw if _bus_reg(b)}

    orders_by_id = {
        str(o.get("id")): o
        for o in orders
        if isinstance(o, dict) and o.get("id") is not None
    }

    telemetry_by_bus = _telemetry_stats_by_bus(telemetry, orders_by_id, dfrom, dto)

    # --- 3) Подготовка на празни редове по автобус ---

    def _empty_bus_row(reg_no, inactive=False):
        return {
            "reg_no": reg_no,
            "inactive": bool(inactive),
            "orders_count": 0,

            # планирано
            "planned_km": 0.0,
            "planned_revenue": 0.0,
            "planned_pax": 0,
            "planned_fuel_cost": 0.0,    # план гориво (лв.)
            "planned_toll_cost": 0.0,
            "planned_labor_cost": 0.0,
            "planned_other_cost": 0.0,
            "planned_fuel_l": 0.0,       # план литри (от км * разход)

            # реално от телеметрия
            "actual_km": 0.0,
            "actual_fuel_l": 0.0,
            "actual_fuel_money": 0.0,   # реално гориво (лв.)
            "actual_revenue": 0.0,

            # техника
            "tech_cost_period": 0.0,
            "tech_fixed_cost_period": 0.0,   # фиксирано: застраховка+кредит
            "service_cost_period": 0.0,      # само service_log

            # обобщени разходи
            "total_cost": 0.0,
            "fuel_cost_total": 0.0,          # променливи разходи (план - гориво)
            "labor_cost_total": 0.0,
            "other_cost_total": 0.0,

            # KPI-та за табличката
            "km": 0.0,                       # used_km
            "revenue_total": 0.0,
            "revenue_per_km": 0.0,
            "revenue_per_passenger": 0.0,
            "total_cost_per_km": 0.0,        # променливи разходи / км (план)
            "fuel_cost_per_km": 0.0,
            "tech_cost_total": 0.0,
            "maint_cost_total": 0.0,         # алиас към tech_cost_total
            "maint_cost": 0.0,               # за шаблона
            "labor_cost_per_trip": 0.0,
            "gross_profit_total": 0.0,
            "gross_profit_per_trip": 0.0,
            "profit_margin_per_km": 0.0,
            "ebitda_per_km": 0.0,

            # средни стойности / KPI за натоварване
            "km_avg_day": 0.0,
            "km_avg_trip": 0.0,
            "fuel_l": 0.0,
            "fuel_per_100km": 0.0,
            "l_per_100km": 0.0,              # алиас за шаблона
            "hours": 0.0,
            "utilisation_pct": 0.0,
            "trips_per_day": 0.0,

            # цена на км (план / реално)
            "cost_per_km": 0.0,              # алиас на total_cost_per_km (план)
            "cost_per_km_planned": 0.0,
            "cost_per_km_real": 0.0,

            # гориво (лв.) – план / реално
            "fuel_money": 0.0,               # общо гориво (лв.) – реално
            "fuel_money_planned": 0.0,       # план гориво (лв.)
            "fuel_money_actual": 0.0,        # реално гориво (лв.)
        }

    bus_rows = {}
    for b in buses_raw:
        reg = _bus_reg(b)
        if not reg:
            continue
        bus_rows[reg] = _empty_bus_row(reg_no=reg, inactive=b.get("inactive", False))

    # --- 4) Попълваме реалните км и гориво от телеметрия ---
    for reg, tstats in telemetry_by_bus.items():
        if reg not in bus_rows:
            bus_rows[reg] = _empty_bus_row(reg_no=reg, inactive=False)

        row = bus_rows[reg]
        row["actual_km"] += _to_float(tstats.get("actual_km"), 0.0)
        row["actual_fuel_l"] += _to_float(tstats.get("actual_fuel_l"), 0.0)
        row["actual_fuel_money"] += _to_float(tstats.get("actual_fuel_money"), 0.0)

    # --- 5) Обработваме orders (планирани приходи, км, труд, гориво план) ---
    actual_order_ids = set()
    for reg, tstats in telemetry_by_bus.items():
        actual_order_ids |= set(tstats.get("order_ids") or [])

    for o in orders:
        if not isinstance(o, dict):
            continue

        reg = _order_bus_reg(o)
        if not reg:
            continue

        sd, ed = _order_dates(o)
        if not sd:
            continue
        if ed < dfrom or sd > dto:
            continue  # извън периода

        row = bus_rows.get(reg)
        if not row:
            row = _empty_bus_row(reg_no=reg, inactive=False)
            bus_rows[reg] = row

        row["orders_count"] += 1

        price = _to_float(o.get("price"), 0.0)
        pax = int(_to_float(o.get("pax"), 0.0))

        order_km, fuel_cost, toll_cost, fuel_liters_from_segments = _order_segments_km_and_costs(o)
        extras_cost = _order_extras_cost(o)
        labor_cost = _order_staff_total(o)
        staff_hours = _order_staff_hours(o)

        row["planned_revenue"] += price
        row["planned_pax"] += pax
        row["planned_km"] += order_km
        row["planned_fuel_cost"] += fuel_cost
        row["planned_toll_cost"] += toll_cost
        row["planned_labor_cost"] += labor_cost
        row["planned_other_cost"] += extras_cost
        row["hours"] += staff_hours

        # ПЛАН ЛИТРИ = планирани км * (разход на автобуса / 100)
        b = buses_by_reg.get(reg)
        consumption_l_100km = _bus_consumption_l_100km(b) if b else 0.0
        planned_liters_for_order = (order_km / 100.0) * consumption_l_100km
        row["planned_fuel_l"] += planned_liters_for_order

        oid = o.get("id")
        if oid is not None and str(oid) in actual_order_ids:
            row["actual_revenue"] += price

    # --- 6) Разходи за техника / период от buses.json ---
    for reg, row in bus_rows.items():
        b = buses_by_reg.get(reg)
        tech_cost = 0.0
        tech_fixed = 0.0
        service_cost = 0.0
        if b:
            # фиксирано: застраховка + кредит
            insurance = _to_float(b.get("insurance_cost"), 0.0)
            credit = _to_float(b.get("monthly_credit"), 0.0)
            days = max(1, (dto - dfrom).days + 1)
            tech_fixed = (insurance + credit) * (days / 30.0)

            # поддръжка: service_log.amount в периода
            for e in b.get("service_log") or []:
                if not isinstance(e, dict):
                    continue
                ed = _parse_date(e.get("date"))
                if not ed or ed < dfrom or ed > dto:
                    continue
                service_cost += _to_float(e.get("amount"), 0.0)

            tech_cost = tech_fixed + service_cost

        row["tech_cost_period"] = tech_cost
        row["tech_fixed_cost_period"] = tech_fixed
        row["service_cost_period"] = service_cost

    # --- 7) Финални KPI за всеки автобус ---
    for reg, row in bus_rows.items():
        planned_km = row["planned_km"]
        actual_km = row["actual_km"]
        used_km = actual_km if actual_km > 0 else planned_km

        planned_rev = row["planned_revenue"]
        actual_rev = row["actual_revenue"]
        revenue_total = actual_rev if actual_rev > 0 else planned_rev

        fuel_cost_total_planned = row["planned_fuel_cost"]
        fuel_money_actual = row.get("actual_fuel_money", 0.0)
        labor_cost_total = row["planned_labor_cost"]
        other_cost_total = row["planned_other_cost"] + row["planned_toll_cost"]
        tech_cost_total = row["tech_cost_period"]

        # променливи разходи (използват се за "Разходи / км" и EBITDA) – по план
        variable_cost = fuel_cost_total_planned + labor_cost_total + other_cost_total
        # общи разходи = променливи + техника
        total_cost = variable_cost + tech_cost_total

        orders_count = row["orders_count"] or 0
        pax_total = row["planned_pax"]
        hours = row.get("hours", 0.0) or 0.0

        # REAL km: ако няма реални, реалното е 0 (за ефективност и real cost/km)
        real_km = actual_km if actual_km > 0 else 0.0

        # средни км
        row["km_avg_day"] = (used_km / days_count) if days_count > 0 else 0.0
        row["km_avg_trip"] = (used_km / orders_count) if orders_count > 0 else 0.0

        # гориво: реални литри (за ефективност)
        used_fuel_l = row.get("actual_fuel_l", 0.0) or 0.0
        row["fuel_l"] = used_fuel_l
        row["fuel_per_100km"] = (used_fuel_l / real_km * 100.0) if real_km > 0 else 0.0
        row["l_per_100km"] = row["fuel_per_100km"]  # алиас за шаблона

        # сурови суми
        row["km"] = used_km
        row["total_cost"] = total_cost
        row["fuel_cost_total"] = fuel_cost_total_planned     # променливи разходи – план
        row["labor_cost_total"] = labor_cost_total
        row["other_cost_total"] = other_cost_total
        row["tech_cost_total"] = tech_cost_total
        row["maint_cost_total"] = tech_cost_total            # алиас за шаблона
        row["maint_cost"] = tech_cost_total

        # гориво (лв.) – план / реално
        row["fuel_money_planned"] = fuel_cost_total_planned
        row["fuel_money_actual"] = fuel_money_actual
        row["fuel_money"] = fuel_money_actual                # общо гориво – реално

        row["revenue_total"] = revenue_total

        # KPI по автобус
        row["revenue_per_km"] = (revenue_total / used_km) if used_km > 0 else 0.0
        row["revenue_per_passenger"] = (revenue_total / pax_total) if pax_total > 0 else 0.0

        # Цена/км – план и реално
        # план: променливи разходи / планирани км
        row["cost_per_km_planned"] = (variable_cost / planned_km) if planned_km > 0 else 0.0
        # реално: реални променливи разходи (реално гориво + същия труд/други) / реални км
        variable_cost_real = fuel_money_actual + labor_cost_total + other_cost_total
        row["cost_per_km_real"] = (variable_cost_real / real_km) if real_km > 0 else 0.0

        # за старите шаблони: Разходи / км = променливи разходи / used_km (по план)
        row["total_cost_per_km"] = (variable_cost / used_km) if used_km > 0 else 0.0
        row["cost_per_km"] = row["total_cost_per_km"]  # алиас, който може да се ползва другаде

        # труд / курс
        row["labor_cost_per_trip"] = (labor_cost_total / orders_count) if orders_count > 0 else 0.0

        # печалба
        gross_profit_total = revenue_total - total_cost
        row["gross_profit_total"] = gross_profit_total
        row["gross_profit_per_trip"] = (gross_profit_total / orders_count) if orders_count > 0 else 0.0

        # марж на печалба / км – след техника
        row["profit_margin_per_km"] = (gross_profit_total / used_km) if used_km > 0 else 0.0

        # EBITDA = приходи - променливи разходи (без техника)
        ebitda_total = revenue_total - variable_cost
        row["ebitda_per_km"] = (ebitda_total / used_km) if used_km > 0 else 0.0

        # натоварване: максимум 15 часа/ден
        if days_count > 0:
            row["trips_per_day"] = (orders_count / days_count)
            row["utilisation_pct"] = min(100.0, (hours / (days_count * 15.0)) * 100.0)
        else:
            row["trips_per_day"] = 0.0
            row["utilisation_pct"] = 0.0

    # --- 8) Флот KPIs (долен ред) ---
    km_total = sum(r["km"] for r in bus_rows.values())
    real_km_total = sum(r["actual_km"] for r in bus_rows.values())
    revenue_total = sum(r["revenue_total"] for r in bus_rows.values())
    pax_total = sum(r["planned_pax"] for r in bus_rows.values())
    orders_total = sum(r["orders_count"] for r in bus_rows.values())
    fuel_money_planned_total = sum(r["fuel_money_planned"] for r in bus_rows.values())
    fuel_money_actual_total = sum(r["fuel_money_actual"] for r in bus_rows.values())
    labor_cost_total = sum(r["labor_cost_total"] for r in bus_rows.values())
    other_cost_total = sum(r["other_cost_total"] for r in bus_rows.values())
    tech_cost_total_all = sum(r["tech_cost_total"] for r in bus_rows.values())
    service_cost_total_all = sum(r["service_cost_period"] for r in bus_rows.values())
    fuel_l_total = sum(r["fuel_l"] for r in bus_rows.values())
    planned_fuel_l_total = sum(r["planned_fuel_l"] for r in bus_rows.values())
    hours_total = sum(r["hours"] for r in bus_rows.values())

    # флотни общи и променливи разходи (по план)
    variable_cost_total = fuel_money_planned_total + labor_cost_total + other_cost_total
    total_cost_total = variable_cost_total + tech_cost_total_all

    buses_count = len(bus_rows) if bus_rows else 1

    fuel_cost_diff_total = fuel_money_planned_total - fuel_money_actual_total

    # реална цена/км за флот (променливи разходи реално / реални км)
    variable_cost_real_total = fuel_money_actual_total + labor_cost_total + other_cost_total
    cost_per_km_real_fleet = (variable_cost_real_total / real_km_total) if real_km_total > 0 else 0.0

    fleet = {
        "revenue_total": revenue_total,
        "revenue_per_km": (revenue_total / km_total) if km_total > 0 else 0.0,
        "revenue_per_passenger": (revenue_total / pax_total) if pax_total > 0 else 0.0,

        # гориво – план / реално
        "fuel_cost_total_planned": fuel_money_planned_total,
        "fuel_cost_total_actual": fuel_money_actual_total,
        "fuel_cost_diff_total": fuel_cost_diff_total,
        "fuel_cost_total": fuel_money_actual_total,        # total fuel cost – реално
        "fuel_money_total": fuel_money_actual_total,       # за шаблоните
        "fuel_cost_per_km": (fuel_money_actual_total / real_km_total) if real_km_total > 0 else 0.0,

        # техника и поддръжка
        "tech_cost_total": tech_cost_total_all,
        "maint_cost_total": tech_cost_total_all,
        "maint_cost": tech_cost_total_all,
        "service_cost_total": service_cost_total_all,

        "labor_cost_total": labor_cost_total,
        "labor_cost_per_trip": (labor_cost_total / orders_total) if orders_total > 0 else 0.0,
        "other_cost_total": other_cost_total,

        "total_cost": total_cost_total,
        # тук "Разходи / км" = само променливи разходи / км (по план)
        "total_cost_per_km": (variable_cost_total / km_total) if km_total > 0 else 0.0,
        "cost_per_km": (variable_cost_total / km_total) if km_total > 0 else 0.0,
        "cost_per_km_real": cost_per_km_real_fleet,

        "gross_profit_total": revenue_total - total_cost_total,
        "profit_margin_per_km": ((revenue_total - total_cost_total) / km_total) if km_total > 0 else 0.0,

        # EBITDA за флот: приходи - променливи разходи (без техника)
        "ebitda_total": revenue_total - variable_cost_total,
        "ebitda_per_km": ((revenue_total - variable_cost_total) / km_total) if km_total > 0 else 0.0,

        "km_avg_day": (km_total / days_count) if days_count > 0 else 0.0,
        "km_avg_trip": (km_total / orders_total) if orders_total > 0 else 0.0,

        "fuel_l": fuel_l_total,
        "fuel_per_100km": (fuel_l_total / real_km_total * 100.0) if real_km_total > 0 else 0.0,
        "l_per_100km": (fuel_l_total / real_km_total * 100.0) if real_km_total > 0 else 0.0,

        "hours_total": hours_total,
        "trips_per_bus_per_day": (orders_total / (days_count * buses_count)) if days_count > 0 and buses_count > 0 else 0.0,
        "utilisation_pct": (hours_total / (days_count * buses_count * 15.0) * 100.0) if days_count > 0 and buses_count > 0 else 0.0,
    }

    totals = {
        "km": km_total,
        "orders": orders_total,
        "pax": pax_total,
        "fuel_l": fuel_l_total,              # реални литри
        "fuel_l_planned": planned_fuel_l_total,
        "fuel_cost": fuel_money_actual_total,
        "tech_cost": tech_cost_total_all,
        "labor_cost": labor_cost_total,
        "other_cost": other_cost_total,
        "total_cost": total_cost_total,
        "revenue": revenue_total,
        "gross_profit": revenue_total - total_cost_total,
        "ebitda": revenue_total - variable_cost_total,
        "hours": hours_total,
        "buses": buses_count,
        "days": days_count,
    }

    # --- 9) Подреждаме редовете така, че r.reg_no и r.stats да съществуват ---
    rows = []
    for reg, stats in bus_rows.items():
        bus = buses_by_reg.get(reg, {
            "reg_no": reg,
            "inactive": stats.get("inactive", False),
        })
        rows.append({
            "reg_no": bus.get("reg_no", reg),
            "inactive": bus.get("inactive", stats.get("inactive", False)),
            "stats": stats,
        })

    rows = sorted(
        rows,
        key=lambda r: (r["inactive"], r["reg_no"]),
    )

    period = request.args.get("period", "custom")

    return {
        "dfrom": dfrom.isoformat(),
        "dto": dto.isoformat(),
        "days_count": days_count,
        "rows": rows,
        "fleet": fleet,
        "totals": totals,
        "period": period,
    }


# ======================== ROUTES ========================

@bp.route("/")
def index():
    return render_template("stats/index.html")  # празна или почти празна страница


@bp.route("/buses/stats")
def buses_stats():
    ctx = _build_buses_context()
    return render_template("stats/statbus.html", **ctx)


@bp.route("/buses/finance")
def buses_finance():
    ctx = _build_buses_context()
    return render_template("stats/finbus.html", **ctx)


@bp.route("/buses")
def buses():
    # за съвместимост – пренасочваме към статистиката
    return redirect(url_for("stats.buses_stats"))

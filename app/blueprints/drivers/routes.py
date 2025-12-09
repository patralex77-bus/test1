# -*- coding: utf-8 -*-
from __future__ import annotations

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    current_app,
    has_app_context,
    session,
)
from pathlib import Path
import json
import datetime as dt
import secrets
import os

# =========================================================
# Blueprint
# =========================================================
bp = Blueprint("drivers", __name__, url_prefix="/drivers", template_folder="templates")

# =========================================================
# Пътища към данни
# =========================================================
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"

# Новите заплати (UI: /settings/payroll); legacy: settings.json
SETTINGS_PAYROLL_JSON = DATA_DIR / "settings_payroll.json"
SETTINGS_JSON = DATA_DIR / "settings.json"

DRIVERS_FILE = DATA_DIR / "drivers.json"
TOKENS_FILE = DATA_DIR / "driver_tokens.json"
LOGS_FILE = DATA_DIR / "driver_logs.json"       # дневници per day (driver/order/date)
ORDERS_FILE = DATA_DIR / "orders.json"
TELEMETRY_FILE = DATA_DIR / "telemetry.json"    # НОВО: сурови телеметрични записи (за статистика)

# автобуси – за валидиране на табела/ID
from app.blueprints.buses import fetch_buses_list


# =========================================================
# Helpers: I/O
# =========================================================
def _load_json(path: Path, default):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # ако файлът е повреден – върни default и презапиши, за да не троши страниците
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# =========================================================
# Helpers: дати/числа/интервали
# =========================================================
def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _ymd(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def _daterange(s: dt.date, e: dt.date):
    one = dt.timedelta(days=1)
    d = s
    while d <= e:
        yield d
        d += one


def _now_local_date() -> dt.date:
    return dt.date.today()


def _hours_between(hhmm_start: str, hhmm_end: str) -> float:
    """Изчислява часове между HH:MM и HH:MM. Ако краят е преди началото -> през полунощ."""
    try:
        t1 = dt.datetime.strptime(hhmm_start, "%H:%M")
        t2 = dt.datetime.strptime(hhmm_end, "%H:%M")
        if t2 < t1:
            t2 = t2 + dt.timedelta(days=1)
        delta = t2 - t1
        return round(delta.total_seconds() / 3600.0, 2)
    except Exception:
        return 0.0


def _fnum(v, default=0.0):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return default


# =========================================================
# Helpers: модели/търсене
# =========================================================
def _get_driver(drivers_store, did):
    sid = str(did)
    for d in drivers_store.get("drivers", []) or []:
        if str(d.get("id")) == sid:
            return d
    return None


def _get_order(orders_store, oid):
    sid = str(oid)
    for o in orders_store.get("orders", []) or []:
        if str(o.get("id")) == sid:
            return o
    return None


def _order_dates(o):
    """Връща (start_date, end_date) като datetime.date, ако са валидни; иначе None."""
    try:
        sd = dt.date.fromisoformat(str(o.get("start_date") or o.get("date"))[:10])
    except Exception:
        sd = None
    if not sd:
        return None, None
    try:
        ed = dt.date.fromisoformat(str(o.get("end_date") or o.get("start_date") or o.get("date"))[:10])
    except Exception:
        ed = sd
    return sd, ed


def _overlap(a1, a2, b1, b2):
    """True ако [a1,a2] и [b1,b2] се засичат (границите включително)."""
    if not a1 or not a2 or not b1 or not b2:
        return False
    return max(a1, b1) <= min(a2, b2)


def _driver_conflicts(orders_store, driver_id, new_order_id):
    """
    Връща списък от поръчки, които конфликтват по период с new_order_id за подадения driver_id.
    Ако new_order_id няма период или не е намерена – празен списък.
    """
    new_o = _get_order(orders_store, new_order_id)
    if not new_o:
        return []
    ns, ne = _order_dates(new_o)
    if not ns:
        return []
    conflicts = []
    for o in orders_store.get("orders", []) or []:
        if str(o.get("id")) == str(new_order_id):
            continue
        if str(o.get("driver_id")) != str(driver_id):
            continue
        os, oe = _order_dates(o)
        if os and _overlap(ns, ne, os, oe):
            conflicts.append(o)
    return conflicts


# =========================================================
# Helpers: Payroll (нормализация от settings_payroll.json/legacy)
# =========================================================
def _num(x, default=0.0):
    try:
        return float(x)
    except Exception:
        try:
            return float(str(x).replace(",", "."))
        except Exception:
            return default


def _payroll_path() -> Path:
    """
    Връща пътя до файла със заплатите:
      1) settings_payroll.json (новият UI /settings/payroll)
      2) <app.root_path>/data/settings_payroll.json (ако има app контекст)
      3) fallback към legacy settings.json
    """
    if SETTINGS_PAYROLL_JSON.exists():
        return SETTINGS_PAYROLL_JSON
    if has_app_context():
        cand = Path(current_app.root_path) / "data" / "settings_payroll.json"
        if cand.exists():
            return cand
    return SETTINGS_PAYROLL_JSON


def load_payroll_settings() -> dict:
    """
    1) Чете data/settings_payroll.json (създаван от /settings/payroll).
    2) Ако липсва – чете data/settings.json → store['payroll'] (legacy).
    Връща нормализирани ключове: daily_fixed, hourly_contract, hourly_custom, min_hours, max_hours
    """
    p = _payroll_path()
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            raw = {}
        src = {
            "daily_fixed": raw.get("daily_fixed"),
            "hourly_contract": raw.get("hourly_contract"),
            "hourly_custom": raw.get("hourly_custom"),
            "min_hours": raw.get("min_hours"),
            "max_hours": raw.get("max_hours"),
        }
    else:
        legacy = _load_json(SETTINGS_JSON, {"payroll": {}})
        src = legacy.get("payroll") or {}

    daily_fixed = _num(src.get("daily_fixed", 0))
    hourly_contract = _num(src.get("hourly_contract", src.get("hourly_rate", src.get("kv_per_day", 0))))
    hourly_custom = _num(src.get("hourly_custom", src.get("hourly_rate", 0)))
    min_hours = _num(src.get("min_hours", 0))
    max_hours = _num(src.get("max_hours", 24))
    if max_hours < min_hours:
        max_hours = min_hours

    return {
        "daily_fixed": daily_fixed,
        "hourly_contract": hourly_contract,
        "hourly_custom": hourly_custom,
        "min_hours": min_hours,
        "max_hours": max_hours,
    }


def _purge_driver_order_data(driver_id: int, order_id: int) -> dict:
    """
    Изчиства незабавно:
      - driver_logs.json: всички логове за (driver_id, order_id)
      - driver_tokens.json: всички токени за (driver_id, order_id)
      - telemetry.json (ако съществува): всички записи за (driver_id, order_id)
    Връща статистика колко е изтрито от всеки файл.
    """
    # logs
    logs_store = _load_json(LOGS_FILE, {"logs": []})
    before_logs = len(logs_store.get("logs", []))
    logs_store["logs"] = [
        L for L in (logs_store.get("logs", []) or [])
        if not (str(L.get("driver_id")) == str(driver_id) and str(L.get("order_id")) == str(order_id))
    ]
    after_logs = len(logs_store.get("logs", []))
    _save_json(LOGS_FILE, logs_store)

    # tokens
    tokens_store = _load_json(TOKENS_FILE, {"tokens": []})
    before_tokens = len(tokens_store.get("tokens", []))
    tokens_store["tokens"] = [
        t for t in (tokens_store.get("tokens", []) or [])
        if not (str(t.get("driver_id")) == str(driver_id) and str(t.get("order_id")) == str(order_id))
    ]
    after_tokens = len(tokens_store.get("tokens", []))
    _save_json(TOKENS_FILE, tokens_store)

    # telemetry (ако файлът го има/ползва се)
    try:
        telemetry = _load_json(TELEMETRY_FILE, [])
        before_tel = len(telemetry) if isinstance(telemetry, list) else 0
        if isinstance(telemetry, list):
            telemetry = [
                x for x in telemetry
                if not (str(x.get("driver_id")) == str(driver_id) and str(x.get("order_id")) == str(order_id))
            ]
            _save_json(TELEMETRY_FILE, telemetry)
            after_tel = len(telemetry)
        else:
            before_tel = after_tel = 0
    except Exception:
        before_tel = after_tel = 0

    return {
        "logs_deleted": before_logs - after_logs,
        "tokens_deleted": before_tokens - after_tokens,
        "telemetry_deleted": before_tel - after_tel,
    }


# =========================================================
# Helpers: токени/валидност
# =========================================================
def _token_is_active(token_obj: dict, order_obj: dict) -> bool:
    """
    Токенът е активен до 00:00 на деня СЛЕД end_date на поръчката.
    Ако липсва end_date -> ползваме start_date.
    На самия 'expires_on' (00:00) токенът вече е НЕактивен.
    """
    if not token_obj or not order_obj:
        return False
    base = order_obj.get("end_date") or order_obj.get("start_date")
    try:
        end_d = dt.date.fromisoformat(str(base)[:10])
    except Exception:
        return False
    expires_on = end_d + dt.timedelta(days=1)
    today = _now_local_date()
    return today < expires_on


def _filter_active_tokens(tokens: list[dict], orders_map: dict[str, dict]) -> list[dict]:
    out = []
    for t in tokens or []:
        o = orders_map.get(str(t.get("order_id")))
        if _token_is_active(t, o):
            out.append(t)
    return out


# =========================================================
# Helpers: Telemetry (НОВО)
# =========================================================
def _data_dir_candidates():
    app_root = current_app.root_path if has_app_context() else str(ROOT / "app")
    proj_root = os.path.abspath(os.path.join(app_root, os.pardir))
    inst_root = current_app.instance_path if has_app_context() else str(ROOT / "instance")
    cwd_root = os.getcwd()
    env_dir = os.environ.get("BUSOPS_DATA_DIR")
    return [
        os.path.join(app_root, "data"),
        os.path.join(proj_root, "data"),
        os.path.join(inst_root, "data"),
        os.path.join(cwd_root, "data"),
        str(DATA_DIR),
        env_dir,
    ]


def _telemetry_path() -> Path:
    for d in _data_dir_candidates():
        if not d:
            continue
        try:
            Path(d).mkdir(parents=True, exist_ok=True)
            return Path(d) / "telemetry.json"
        except Exception:
            continue
    # последен шанс – локална data/
    Path("data").mkdir(exist_ok=True)
    return Path("data") / "telemetry.json"


def _load_telemetry() -> list:
    p = _telemetry_path()
    if not p.exists():
        p.write_text("[]", encoding="utf-8")
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        p.write_text("[]", encoding="utf-8")
        return []


def _save_telemetry(items: list):
    p = _telemetry_path()
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm_plate(obj_or_str):
    if isinstance(obj_or_str, str):
        return obj_or_str.strip().upper()
    if isinstance(obj_or_str, dict):
        for k in ("reg_no", "reg", "plate", "bus_plate", "number", "registration", "regnum"):
            v = obj_or_str.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip().upper()
    return ""


def _bus_index():
    """Връща (by_plate, by_id) за бързо валидиране и намиране на bus_id."""
    by_plate, by_id = {}, {}
    try:
        buses = fetch_buses_list()
        for b in buses:
            plate = _norm_plate(b)
            if plate:
                by_plate[plate] = b
            if b.get("id") is not None:
                by_id[int(b["id"])] = b
    except Exception:
        pass
    return by_plate, by_id


# --- COMPLIANCE HELPERS (винаги спрямо днешната дата) ---

def _parse_hhmm(s: str) -> dt.time | None:
    try:
        return dt.datetime.strptime((s or '').strip(), "%H:%M").time()
    except Exception:
        return None


def _hours_gap(prev_end: str | None, today_start: str | None) -> float | None:
    """
    Почивка (часове) между вчерашния край и днешното начало.
    Ако някое липсва: fallback ~ 24 - worked_hours_prev (грубо) или 24.0 ако няма данни.
    """
    t_end = _parse_hhmm(prev_end or "")
    t_start = _parse_hhmm(today_start or "")
    if t_end and t_start:
        # разлика през полунощ
        dt_end = dt.datetime.combine(dt.date.today() - dt.timedelta(days=1), t_end)
        dt_start = dt.datetime.combine(dt.date.today(), t_start)
        if dt_start <= dt_end:
            dt_start += dt.timedelta(days=1)
        return round((dt_start - dt_end).total_seconds() / 3600.0, 2)
    return None  # липсват точни времена


def _compliance_metrics(driver_logs: list[dict], ref_date: dt.date) -> dict:
    """
    driver_logs: елементи с ключове:
      date (YYYY-MM-DD), worked_hours (float), work_start (HH:MM), work_end (HH:MM)
    ref_date: днешната дата (проверките винаги спрямо нея)
    """
    # индексиране по ISO дата
    by_date = {str(L.get("date"))[:10]: L for L in (driver_logs or []) if L.get("date")}
    ymd = ref_date.strftime("%Y-%m-%d")
    y_ymd = (ref_date - dt.timedelta(days=1)).strftime("%Y-%m-%d")

    today_log = by_date.get(ymd) or {}
    yest_log = by_date.get(y_ymd) or {}

    # 1) Дневен лимит ≤ 13 ч (работно време ~ worked_hours)
    today_hours = float(today_log.get("worked_hours") or 0.0)
    day_ok = today_hours <= 13.0

    # 2) Дневна почивка ≥ 11 ч (между вчерашния край и днешното начало)
    gap = _hours_gap(yest_log.get("work_end"), today_log.get("work_start"))
    if gap is None:
        # fallback, ако нямаме точни часове: груба оценка
        y_hours = float(yest_log.get("worked_hours") or 0.0)
        gap = max(0.0, 24.0 - y_hours)
    daily_rest_ok = gap >= 11.0

    # 3) Двуседмичен лимит ≤ 90 ч (последните 14 дни включително днес)
    start_14 = ref_date - dt.timedelta(days=13)
    total14 = 0.0
    d = start_14
    while d <= ref_date:
        rec = by_date.get(d.strftime("%Y-%m-%d")) or {}
        total14 += float(rec.get("worked_hours") or 0.0)
        d += dt.timedelta(days=1)
    fortnight_ok = total14 <= 90.0

    # 4) Седмична непрекъсната почивка ≥ 45 ч:
    #    Приближение: търсим ≥ 48ч прозорец в последните 7 дни (≥ 2 поредни дни без работа).
    last7_start = ref_date - dt.timedelta(days=6)
    off_streak = 0
    two_days_off_found = False
    d = last7_start
    while d <= ref_date:
        rec = by_date.get(d.strftime("%Y-%m-%d")) or {}
        hrs = float(rec.get("worked_hours") or 0.0)
        if hrs < 1e-6:  # безсмислено малки стойности = ден почивка
            off_streak += 1
            if off_streak >= 2:
                two_days_off_found = True
        else:
            off_streak = 0
        d += dt.timedelta(days=1)
    weekly_rest_ok = two_days_off_found

    return {
        "ref_date": ymd,
        "day_hours": round(today_hours, 2),
        "day_ok": day_ok,
        "daily_rest_hours": round(gap, 2),
        "daily_rest_ok": daily_rest_ok,
        "fortnight_hours": round(total14, 2),
        "fortnight_ok": fortnight_ok,
        "weekly_rest_ok": weekly_rest_ok,
        "weekly_rest_note": "Открит прозорец ≥48ч през последните 7 дни" if weekly_rest_ok else "Няма ≥48ч прозорец в последните 7 дни",
    }


# =========================================================
# Views: drivers CRUD
# =========================================================
@bp.get("/reports", endpoint="reports")
def drivers_reports():
    # зареждаме шофьорите
    drivers_store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    drivers_raw = drivers_store.get("drivers", []) or []

    drivers = []
    for d in drivers_raw:
        drivers.append({
            "id": d.get("id"),
            "first_name": d.get("first_name") or "",
            "last_name": d.get("last_name") or "",
        })

    drivers.sort(key=lambda x: ((x["last_name"] or "").lower(), (x["first_name"] or "").lower(), int(x["id"] or 0)))

    if not drivers:
        # няма шофьори – просто празен екран
        return render_template(
            "drivers/reports.html",
            page="drivers_reports",
            drivers=[],
            selected_driver=None,
            selected_driver_id=None,
            month_value="",
            prev_month_value="",
            next_month_value="",
            month_label="",
            totals=None,
            stats_day=[],
            stats_week=[],
        )

    # избран шофьор (по параметър или първият)
    driver_id_param = request.args.get("driver_id", "") or ""
    try:
        selected_driver_id = int(driver_id_param) if driver_id_param else int(drivers[0]["id"])
    except Exception:
        selected_driver_id = int(drivers[0]["id"])

    selected_driver = next((d for d in drivers_raw if int(d.get("id") or 0) == selected_driver_id), None)

    # месец (YYYY-MM)
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

    # последен ден от месеца
    next_month = (month_start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    month_end = next_month - dt.timedelta(days=1)

    # за навигацията
    prev_month_start = (month_start - dt.timedelta(days=1)).replace(day=1)
    next_month_start = next_month

    month_value = f"{month_start.year:04d}-{month_start.month:02d}"
    prev_month_value = f"{prev_month_start.year:04d}-{prev_month_start.month:02d}"
    next_month_value = f"{next_month_start.year:04d}-{next_month_start.month:02d}"
    month_label = month_start.strftime("%B %Y")

    # изчисляваме статистиките
    totals, stats_day, stats_week = _compute_driver_stats_for_month(
        driver_id=selected_driver_id,
        month_start=month_start,
        month_end=month_end,
    )

    # превръщаме totals в прост обект (за Jinja е удобно)
    class TotalsObj:
        def __init__(self, d):
            self.hours = d.get("hours", 0.0)
            self.km = d.get("km", 0.0)
            self.costs = d.get("costs", 0.0)

    return render_template(
        "drivers/reports.html",
        page="drivers_reports",
        drivers=drivers,
        selected_driver=selected_driver,
        selected_driver_id=selected_driver_id,
        month_value=month_value,
        prev_month_value=prev_month_value,
        next_month_value=next_month_value,
        month_label=month_label,
        totals=TotalsObj(totals),
        stats_day=stats_day,
        stats_week=stats_week,
    )



@bp.get("/", endpoint="list")
def drivers_list():
    store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    drivers = store.get("drivers", [])

    def _key(d):
        return (
            str(d.get("last_name") or "").lower(),
            str(d.get("first_name") or "").lower(),
            int(d.get("id") or 0),
        )

    drivers = sorted(drivers, key=_key)
    return render_template("drivers/list.html", drivers=drivers)


@bp.route("/new", methods=["GET", "POST"], endpoint="new")
def drivers_new():
    if request.method == "POST":
        store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
        did = store.get("next_id", 1)
        payload = {
            "id": did,
            "first_name": request.form.get("first_name", "").strip(),
            "last_name": request.form.get("last_name", "").strip(),
            "notes": request.form.get("notes", ""),
            "docs": {
                "license_valid_until": request.form.get("license_valid_until") or "",
                "card_valid_until": request.form.get("card_valid_until") or "",
                "passport_valid_until": request.form.get("passport_valid_until") or "",
                "med_check_valid_until": request.form.get("med_check_valid_until") or "",
            },
        }
        store.setdefault("drivers", []).append(payload)
        store["next_id"] = did + 1
        _save_json(DRIVERS_FILE, store)
        flash("Шофьорът е добавен.", "success")
        return redirect(url_for("drivers.list"))
    return render_template("drivers/entry.html", driver=None)


@bp.route("/<int:driver_id>/edit", methods=["GET", "POST"], endpoint="edit")
def drivers_edit(driver_id: int):
    store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    d = _get_driver(store, driver_id)
    if not d:
        flash("Шофьорът не е намерен.", "warning")
        return redirect(url_for("drivers.list"))

    if request.method == "POST":
        d["first_name"] = request.form.get("first_name", "").strip()
        d["last_name"] = request.form.get("last_name", "").strip()
        d["notes"] = request.form.get("notes", "")
        d.setdefault("docs", {})
        d["docs"]["license_valid_until"] = request.form.get("license_valid_until") or ""
        d["docs"]["card_valid_until"] = request.form.get("card_valid_until") or ""
        d["docs"]["passport_valid_until"] = request.form.get("passport_valid_until") or ""
        d["docs"]["med_check_valid_until"] = request.form.get("med_check_valid_until") or ""
        _save_json(DRIVERS_FILE, store)
        flash("Промените са запазени.", "success")
        return redirect(url_for("drivers.detail", driver_id=driver_id))

    return render_template("drivers/entry.html", driver=d)


@bp.post("/<int:driver_id>/delete", endpoint="delete")
def drivers_delete(driver_id: int):
    store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    before = len(store.get("drivers", []))
    store["drivers"] = [d for d in store.get("drivers", []) if int(d.get("id", -1)) != driver_id]
    _save_json(DRIVERS_FILE, store)
    flash("Шофьорът е изтрит." if len(store["drivers"]) < before else "Шофьорът не бе намерен.", "info")
    return redirect(url_for("drivers.list"))


# =========================================================
# API: списък шофьори за UI (dropdown)
# =========================================================
@bp.get("/api/list")
def api_drivers_list():
    """
    GET /drivers/api/list -> { "drivers": [ {id, first_name, last_name}, ... ] }
    Ползва се от календара/панела за зачисляване.
    """
    store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    out = []
    for d in store.get("drivers", []) or []:
        out.append({
            "id": d.get("id"),
            "first_name": d.get("first_name") or "",
            "last_name": d.get("last_name") or "",
        })
    out.sort(key=lambda x: ((x["last_name"] or "").lower(), (x["first_name"] or "").lower(), int(x["id"] or 0)))
    return jsonify({"drivers": out})


# =========================================================
# Driver detail + tokens (filtered by expiry)
# =========================================================
@bp.get("/<int:driver_id>", endpoint="detail")
def drivers_detail(driver_id: int):
    drivers_store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    tokens_store = _load_json(TOKENS_FILE, {"tokens": []})
    logs_store = _load_json(LOGS_FILE, {"logs": []})

    d = _get_driver(drivers_store, driver_id)
    if not d:
        flash("Шофьорът не е намерен.", "warning")
        return redirect(url_for("drivers.list"))

    assigned = [o for o in (orders_store.get("orders") or []) if str(o.get("driver_id")) == str(driver_id)]
    orders_map = {str(o.get("id")): o for o in (orders_store.get("orders") or [])}

    # само активни токени (до деня след end_date)
    driver_tokens_all = [t for t in (tokens_store.get("tokens") or []) if str(t.get("driver_id")) == str(driver_id)]
    tokens = _filter_active_tokens(driver_tokens_all, orders_map)

    # логове за календара/изчисленията
    driver_logs = [L for L in (logs_store.get("logs") or []) if str(L.get("driver_id")) == str(driver_id)]

    # ставки от файла на заплатите → payroll (НОРМАЛИЗИРАНО)
    payroll_settings = load_payroll_settings()

    today = _now_local_date()
    compliance = _compliance_metrics(driver_logs, today)

    return render_template(
        "drivers/detail.html",
        driver=d,
        assigned_orders=assigned,
        driver_logs=driver_logs,
        tokens=tokens,
        payroll_settings=payroll_settings,
        page="drivers",
        compliance=compliance,   # <— ПОДАВАМЕ КЪМ ШАБЛОНА
    )


# =========================================================
# API: check conflict (GET/POST)
# =========================================================
@bp.get("/api/check_conflict", endpoint="api_check_conflict_get")
def api_check_conflict_get():
    """
    GET /drivers/api/check_conflict?driver_id=1&start=YYYY-MM-DD&end=YYYY-MM-DD&exclude_order=<id>
    Връща {"ok":true,"conflicts":[{id,title,start_date,end_date}...]}
    """
    driver_id = request.args.get("driver_id", "").strip()
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()
    exclude = request.args.get("exclude_order", "").strip()

    if not driver_id or not start:
        return jsonify({"ok": False, "error": "missing driver_id or start"}), 400

    try:
        sd = dt.date.fromisoformat(start[:10])
    except Exception:
        return jsonify({"ok": False, "error": "invalid start"}), 400
    try:
        ed = dt.date.fromisoformat((end or start)[:10])
    except Exception:
        ed = sd

    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    conflicts = []
    for o in orders_store.get("orders", []) or []:
        if exclude and str(o.get("id")) == str(exclude):
            continue
        if str(o.get("driver_id")) != str(driver_id):
            continue
        os, oe = _order_dates(o)
        if os and _overlap(sd, ed, os, oe):
            conflicts.append({
                "id": o.get("id"),
                "title": o.get("title") or f"Поръчка #{o.get('id')}",
                "start_date": o.get("start_date"),
                "end_date": o.get("end_date") or o.get("start_date"),
            })
    return jsonify({"ok": True, "conflicts": conflicts})


@bp.post("/api/check_conflict", endpoint="api_check_conflict")
def api_check_conflict_post():
    """
    JSON:
      {
        "driver_id": <int>,                 # задължително
        "start_date": "YYYY-MM-DD",         # задължително
        "end_date":   "YYYY-MM-DD",         # по избор (ако липсва -> start_date)
        "ignore_order_id": <int|null>       # по избор: игнорирай тази поръчка
      }
    -> { "ok": true, "conflict": bool, "overlaps": [...] }
    """
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"ok": False, "error": "invalid json"}), 400

    def _dloc(s):
        try:
            return dt.date.fromisoformat(str(s)[:10])
        except Exception:
            return None

    driver_id = payload.get("driver_id", None)
    sd_raw = payload.get("start_date", "")
    ed_raw = payload.get("end_date", "") or sd_raw
    ignore_id = payload.get("ignore_order_id", None)

    try:
        driver_id = int(driver_id)
    except Exception:
        return jsonify({"ok": False, "error": "missing or invalid driver_id"}), 400

    sd = _dloc(sd_raw)
    ed = _dloc(ed_raw)
    if not sd:
        return jsonify({"ok": False, "error": "missing or invalid start_date"}), 400
    if not ed:
        ed = sd
    if ed < sd:
        sd, ed = ed, sd

    store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    orders = store.get("orders", []) or []

    overlaps = []
    for o in orders:
        if str(o.get("driver_id", "")) != str(driver_id):
            continue
        if ignore_id is not None and str(o.get("id")) == str(ignore_id):
            continue

        os = _d(o.get("start_date") or o.get("date"))
        oe = _d(o.get("end_date") or o.get("start_date") or o.get("date")) or os
        if not os:
            continue

        if _overlap(sd, ed, os, oe):
            overlaps.append({
                "id": o.get("id"),
                "title": o.get("title") or f"Поръчка #{o.get('id')}",
                "start_date": (o.get("start_date") or ""),
                "end_date": (o.get("end_date") or o.get("start_date") or "")
            })

    return jsonify({
        "ok": True,
        "conflict": len(overlaps) > 0,
        "overlaps": overlaps
    })


# =========================================================
# Диагностика: payroll
# =========================================================
@bp.get("/api/payroll", endpoint="api_payroll")
def api_payroll():
    return jsonify({"ok": True, "payroll": load_payroll_settings()})


# =========================================================
# Tokens (генериране/маркиране/изтриване)
# =========================================================
@bp.post("/<int:driver_id>/tokens/new", endpoint="new_token")
def drivers_new_token(driver_id: int):
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    tokens_store = _load_json(TOKENS_FILE, {"tokens": []})

    order_id = (request.form.get("order_id") or "").strip()
    if not order_id:
        flash("Избери поръчка за портала.", "warning")
        return redirect(url_for("drivers.detail", driver_id=driver_id))
    if not _get_order(orders_store, order_id):
        flash("Поръчката не е намерена.", "warning")
        return redirect(url_for("drivers.detail", driver_id=driver_id))

    token = secrets.token_urlsafe(24)
    tokens_store.setdefault("tokens", []).append(
        {
            "token": token,
            "driver_id": int(driver_id),
            "order_id": int(order_id),
            "created_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "sent": False,
        }
    )
    _save_json(TOKENS_FILE, tokens_store)

    portal_url = url_for("drivers.portal", token=token, _external=True)

    flash(
        f"Генериран е портал линк: {portal_url}",
        "success",
    )
    return redirect(url_for("drivers.detail", driver_id=driver_id))



@bp.post("/<int:driver_id>/tokens/<token>/toggle", endpoint="toggle_token_sent")
def toggle_token_sent(driver_id: int, token: str):
    tokens_store = _load_json(TOKENS_FILE, {"tokens": []})
    changed = False
    for t in tokens_store.get("tokens", []) or []:
        if t.get("token") == token and str(t.get("driver_id")) == str(driver_id):
            t["sent"] = not bool(t.get("sent"))
            changed = True
            break
    if changed:
        _save_json(TOKENS_FILE, tokens_store)
        flash("Статусът на токена е променен.", "success")
    else:
        flash("Токенът не е намерен.", "warning")
    return redirect(url_for("drivers.detail", driver_id=driver_id))


@bp.post("/<int:driver_id>/tokens/<token>/delete", endpoint="delete_token")
def delete_token(driver_id: int, token: str):
    tokens_store = _load_json(TOKENS_FILE, {"tokens": []})
    before = len(tokens_store.get("tokens", []) or [])
    tokens_store["tokens"] = [
        t for t in tokens_store.get("tokens", []) or []
        if not (t.get("token") == token and str(t.get("driver_id")) == str(driver_id))
    ]
    after = len(tokens_store.get("tokens", []) or [])
    if after < before:
        _save_json(TOKENS_FILE, tokens_store)
        flash("Токенът е изтрит.", "success")
    else:
        flash("Токенът не беше намерен.", "warning")
    return redirect(url_for("drivers.detail", driver_id=driver_id))


# =========================================================
# Driver Portal (GET + POST save) — с автоматичен запис в telemetry.json
# =========================================================
@bp.get("/portal/<token>", endpoint="portal")
def portal(token: str):
    tokens_store = _load_json(TOKENS_FILE, {"tokens": []})
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    drivers_store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})

    t = next((x for x in tokens_store.get("tokens", []) if x.get("token") == token), None)
    if not t:
        return render_template("drivers/portal_invalid.html"), 404

    o = _get_order(orders_store, t.get("order_id"))
    d = _get_driver(drivers_store, t.get("driver_id"))
    if not o or not d:
        return render_template("drivers/portal_invalid.html"), 404

    if not _token_is_active(t, o):
        return render_template("drivers/portal_invalid.html"), 410

    # всичко е наред → логваме шофьора в кабинета
    session["driver_portal"] = {
        "driver_id": int(d.get("id")),
        "order_id": int(o.get("id")),
        "token": token,
    }

    # пращаме към dashboard в новия blueprint
    return redirect(url_for("driver_portal.dashboard"))


# Позволяваме POST както на /portal/<token>, така и на /portal/<token>/save@bp.post("/portal/<token>", endpoint="portal_save")
@bp.post("/portal/<token>", endpoint="portal_save")
@bp.post("/portal/<token>/save")
def portal_save(token: str):
    tokens_store = _load_json(TOKENS_FILE, {"tokens": []})
    logs_store   = _load_json(LOGS_FILE,   {"logs": []})
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})

    t = next((x for x in tokens_store.get("tokens", []) if x.get("token") == token), None)
    if not t:
        return jsonify({"ok": False, "error": "invalid token"}), 404

    o = _get_order(orders_store, t.get("order_id"))
    if not o or not _token_is_active(t, o):
        # токенът е активен до 00:00 на деня след end_date
        return jsonify({"ok": False, "error": "token expired"}), 410

    order_id  = int(t.get("order_id"))
    driver_id = int(t.get("driver_id"))

    # --- Диапазон на поръчката
    sd = _d(o.get("start_date") or o.get("date"))
    ed = _d(o.get("end_date") or o.get("start_date") or o.get("date")) or sd
    if not sd:
        return jsonify({"ok": False, "error": "order has no valid dates"}), 400

    today = _now_local_date()

    # --- Вземи date от формата; ако липсва -> опитай с днешна дата
    raw_date = (request.form.get("date") or request.form.get("day") or "").strip()
    if raw_date:
        date_obj = _d(raw_date)
        if not date_obj:
            return jsonify({"ok": False, "error": "invalid date"}), 400
    else:
        date_obj = today  # fallback

    # --- Правила за попълване:
    # 1) Може да се попълва само в рамките на поръчката
    if date_obj < sd or date_obj > ed:
        return jsonify({
            "ok": False,
            "error": f"date out of range; allowed: {sd.isoformat()}..{ed.isoformat()}",
        }), 400

    # 2) Може да се попълва само АКТУАЛНИЯТ ден
    if date_obj != today:
        return jsonify({
            "ok": False,
            "error": "only today is allowed for entry",
            "today": today.isoformat(),
            "requested": date_obj.isoformat(),
        }), 400

    date_str = date_obj.isoformat()

    work_start   = (request.form.get("work_start") or "").strip()  # 'HH:MM'
    work_end     = (request.form.get("work_end") or "").strip()    # 'HH:MM'
    worked_hours = _hours_between(work_start, work_end) if (work_start and work_end) else 0.0

    # числови полета (дневник)
    odo_start      = _fnum(request.form.get("odo_start"))
    odo_end        = _fnum(request.form.get("odo_end"))
    fuel_liters    = _fnum(request.form.get("fuel_liters"))
    fuel_amount    = _fnum(request.form.get("fuel_amount"))
    other_expenses = _fnum(request.form.get("other_expenses"))
    tolls          = _fnum(request.form.get("tolls"))
    parking        = _fnum(request.form.get("parking"))
    ferry          = _fnum(request.form.get("ferry"))

    payload = {
        "order_id": order_id,
        "driver_id": driver_id,
        "date": date_str,
        "odo_start": request.form.get("odo_start") or "",
        "odo_end": request.form.get("odo_end") or "",
        "fuel_liters": fuel_liters,
        "fuel_amount": fuel_amount,
        "tolls": tolls,
        "parking": parking,
        "ferry": ferry,
        "other_expenses": other_expenses,
        "work_start": work_start,
        "work_end": work_end,
        "worked_hours": worked_hours,
        "incidents": request.form.get("incidents") or "",
        "notes": request.form.get("notes") or "",
        "updated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    # upsert по (order_id, driver_id, date)
    found = False
    for i, L in enumerate(logs_store.get("logs", [])):
        if (
            str(L.get("order_id")) == str(order_id)
            and str(L.get("driver_id")) == str(driver_id)
            and L.get("date") == date_str
        ):
            logs_store["logs"][i] = payload
            found = True
            break
    if not found:
        logs_store.setdefault("logs", []).append(payload)
    _save_json(LOGS_FILE, logs_store)

    # ===== Telemetry (без промяна на твоя формат) =====
    plate_from_order = _norm_plate(o.get("vehicle_plate") or o.get("bus_plate") or "")
    by_plate, by_id = _bus_index()
    bus_id = by_plate.get(plate_from_order, {}).get("id") if plate_from_order in by_plate else None

    # km (от полето или от одометърите)
    try:
        km_val = _fnum(request.form.get("km"))
    except Exception:
        km_val = 0.0
    if km_val <= 0 and (odo_end > 0 or odo_start > 0):
        km_val = max(0.0, odo_end - odo_start)

    fuel_price_l = round(fuel_amount / fuel_liters, 4) if fuel_liters > 0 else 0.0

    telemetry_entry = {
        "date": date_str,
        "driver_id": driver_id,
        "order_id": order_id,
        "bus_reg_no": plate_from_order or None,
        "bus_id": bus_id,
        "odometer_start": odo_start if odo_start > 0 else None,
        "odometer_end": odo_end if odo_end > 0 else None,
        "km": km_val if km_val > 0 else None,
        "fuel_liters": fuel_liters if fuel_liters > 0 else None,
        "fuel_total": fuel_amount if fuel_amount > 0 else None,
        "fuel_price_l": fuel_price_l if fuel_price_l > 0 else None,
        "notes": (request.form.get("notes") or "").strip() or None,
        "created_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    telemetry = _load_telemetry()
    telemetry.append(telemetry_entry)
    _save_telemetry(telemetry)

    return jsonify({"ok": True, "hours": worked_hours})


def _compute_driver_stats_for_month(driver_id: int, month_start: dt.date, month_end: dt.date):
    """
    Връща:
      - totals: { hours, km, costs }
      - stats_day: списък по дни в месеца
          {
            date: "YYYY-MM-DD",
            date_human: "DD.MM.YYYY",
            week_in_month: int,      # 1..N
            hours, km, costs,
            buses: [...],
          }
      - stats_week: списък по календарни седмици (Пн–Нд)
          {
            year, week,
            week_in_month: int,      # 1..N
            range_start: "DD.MM",
            range_end:   "DD.MM",
            hours, km, costs,
            buses: [...],
          }

    ВАЖНО: адаптирана е за двата формата на driver_logs.json:
      - стария (worked_hours, fuel_amount, other_expenses като число ...)
      - новия от driver_portal (work_start/work_end, diesel_amount, other_expenses като списък)
    """
    # зареждаме сторове
    logs_store   = _load_json(LOGS_FILE,   {"logs": []})
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    try:
        telemetry = _load_telemetry()
        if not isinstance(telemetry, list):
            telemetry = []
    except Exception:
        telemetry = []

    telemetry_empty = not telemetry  # ако няма телеметрия – ще смятаме км от логовете

    orders_map = {str(o.get("id")): o for o in (orders_store.get("orders") or [])}

    # === Подготовка: дневни записи за ВСИЧКИ дни в месеца ===
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
            "buses": set(),   # рег. номера
            "orders": set(),  # order_id
        }
        d_cur += dt.timedelta(days=1)

    # helper дали дата е в месеца
    def _in_month_range(date_str):
        dd = _d(date_str)
        if not dd:
            return False
        return month_start <= dd <= month_end

       # === 1) LOGS: време + разходи + автобуси през поръчките ===
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

        # ----- ЧАСОВЕ -----
        worked_hours = float(L.get("worked_hours") or 0.0)
        if worked_hours <= 0.0:
            ws = (L.get("work_start") or "").strip()
            we = (L.get("work_end") or "").strip()
            if ws and we:
                worked_hours = _hours_between(ws, we)
        rec["hours"] += worked_hours

        # ----- РАЗХОДИ -----
        fuel_amount = _fnum(L.get("fuel_amount") or L.get("diesel_amount"), 0.0)
        tolls       = _fnum(L.get("tolls"), 0.0)
        parking     = _fnum(L.get("parking"), 0.0)
        ferry       = _fnum(L.get("ferry"), 0.0)

        other_expenses_val = 0.0
        raw_other = L.get("other_expenses")
        if isinstance(raw_other, list):
            for item in raw_other:
                if not isinstance(item, dict):
                    continue
                other_expenses_val += _fnum(item.get("amount"), 0.0)
        else:
            other_expenses_val = _fnum(raw_other, 0.0)

        rec["costs"] += fuel_amount + tolls + parking + ferry + other_expenses_val

        # ----- КМ ОТ ЛОГА (odo_start/odo_end или km) -----
        km_from_log = _fnum(L.get("km"), 0.0)
        if km_from_log <= 0.0:
            odo_start = _fnum(L.get("odo_start"), 0.0)
            odo_end   = _fnum(L.get("odo_end"), 0.0)
            if odo_end > 0 and odo_end > odo_start:
                km_from_log = odo_end - odo_start
        rec["km"] += km_from_log

        # ----- поръчка и автобус -----
        oid = L.get("order_id")
        if oid is not None:
            rec["orders"].add(int(oid))
            o = orders_map.get(str(oid))
            if o:
                plate = _norm_plate(o)
                if plate:
                    rec["buses"].add(plate)


    # === 2) TELEMETRY: километри + гориво + автобус ===
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

        # км от телеметрия – ако има стойност, я считаме за по-точна
        km_val = _fnum(x.get("km"), 0.0)
        if km_val > 0:
            # или overwrite, или вземи по-голямото:
            rec["km"] = max(rec["km"], km_val)

        # разходи (гориво)
        fuel_total = _fnum(x.get("fuel_total"), 0.0)
        rec["costs"] += fuel_total

        # автобус от телеметрията (рег. номер)
        if x.get("bus_reg_no"):
            plate = _norm_plate(x.get("bus_reg_no"))
            if plate:
                rec["buses"].add(plate)

        if x.get("order_id") is not None:
            rec["orders"].add(int(x.get("order_id")))

    # === Totals за месеца ===
    totals_hours = totals_km = totals_costs = 0.0
    for rec in daily.values():
        totals_hours  += rec["hours"]
        totals_km     += rec["km"]
        totals_costs  += rec["costs"]

    totals = {
        "hours": round(totals_hours, 2),
        "km": round(totals_km, 1),
        "costs": round(totals_costs, 2),
    }

    # === Групиране по КАЛЕНДАРНИ седмици (Пн–Нд) ===
    weeks = {}
    for rec in daily.values():
        iso_year = rec["iso_year"]
        iso_week = rec["iso_week"]
        key = (iso_year, iso_week)

        if key not in weeks:
            week_start = dt.date.fromisocalendar(iso_year, iso_week, 1)
            week_end   = dt.date.fromisocalendar(iso_year, iso_week, 7)
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
        bucket["km"]    += rec["km"]
        bucket["costs"] += rec["costs"]
        for b in rec["buses"]:
            bucket["buses"].add(b)

    sorted_weeks = sorted(weeks.values(), key=lambda w: w["week_start"])

    week_index = {}
    for idx, w in enumerate(sorted_weeks, start=1):
        week_index[(w["year"], w["week"])] = idx

    # === Списък по дни (stats_day) ===
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
            "orders": sorted(rec["orders"]),
        })

    # === Списък по седмици (stats_week) ===
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
# Назначаване/сваляне на поръчка (единствени, без дубликати)
# =========================================================
@bp.post("/<int:driver_id>/unassign/<int:order_id>", endpoint="unassign_order")
def drivers_unassign_order(driver_id: int, order_id: int):
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    o = _get_order(orders_store, order_id)
    if not o:
        flash("Поръчката не е намерена.", "warning")
        return redirect(url_for("drivers.detail", driver_id=driver_id))

    if str(o.get("driver_id")) != str(driver_id):
        flash("Поръчката не е назначена на този шофьор.", "info")
        return redirect(url_for("drivers.detail", driver_id=driver_id))

    # 1) изчисти всички данни свързани с (driver_id, order_id)
    stats = _purge_driver_order_data(driver_id=int(driver_id), order_id=int(order_id))

    # 2) разкачи поръчката от шофьора + ИЗРИСНИ driver_name
    o["driver_id"] = None
    o["driver_name"] = ""   # ← ключовото за календара
    _save_json(ORDERS_FILE, orders_store)

    flash(
        f"Поръчка #{order_id} е свалена от шофьора. "
        f"Премахнати са {stats['logs_deleted']} дневн., {stats['tokens_deleted']} токена"
        + (f", {stats['telemetry_deleted']} телеметрии" if stats['telemetry_deleted'] else ""),
        "success"
    )
    return redirect(url_for("drivers.detail", driver_id=driver_id))


@bp.post("/<int:driver_id>/assign", endpoint="assign_order")
def drivers_assign_order(driver_id: int):
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    oid = (request.form.get("order_id") or "").strip()
    if not oid:
        flash("Не е избрана поръчка.", "warning")
        return redirect(url_for("drivers.detail", driver_id=driver_id))

    o = _get_order(orders_store, oid)
    if not o:
        flash("Поръчката не е намерена.", "warning")
        return redirect(url_for("drivers.detail", driver_id=driver_id))

    conflicts = _driver_conflicts(orders_store, driver_id, oid)
    if conflicts:
        human = ", ".join([f"#{x.get('id')} ({x.get('start_date')}→{x.get('end_date') or x.get('start_date')})" for x in conflicts])
        flash(f"Конфликт с вече назначени: {human}. Назначаването е отказано.", "warning")
        return redirect(url_for("drivers.detail", driver_id=driver_id))

    old_driver_id = o.get("driver_id")
    if old_driver_id and str(old_driver_id) != str(driver_id):
        # поръчката се прехвърля от стар на нов шофьор → чистим данните на стария
        stats = _purge_driver_order_data(driver_id=int(old_driver_id), order_id=int(o.get("id")))
        flash(
            f"Поръчка #{o.get('id')} беше прехвърлена от шофьор #{old_driver_id} към #{driver_id}. "
            f"Премахнати от стария: {stats['logs_deleted']} дневн., {stats['tokens_deleted']} токена"
            + (f", {stats['telemetry_deleted']} телеметрии" if stats['telemetry_deleted'] else ""),
            "info"
        )

    o["driver_id"] = int(driver_id)
    _save_json(ORDERS_FILE, orders_store)
    flash(f"Поръчка #{o.get('id')} е назначена на шофьора.", "success")
    return redirect(url_for("drivers.detail", driver_id=driver_id))


# -------- Helpers за cleanup екрана --------
def _date_in_order_range(date_str: str, order: dict) -> bool:
    try:
        d = dt.date.fromisoformat(str(date_str)[:10])
    except Exception:
        return False
    s, e = _order_dates(order)
    if not s:
        return False
    e = e or s
    return s <= d <= e

def _cleanup_scan_for_driver(driver_id: int) -> dict:
    """
    Връща списъци с кандидати за чистене:
      - logs: елементи от driver_logs.json
      - tokens: елементи от driver_tokens.json
      - telemetry: елементи от telemetry.json (ако има)
    Всеки елемент има 'uid' (уникален ключ за изтриване) и 'reason'.
    """
    drivers_store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    orders_store  = _load_json(ORDERS_FILE,  {"orders": [], "next_id": 1})
    logs_store    = _load_json(LOGS_FILE,    {"logs": []})
    tokens_store  = _load_json(TOKENS_FILE,  {"tokens": []})
    try:
        telemetry = _load_json(TELEMETRY_FILE, [])
        if not isinstance(telemetry, list):
            telemetry = []
    except Exception:
        telemetry = []

    orders_map = {str(o.get("id")): o for o in (orders_store.get("orders") or [])}

    # ---- LOGS ----
    logs_out = []
    for L in logs_store.get("logs", []):
        if str(L.get("driver_id")) != str(driver_id):
            continue
        oid = str(L.get("order_id"))
        o = orders_map.get(oid)
        reason = None
        if not o:
            reason = "Липсва поръчка"
        elif str(o.get("driver_id")) != str(driver_id):
            reason = "Поръчката е назначена на друг шофьор"
        elif not _date_in_order_range(L.get("date"), o):
            reason = "Ден извън периода на поръчката"
        if reason:
            uid = f"log:{oid}:{L.get('date')}"
            logs_out.append({
                "uid": uid,
                "order_id": L.get("order_id"),
                "date": L.get("date"),
                "worked_hours": L.get("worked_hours"),
                "reason": reason,
            })

    # ---- TOKENS ----
    tokens_out = []
    for t in tokens_store.get("tokens", []):
        if str(t.get("driver_id")) != str(driver_id):
            continue
        oid = str(t.get("order_id"))
        o = orders_map.get(oid)
        reason = None
        if not o:
            reason = "Липсва поръчка"
        elif str(o.get("driver_id")) != str(driver_id):
            reason = "Поръчката е назначена на друг шофьор"
        elif not _token_is_active(t, o):
            reason = "Токенът е изтекъл"
        if reason:
            uid = f"tok:{t.get('token')}"
            tokens_out.append({
                "uid": uid,
                "order_id": t.get("order_id"),
                "token": t.get("token"),
                "created_at": t.get("created_at"),
                "sent": bool(t.get("sent")),
                "reason": reason,
            })

    # ---- TELEMETRY ----
    telemetry_out = []
    for x in telemetry:
        if str(x.get("driver_id")) != str(driver_id):
            continue
        oid = str(x.get("order_id"))
        o = orders_map.get(oid)
        reason = None
        if not o:
            reason = "Липсва поръчка"
        elif str(o.get("driver_id")) != str(driver_id):
            reason = "Поръчката е назначена на друг шофьор"
        elif not _date_in_order_range(x.get("date"), o):
            reason = "Ден извън периода на поръчката"
        if reason:
            # нямаме гарантиран id → ползваме композитен ключ за триене
            stamp = x.get("created_at") or ""
            uid = f"tel:{oid}:{x.get('date')}:{stamp}"
            telemetry_out.append({
                "uid": uid,
                "order_id": x.get("order_id"),
                "date": x.get("date"),
                "km": x.get("km"),
                "fuel_liters": x.get("fuel_liters"),
                "fuel_total": x.get("fuel_total"),
                "created_at": stamp,
                "reason": reason,
            })

    return {
        "logs": logs_out,
        "tokens": tokens_out,
        "telemetry": telemetry_out,
    }


# -------- View: екранът за почистване --------
@bp.get("/<int:driver_id>/cleanup", endpoint="cleanup")
def drivers_cleanup(driver_id: int):
    drivers_store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    d = _get_driver(drivers_store, driver_id)
    if not d:
        flash("Шофьорът не е намерен.", "warning")
        return redirect(url_for("drivers.list"))

    scan = _cleanup_scan_for_driver(driver_id)
    return render_template(
        "drivers/cleanup.html",
        driver=d,
        scan=scan,
        page="drivers"
    )


@bp.post("/<int:driver_id>/cleanup/delete", endpoint="cleanup_delete")
def drivers_cleanup_delete(driver_id: int):
    """
    Приема checkbox списък 'sel[]' с uid стойности:
      - log:<order_id>:<YYYY-MM-DD>
      - tok:<token>
      - tel:<order_id>:<YYYY-MM-DD>:<created_at>
    Изтрива съответните записи и показва резултат.
    """
    selected = request.form.getlist("sel[]") or []
    if not selected:
        flash("Няма избрани записи за изтриване.", "info")
        return redirect(url_for("drivers.cleanup", driver_id=driver_id))

    # зареди всички сторове
    logs_store   = _load_json(LOGS_FILE,   {"logs": []})
    tokens_store = _load_json(TOKENS_FILE, {"tokens": []})
    try:
        telemetry = _load_json(TELEMETRY_FILE, [])
        if not isinstance(telemetry, list):
            telemetry = []
    except Exception:
        telemetry = []

    del_logs = del_tokens = del_tel = 0

    # подготви множества за бързо тестване
    want_logs = set()
    want_tokens = set()
    want_tel = set()
    for uid in selected:
        if uid.startswith("log:"):
            # log:<oid>:<date>
            parts = uid.split(":")
            if len(parts) == 3:
                want_logs.add((parts[1], parts[2]))
        elif uid.startswith("tok:"):
            # tok:<token>
            token = uid[4:]
            if token:
                want_tokens.add(token)
        elif uid.startswith("tel:"):
            # tel:<oid>:<date>:<created_at>
            parts = uid.split(":")
            if len(parts) >= 4:
                # някои записи може да нямат created_at → ползваме празно
                created = ":".join(parts[3:])  # пази двоеточия, ако има
                want_tel.add((parts[1], parts[2], created))

    # филтрирай
    before = len(logs_store.get("logs", []))
    logs_store["logs"] = [
        L for L in (logs_store.get("logs", []) or [])
        if not (
            str(L.get("driver_id")) == str(driver_id)
            and (str(L.get("order_id")), str(L.get("date") or "")) in want_logs
        )
    ]
    after = len(logs_store.get("logs", []))
    del_logs = before - after
    _save_json(LOGS_FILE, logs_store)

    before = len(tokens_store.get("tokens", []))
    tokens_store["tokens"] = [
        t for t in (tokens_store.get("tokens", []) or [])
        if not (
            str(t.get("driver_id")) == str(driver_id)
            and str(t.get("token")) in want_tokens
        )
    ]
    after = len(tokens_store.get("tokens", []))
    del_tokens = before - after
    _save_json(TOKENS_FILE, tokens_store)

    before = len(telemetry)
    telemetry = [
        x for x in telemetry
        if not (
            str(x.get("driver_id")) == str(driver_id)
            and (str(x.get("order_id")), str(x.get("date") or ""), str(x.get("created_at") or "")) in want_tel
        )
    ]
    after = len(telemetry)
    del_tel = before - after
    try:
        _save_telemetry(telemetry)
    except Exception:
        # ако няма телеметрия файл или не може да се запише — игнор
        del_tel = 0

    flash(
        f"Изтрито: {del_logs} дневн., {del_tokens} токена"
        + (f", {del_tel} телеметрии" if del_tel else ""),
        "success"
    )
    return redirect(url_for("drivers.cleanup", driver_id=driver_id))

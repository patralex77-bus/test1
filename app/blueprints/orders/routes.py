# -*- coding: utf-8 -*-
from flask import (
    render_template,
    jsonify,
    request,
    redirect,
    url_for,
    Blueprint,
    flash,
    Flask,
    send_from_directory,
    make_response,
)
from pathlib import Path
from werkzeug.utils import secure_filename
import json
import datetime
import os
import time
from html import escape as html_escape
from app.blueprints.buses import fetch_buses_list
from app.blueprints.drivers.routes import TOKENS_FILE, _save_json, _load_json
from openai import OpenAI, RateLimitError  

# Само ЕДНА дефиниция на blueprint-а тук.
bp = Blueprint("orders", __name__, url_prefix="/orders", template_folder="templates")

client = OpenAI(api_key="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")


# лимити за заетост
MONTH_MAX_DAYS = 132
WEEK_MAX_DAYS = 30

# Пътища към файлове с данни
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
ORDERS_FILE = DATA_DIR / "orders.json"
BUSES_FILE = DATA_DIR / "buses.json"
DRIVERS_FILE = DATA_DIR / "drivers.json"  # за поповъра „Назначи на шофьор“
TOKENS_FILE = DATA_DIR / "driver_tokens.json"  # използва се за порталните токени

# „Кабинет“ (MVP) – централен store + файлове под data/order_files/<id>/
CABINET_STORE_FILE = DATA_DIR / "orders_cabinet.json"
ORDER_FILES_DIR = DATA_DIR / "order_files"

# Страни: основен файл (settings.json) + fallback (countries.json)
COUNTRIES_FILE_MAIN = DATA_DIR / "settings.json"
COUNTRIES_FILE_FALLBACK = DATA_DIR / "countries.json"

# Заплати: основен файл settings_payroll.json; възможен fallback от settings.json["payroll"]
PAYROLL_FILE = DATA_DIR / "settings_payroll.json"


# ------------------ storage helpers ------------------
def _load_json_safe(path: Path, default):
    """Чете JSON файл; ако липсва — създава го с подадения default.
       Ако е повреден — презаписва с default за да не чупи страниците."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        data = json.loads(path.read_text(encoding="utf-8"))
    # Гарантирай default статус „Планирана“ при липса само за orders.json
    if path == ORDERS_FILE and isinstance(data, dict):
        for o in data.get("orders", []) or []:
            if not o.get("status"):
                o["status"] = "Планирана"
    return data


def _save_json_safe(path: Path, data):
    """Записва JSON; подсигурява статус за всяка поръчка (само за orders.json)."""
    if path == ORDERS_FILE and isinstance(data, dict):
        for o in data.get("orders", []) or []:
            if not o.get("status"):
                o["status"] = "Планирана"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# Оставяме съвместимост с импортите от drivers.routes
def _load_json(path: Path, default):
    return _load_json_safe(path, default)


def _save_json(path: Path, data):
    return _save_json_safe(path, data)


def _ymd(d: datetime.date) -> str:
    return d.strftime("%Y-%m-%d")


def _daterange(s: datetime.date, e: datetime.date):
    one = datetime.timedelta(days=1)
    d = s
    while d <= e:
        yield d
        d += one


def _parse_iso_date(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _load_countries():
    """
    Чете страните от settings.json (ако го има),
    иначе ползва fallback към countries.json.
    Връща list от обекти: { name, fee_per_km, fuel_price, vat_percent, ... }
    """
    if COUNTRIES_FILE_MAIN.exists():
        data = _load_json(COUNTRIES_FILE_MAIN, {"countries": []})
        return data.get("countries", [])
    if COUNTRIES_FILE_FALLBACK.exists():
        data = _load_json(COUNTRIES_FILE_FALLBACK, {"countries": []})
        return data.get("countries", [])
    return []


# ---------- ПЛАЩАНИЯ / ЗАПЛАТИ ----------
def _load_payroll_raw():
    """
    Връща оригиналните настройки за заплати от settings_payroll.json,
    или fallback от settings.json -> ключ 'payroll'.
    """
    if PAYROLL_FILE.exists():
        return _load_json(PAYROLL_FILE, {})
    # fallback от settings.json
    if COUNTRIES_FILE_MAIN.exists():
        s = _load_json(COUNTRIES_FILE_MAIN, {})
        if isinstance(s, dict) and isinstance(s.get("payroll"), dict):
            return s["payroll"]
    return {}


def _payroll_front_payload():
    """
    Конвертира наличните ключове към тези, които фронтът очаква:
      - daily_rate
      - hourly_factor
    Поддържа следните възможни източници:
      settings_payroll.json:    daily_fixed, hourly_contract, hourly_custom
      settings.json["payroll"]: daily_fixed, hourly_contract, hourly_custom
    Приоритет за часова ставка: hourly_contract (ако липсва -> hourly_custom)
    """
    raw = _load_payroll_raw() or {}
    # опитай да „разбереш“ ключовете
    daily_rate = raw.get("daily_rate")
    if daily_rate is None:
        daily_rate = raw.get("daily_fixed")
    if daily_rate is None:
        daily_rate = raw.get("daily")  # най-краен fallback
    try:
        daily_rate = float(str(daily_rate).replace(",", ".")) if daily_rate is not None else 0.0
    except Exception:
        daily_rate = 0.0

    hourly = raw.get("hourly_factor")
    if hourly is None:
        hourly = raw.get("hourly_contract", raw.get("hourly_custom"))
    if hourly is None:
        hourly = raw.get("hourly")
    try:
        hourly = float(str(hourly).replace(",", ".")) if hourly is not None else 0.0
    except Exception:
        hourly = 0.0

    return {
        "daily_rate": daily_rate or 0.0,
        "hourly_factor": hourly or 0.0,
    }


@bp.get("/api/payroll")
def api_orders_payroll():
    """
    JSON API за фронта: /orders/api/payroll
    Връща {"daily_rate": <float>, "hourly_factor": <float>}
    """
    return jsonify(_payroll_front_payload())


def _norm_plate(s):
    return (str(s or "").strip().upper())


def _bus_index():
    """
    Връща речник по рег. номер (нормализиран) -> bus обект.
    """
    try:
        buses = fetch_buses_list()
    except Exception:
        buses = []
    out = {}
    for b in (buses or []):
        plate = _norm_plate(b.get("reg_no") or b.get("reg") or b.get("plate") or b.get("number"))
        if plate:
            out[plate] = b
    return out


def _bus_consumption_l100(bus_obj, default=28.0):
    """
    Опитва се да прочете консумацията (l/100km) от различни възможни ключове.
    """
    if not isinstance(bus_obj, dict):
        return float(default)
    candidates = [
        "consumption_l_100", "consumption_l100", "consumption100",
        "avg_consumption", "avg_consumption_l100", "fuel_consumption_l100",
        "consumption"
    ]
    for k in candidates:
        v = bus_obj.get(k)
        try:
            v = float(str(v).replace(",", "."))
            if v > 0:
                return v
        except Exception:
            pass
    return float(default)


def _country_fuel_price(name, default=0.0):
    """
    Взима цена на гориво за държава от settings/countries.
    Очаква `countries[].name` и `countries[].fuel_price`.
    """
    if not name:
        return float(default)
    countries = _load_countries() or []
    for c in countries:
        if str(c.get("name") or "").strip().lower() == str(name).strip().lower():
            try:
                v = float(str(c.get("fuel_price") or "0").replace(",", "."))
                return v if v >= 0 else float(default)
            except Exception:
                break
    return float(default)


def _auto_fill_fuel_costs(order_obj: dict) -> bool:
    """
    Автоматично попълва сегментните `fuel_cost`, ако липсват/са 0.
    Формула: fuel_cost = (km * cons_l100 / 100) * fuel_price(country)
    Връща True, ако е направена промяна.
    """
    if not isinstance(order_obj, dict):
        return False

    segments = order_obj.get("segments") or []
    if not segments:
        return False

    # индекс по табела → автобус
    bus_plate = _norm_plate(order_obj.get("vehicle_plate") or order_obj.get("bus_plate"))
    buses_by_plate = _bus_index()
    bus = buses_by_plate.get(bus_plate, {})
    cons_l100 = _bus_consumption_l100(bus, default=28.0)

    changed = False
    for s in segments:
        # ако вече има въведена стойност > 0 — не я пипаме
        try:
            fc = float(str(s.get("fuel_cost") or "0").replace(",", "."))
        except Exception:
            fc = 0.0
        if fc and fc > 0:
            continue

        # нужни са km и country
        km_raw = s.get("km") or s.get("kms") or "0"
        try:
            kms = float(str(km_raw).replace(",", "."))
        except Exception:
            kms = 0.0
        country = s.get("country") or ""
        if kms <= 0:
            continue

        price = _country_fuel_price(country, default=0.0)
        liters = kms * cons_l100 / 100.0
        fuel_cost = round(liters * price, 2)

        # попълваме само ако има смисъл (price може да е 0 → тогава оставяме 0.00)
        s["fuel_cost"] = f"{fuel_cost:.2f}"
        changed = True

    return changed


def _bus_plates_from_buses_json(active_only=True):
    """
    Чете списъка автобуси през buses.fetch_buses_list() => само от buses.json.
    Връща сортиран списък с уникални рег. номера. По подразбиране – само активни.
    """
    try:
        buses = fetch_buses_list()  # идва от app.blueprints.buses
    except Exception:
        buses = []

    if active_only:
        buses = [b for b in buses if not b.get("inactive")]

    plates = []
    for b in buses:
        p = (b.get("reg_no") or b.get("reg") or b.get("plate") or "").strip()
        if p:
            plates.append(p)

    # уникални + case-insensitive сортировка
    return sorted(dict.fromkeys(plates), key=lambda x: x.lower())


def _find_order(store: dict, oid) -> dict | None:
    """Намира поръчка по id (стринг/инт)."""
    sid = str(oid)
    for o in store.get("orders", []) or []:
        if str(o.get("id")) == sid:
            return o
    return None


def _get_order(store: dict, oid) -> dict | None:
    sid = str(oid)
    for o in store.get("orders", []) or []:
        if str(o.get("id")) == sid:
            return o
    return None


# ------------------ числови/финансови помощници ------------------
def _fnum(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _days_inclusive(sd, ed):
    s = _parse_iso_date(sd)
    e = _parse_iso_date(ed) or s
    if not s:
        return 0
    return max(1, (e - s).days + 1)


def _personnel_total_from_staff_payload(o: dict):
    """
    НОВО: ако има staff_payload (JSON/dict) със 'total', върни го като персонален разход.
    Поддържа формати:
      {"mode":"daily","daily_rate":..,"days":..,"total":..}
      {"mode":"hourly","hourly_factor":..,"items":[...],"total_hours":..,"total":..}
    """
    payload = o.get("staff_payload")
    if not payload:
        # възможно е да е сериализирано като string
        try:
            payload = json.loads(o.get("staff_payload_json", "") or "{}")
        except Exception:
            payload = None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload or "{}")
        except Exception:
            payload = None
    if isinstance(payload, dict):
        t = payload.get("total")
        try:
            t = float(str(t).replace(",", ".")) if t is not None else None
        except Exception:
            t = None
        if t is not None and t >= 0:
            return round(t, 2)
    return None


def _direct_costs_from_struct(o):
    """
    Директни разходи:
      - гориво: sum(seg.fuel_cost)
      - пътни такси (firm)
      - extras (firm)
      - персонал:
          * ако има staff_payload.total -> вземи него
          * иначе back-compat:
              - daily: daily_rate * дни
              - hourly: hourly_rate * hours_per_day * дни
              - + second driver (daily_rate2 * days_second)
    """
    segs = o.get("segments") or []
    fuel_sum = 0.0
    toll_firm = 0.0
    for s in segs:
        fuel_sum += _fnum(s.get("fuel_cost"))
        scope = (s.get("scope") or "firm").strip().lower()
        if scope != "neutral":
            toll_firm += _fnum(s.get("toll_cost"))

    extras = o.get("extras") or []
    extra_firm = 0.0
    for ex in extras:
        scope = (ex.get("scope") or "firm").strip().lower()
        if scope != "neutral":
            extra_firm += _fnum(ex.get("amount"))

    # Персонал от новия payload (ако има)
    personnel_from_payload = _personnel_total_from_staff_payload(o)

    if personnel_from_payload is not None:
        personnel_total = personnel_from_payload
        mode = (o.get("staff_mode") or o.get("personnel_mode") or "daily").strip().lower()
        planned_hours_total = None
        hours_per_day = None
    else:
        # Back-compat
        mode = (o.get("personnel_mode") or "daily").strip().lower()
        sd, ed = o.get("start_date"), (o.get("end_date") or o.get("start_date"))
        d = _days_inclusive(sd, ed)
        if mode == "hourly":
            hourly_rate = _fnum(o.get("hourly_rate"))
            hours_per_day = _fnum(o.get("hours_per_day"))
            p1 = hourly_rate * hours_per_day * d
            planned_hours_total = hours_per_day * d
        else:
            daily_rate = _fnum(o.get("daily_rate"))
            p1 = daily_rate * d
            hours_per_day = None
            planned_hours_total = None

        second_driver = bool(o.get("second_driver"))
        p2 = 0.0
        if second_driver:
            daily_rate2 = _fnum(o.get("daily_rate2"))
            days_second = _fnum(o.get("days_second"))
            p2 = daily_rate2 * days_second
        personnel_total = p1 + p2

    total_direct = fuel_sum + toll_firm + extra_firm + personnel_total
    # За „work_plan“ в snapshot:
    sd, ed = o.get("start_date"), (o.get("end_date") or o.get("start_date"))
    d = _days_inclusive(sd, ed)
    return {
        "total_direct": round(total_direct, 2),
        "fuel_sum": round(fuel_sum, 2),
        "toll_firm": round(toll_firm, 2),
        "extra_firm": round(extra_firm, 2),
        "personnel_total": round(personnel_total, 2),
        "personnel_mode": (o.get("staff_mode") or o.get("personnel_mode") or "daily"),
        "planned_days": d,
        "hours_per_day": None,              # не е приложимо при новия payload
        "planned_hours_total": None,        # не е приложимо при новия payload
        "second_driver": bool(o.get("second_driver")),
        "second_driver_days": _fnum(o.get("days_second")) if o.get("second_driver") else 0.0,
    }


# ---------- helpers: „кабинет“ (централен store + order_files/<id>) ----------
def _cabinet_now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _cabinet_load() -> dict:
    return _load_json(CABINET_STORE_FILE, {"orders": {}})


def _cabinet_save(store: dict):
    _save_json(CABINET_STORE_FILE, store)


def _cabinet_get_order(store: dict, oid: int) -> dict:
    s = store.setdefault("orders", {})
    key = str(int(oid))
    o = s.get(key)
    if not o:
        o = {"tasks": [], "files": [], "log": []}
        s[key] = o
    return o


def _ensure_files_dir(oid: int) -> Path:
    p = ORDER_FILES_DIR / str(int(oid))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _filename_unique(base: Path, filename: str) -> str:
    """Връща безопасно име; ако съществува — добавя _нумерация."""
    safe = secure_filename(filename) or f"file_{int(time.time())}"
    stem = Path(safe).stem
    ext = Path(safe).suffix
    cand = safe
    i = 1
    while (base / cand).exists():
        cand = f"{stem}_{i}{ext}"
        i += 1
    return cand


def _task_id(tasks: list) -> int:
    """Прост инкрементален id за задачи."""
    max_id = 0
    for t in tasks:
        try:
            max_id = max(max_id, int(t.get("id") or 0))
        except Exception:
            pass
    return max_id + 1


def _build_cabinet_snapshot(oid: int):
    """Единна функция за snapshot: ползват я /api/cabinet/snapshot и алиасите."""
    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    order = _get_order(orders_store, oid)
    if not order:
        return None

    # Финансови изчисления
    price = _fnum(order.get("price"))
    costs = _direct_costs_from_struct(order)
    gross = round(price - costs["total_direct"], 2)
    margin = round((gross / price * 100.0), 2) if price > 0 else 0.0

    # Бюджети и етикети
    budget1 = order.get("budget1_tag_date") or ""
    budget2 = order.get("budget2_tag_date") or ""
    round_trip = bool(order.get("round_trip"))

    # Основни полета
    title = order.get("title") or f"Поръчка #{oid}"
    sd = order.get("start_date") or order.get("date") or ""
    ed = order.get("end_date") or sd or ""
    bus = order.get("vehicle_plate") or order.get("bus_plate") or ""
    status = order.get("status") or "Планирана"
    driver_name = order.get("driver_name") or ""
    driver_assigned = bool(order.get("driver_id"))
    pax = order.get("pax") or order.get("passengers") or order.get("pax_count") or None

    # Кабинет данни
    cab_store = _cabinet_load()
    cab = _cabinet_get_order(cab_store, oid)

    return {
        "ok": True,
        "order_id": oid,
        "summary": {
            "title": title,
            "start_date": sd,
            "end_date": ed,
            "bus_plate": bus,
            "status": status,
            "driver_name": driver_name,
            "driver_assigned": driver_assigned,
            "pax": pax,
            # Бюджети / флагове
            "budget1_tag_date": budget1,
            "budget2_tag_date": budget2,
            "round_trip": round_trip,
            # Финанси
            "price": round(price, 2),
            "direct_costs": costs["total_direct"],
            "gross_profit": gross,
            "margin_pct": margin,
            "costs_breakdown": {
                "fuel_sum": costs["fuel_sum"],
                "toll_firm": costs["toll_firm"],
                "extras_firm": costs["extra_firm"],
                "personnel_total": costs["personnel_total"],
            },
            # Работно време / план (информационно)
            "work_plan": {
                "mode": costs["personnel_mode"],              # daily / hourly (или избрания staff_mode)
                "days": costs["planned_days"],
                "hours_per_day": costs["hours_per_day"],
                "planned_hours_total": costs["planned_hours_total"],
                "second_driver": costs["second_driver"],
                "second_driver_days": costs["second_driver_days"],
            },
        },
        "tasks": cab.get("tasks", []),
        "files": cab.get("files", []),
        "log": cab.get("log", []),
    }


# ======= CABINET ID HELPERS (за ID на файлове/задачи) =======
def _cabinet_next_id(items: list, key: str = "id") -> int:
    mx = 0
    for it in items or []:
        try:
            mx = max(mx, int(it.get(key) or 0))
        except Exception:
            pass
    return mx + 1


def _cabinet_ensure_file_ids(cab: dict) -> bool:
    """Ако файловете нямат 'id', добавя ги и връща True (за да запишем store)."""
    changed = False
    for f in cab.get("files", []):
        if "id" not in f:
            f["id"] = int(time.time() * 1000) % 1_000_000 + _cabinet_next_id(cab.get("files", []))
            changed = True
    return changed


def _cabinet_ensure_task_ids(cab: dict) -> bool:
    changed = False
    for t in cab.get("tasks", []):
        if "id" not in t:
            t["id"] = _cabinet_next_id(cab.get("tasks", []))
            changed = True
    return changed


# ------------------ app factory (по желание) ------------------
def create_app():
    """
    Минимална фабрика на приложението, която регистрира ТОЗИ blueprint.
    Началната страница редиректва към /orders/entry.
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "change-me"

    app.register_blueprint(bp)  # url_prefix се взима от bp.url_prefix -> "/orders"

    @app.get("/")
    def _root():
        return redirect(url_for("orders.entry"))

    return app


# ------------------ views ------------------
@bp.get("/", endpoint="index")
def index():
    """Главен екран: рендерира orders/empty.html."""
    return render_template("orders/empty.html", page="orders")


# --------- помощници за PAX/капацитет ---------
def _parse_int(v, default=None):
    try:
        iv = int(str(v).strip())
        return iv if iv >= 0 else default
    except Exception:
        return default


def _bus_capacity_from_obj(bus_obj) -> int | None:
    """
    Извлича капацитет (бр. места) от bus обект, покривайки различни схеми:
    seats, capacity, seat_count, seats_count, places, max_pax, max_seats
    """
    if not isinstance(bus_obj, dict):
        return None
    for attr in ("seats", "capacity", "seat_count", "seats_count", "places", "max_pax", "max_seats"):
        if attr in bus_obj:
            try:
                iv = int(str(bus_obj.get(attr)))
                if iv > 0:
                    return iv
            except Exception:
                continue
    return None


def _bus_capacity_for_plate(plate: str) -> int | None:
    if not plate:
        return None
    plate_norm = _norm_plate(plate)
    buses = {}
    try:
        buses = _bus_index()
    except Exception:
        pass
    bus = buses.get(plate_norm)
    return _bus_capacity_from_obj(bus)


@bp.route("/entry", methods=["GET", "POST"], endpoint="entry")
def orders_entry():
    """
    GET:
      - без параметри: празна форма (нова поръчка)
      - ?edit=<id>: зарежда поръчка за редакция, сетва is_edit=True
    POST:
      - ако има hidden id -> redirect към UPDATE (307, запазва POST)
      - иначе -> redirect към CREATE (307)
    """
    if request.method == "POST":
        oid = (request.form.get("id") or "").strip()
        if oid:
            return redirect(url_for("orders.update", order_id=oid), code=307)
        return redirect(url_for("orders.create"), code=307)

    # GET (покажи форма)
    edit_id = (request.args.get("edit") or "").strip()
    order_obj = None
    is_edit = False
    if edit_id:
        store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
        order_obj = _find_order(store, edit_id)
        is_edit = order_obj is not None

        # --- АВТОПОПЪЛВАНЕ на липсващи fuel_cost според избрания автобус ---
        if is_edit and order_obj:
            if _auto_fill_fuel_costs(order_obj):
                # Ъпдейтни на място store, за да се визуализира във формата
                _save_json(ORDERS_FILE, store)

    # променливи за шаблона
    heading = f"Редактиране на поръчка #{order_obj.get('id')}" if is_edit else "Нова поръчка"
    submit_label = "Запази промените" if is_edit else "Създай поръчка"

    # action URL за формата
    form_action = url_for("orders.update", order_id=order_obj.get("id")) if is_edit else url_for("orders.create")

    # Данни за селектите
    bus_plates = _bus_plates_from_buses_json(active_only=True)
    countries = _load_countries()
    try:
        buses_all = fetch_buses_list()  # съдържа reg_no/plate + consumption_l100 или еквивалент
    except Exception:
        buses_all = []

    # НОВО: подай payroll към фронта (и като контекст, и като JSON API вече има /orders/api/payroll)
    payroll = _payroll_front_payload()

    return render_template(
        "orders/entry.html",
        order=order_obj,
        is_edit=is_edit,
        heading=heading,
        submit_label=submit_label,
        form_action=form_action,
        bus_plates=bus_plates,
        countries=countries,
        buses_all=buses_all,
        payroll=payroll,  # <-- за директно вкарване (ако фронтът реши да го ползва)
    )


@bp.route("/list", methods=["GET"], endpoint="list")
def orders_list():
    """
    Рендерира списъка с поръчки:
      - разделя на текущи и архивни
      - добавя gross_profit и margin_pct
      - подава drivers_all за поповъра „Назначи на шофьор“
      - изчислява МЕСЕЧНА ЗАЕТОСТ върху ВСИЧКИ поръчки (текущи + архив)
    """
    store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    rows = store.get("orders") or []

    today = datetime.date.today()

    # посока на сортиране: по подразбиране от по-стара към по-нова (asc)
    sort_dir = (request.args.get("dir") or "asc").lower()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"
    reverse_flag = (sort_dir == "desc")

    current, archived = [], []

    # --- основни метрики за всяка поръчка (цена, марж) ---
    for o in rows:
        price = _fnum(o.get("price"))
        c = _direct_costs_from_struct(o)
        gross = price - c["total_direct"]
        margin = (gross / price * 100.0) if price > 0 else 0.0

        row = dict(o)
        row["gross_profit"] = round(gross, 2)
        row["margin_pct"] = round(margin, 2)

        end = _parse_iso_date(row.get("end_date") or row.get("start_date"))
        (current if (end is None or end >= today) else archived).append(row)

    # --- стабилно сортиране по дата + id ---
    def _safe_iso_date(val):
        if not val:
            return datetime.date.min
        try:
            return datetime.date.fromisoformat(str(val)[:10])
        except Exception:
            return datetime.date.min

    def _int_id(x):
        try:
            return int(str(x).strip())
        except Exception:
            return 0

    def sort_key(x):
        d = _safe_iso_date(x.get("start_date") or x.get("date"))
        return (d, _int_id(x.get("id")))

    current = sorted(current, key=sort_key, reverse=reverse_flag)
    archived = sorted(archived, key=sort_key, reverse=reverse_flag)

    # ---- Подай списък шофьори (за поповъра) + име към редовете (бейдж) ----
    drivers_store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})
    drivers_all = drivers_store.get("drivers", []) or []
    drivers_all = sorted(
        drivers_all,
        key=lambda d: (
            str(d.get("last_name") or "").lower(),
            str(d.get("first_name") or "").lower(),
            int(d.get("id") or 0),
        ),
    )

    def _driver_label(d):
        fn = (d.get("first_name") or "").strip()
        ln = (d.get("last_name") or "").strip()
        full = (ln + " " + fn).strip()
        return full or f"Шофьор #{d.get('id')}"

    drivers_by_id = {
        int(d.get("id")): _driver_label(d)
        for d in (drivers_store.get("drivers") or [])
        if d.get("id") is not None
    }

    for row in current:
        did = row.get("driver_id")
        try:
            did = int(did) if did is not None else None
        except Exception:
            did = None
        row["driver_name"] = drivers_by_id.get(did, "") if did is not None else ""

    for row in archived:
        did = row.get("driver_id")
        try:
            did = int(did) if did is not None else None
        except Exception:
            did = None
        row["driver_name"] = drivers_by_id.get(did, "") if did is not None else ""

    # =====================================================
    # МЕСЕЧНА ЗАЕТОСТ – върху ВСИЧКИ поръчки (current+archived)
    # =====================================================
    all_for_stats = current + archived

    month_orders = {}   # key -> set(order_id) : за "Общо поръчки"
    month_days = {}     # key -> set(date)     : за "заети дни"
    month_weeks = {}    # key -> { week_idx -> set(date) }

    for o in all_for_stats:
        oid = o.get("id")
        sd_str = o.get("start_date") or o.get("date")
        ed_str = o.get("end_date") or sd_str

        sd = _parse_iso_date(sd_str)
        ed = _parse_iso_date(ed_str) or sd
        if not sd:
            continue

        for d in _daterange(sd, ed):
            month_key = f"{d.year:04d}-{d.month:02d}"

            # поръчки за месеца (всяка поръчка се брои веднъж на месец, ако има поне един ден там)
            month_orders.setdefault(month_key, set()).add(oid)

            # заети дни в месеца
            month_days.setdefault(month_key, set()).add(d)

            # по седмици в рамките на месеца (седмица 1 = дни 1–7, 2 = 8–14, ...)
            week_idx = ((d.day - 1) // 7) + 1
            month_weeks.setdefault(month_key, {}).setdefault(week_idx, set()).add(d)

    # Списък с месеци за избиране в UI (календар + чипове)
    months = []
    for key in sorted(month_orders.keys()):
        # key = "YYYY-MM"
        if len(key) == 7 and key[4] == "-":
            label = f"{key[5:7]}.{key[0:4]}"
        else:
            label = key
        months.append({"key": key, "label": label})

    # избран месец: от query ?month=YYYY-MM, иначе текущия месец, иначе последния наличен
    q_month = (request.args.get("month") or "").strip()
    today_key = f"{today.year:04d}-{today.month:02d}"

    if q_month and q_month in month_orders:
        current_month_key = q_month
    elif today_key in month_orders:
        current_month_key = today_key
    else:
        current_month_key = months[-1]["key"] if months else None

    current_month_stats = None
    if current_month_key and current_month_key in month_orders:
        orders_set = month_orders[current_month_key]
        days_set = month_days.get(current_month_key, set())
        total_orders = len(orders_set)
        busy_days = len(days_set)

        # според твоето изискване: макс. 132 "дена" за месец
        month_max_days = 132
        month_occupancy = (busy_days / month_max_days * 100.0) if month_max_days > 0 else 0.0

        # седмици
        weeks_raw = month_weeks.get(current_month_key, {})
        weeks_list = []
        for week_idx in sorted(weeks_raw.keys()):
            w_days = len(weeks_raw[week_idx])
            # според изискването: макс. 30 "дена" за седмица
            max_days_week = 30
            occ = (w_days / max_days_week * 100.0) if max_days_week > 0 else 0.0
            weeks_list.append({
                "index": week_idx,
                "label": f"Седмица {week_idx}",
                "busy_days": w_days,
                "max_days": max_days_week,
                "occupancy": occ,
            })

        current_month_stats = {
            "month_key": current_month_key,
            "total_orders": total_orders,
            "busy_days": busy_days,
            "month_max_days": month_max_days,
            "month_occupancy": month_occupancy,
            "weeks": weeks_list,
        }

    return render_template(
        "orders/list.html",
        current_orders=current,
        archived_orders=archived,
        drivers_all=drivers_all,
        # за календар / статистика в горния панел
        months=months,
        current_month_key=current_month_key,
        current_month_stats=current_month_stats,
        sort_dir=sort_dir,
    )

def _parse_json_from_content(content_raw: str):
    """
    Чисти ```json ... ``` обвивки и парсва до Python dict.
    Вдига JSONDecodeError ако не успее.
    """
    content = (content_raw or "").strip()

    if content.startswith("```"):
        first_newline = content.find("\n")
        if first_newline != -1:
            content = content[first_newline + 1 :]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    return json.loads(content)


@bp.route("/ai-fill", methods=["POST"])
def ai_fill():
    data = request.get_json() or {}
    raw_text = (data.get("text") or "").strip()

    if not raw_text:
        return jsonify({"error": "no_text", "message": "No text provided"}), 400

    # --- 1. Основен (строг) prompt ---
    strict_system_prompt = """
Ти си помощник за диспечер на автобусни поръчки.
От свободен текст трябва да извадиш структурирани данни за поръчката.

Върни САМО валиден JSON (без обяснения, без ```json, без ```), с ключове:
- title: кратко заглавие на поръчката
- description: кратко описание (ако има)
- program: по-подробна програма/маршрут
- pax: брой пътници (цяло число)
- price: сума в евро (число), ако има
- date_from: YYYY-MM-DD
- date_to: YYYY-MM-DD
- start_time: HH:MM (24 часа)
- end_time: HH:MM (24 часа)
- bus_plate: рег. номер на автобуса, ако го има (иначе null)

Ако нещо липсва, сложи null.
"""

    user_prompt = f"Текст на поръчка:\n```{raw_text}```"

    try:
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": strict_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
        content_raw = completion.choices[0].message.content or ""
        try:
            structured = _parse_json_from_content(content_raw)
        except json.JSONDecodeError:
            # ---- 2. Fallback prompt – само основни полета ----
            print("Strict JSON parse failed, trying fallback extraction...")
            fallback_system_prompt = """
Извлечи САМО основни полета за поръчка от свободния текст и върни чист JSON (без ```):

- date_from: YYYY-MM-DD (ако няма – null)
- date_to: YYYY-MM-DD (ако няма – същата като date_from или null)
- start_time: HH:MM (24 часа) ако има, иначе null
- end_time: HH:MM (24 часа) ако има, иначе null
- pax: цяло число ако има, иначе null

Всички останали полета (title, description, program, price, bus_plate) сложи null.
"""

            fb = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": fallback_system_prompt},
                    {"role": "user", "content": raw_text},
                ],
                temperature=0.1,
            )
            fb_raw = fb.choices[0].message.content or ""
            structured = _parse_json_from_content(fb_raw)

    except RateLimitError as e:
        print("OpenAI quota error:", repr(e))
        return jsonify({
            "error": "quota",
            "message": "Няма наличен кредит за ИИ (insufficient_quota)."
        }), 429
    except Exception as e:
        print("OpenAI call failed:", repr(e))
        return jsonify({
            "error": "backend",
            "message": "Възникна грешка при връзката с ИИ."
        }), 500

    # --- 3. Генерираме warnings за липсващи ключови полета ---
    warnings = []

    def is_empty(v):
        return v is None or (isinstance(v, str) and not v.strip())

    # Ключови полета, които са важни за поръчката
    critical_fields = {
        "date_from": "Начална дата",
        "start_time": "Начален час",
        "pax": "Брой пътници (PAX)"
    }

    for key, label in critical_fields.items():
        if is_empty(structured.get(key)):
            warnings.append(f"Липсва поле: {label}")

    if is_empty(structured.get("date_to")):
        warnings.append("Не е разпозната крайна дата (date_to).")

    if is_empty(structured.get("price")):
        warnings.append("Не е разпозната цена (price).")

    if is_empty(structured.get("bus_plate")):
        warnings.append("Не е разпознат автобус (регистрационен номер).")

    result = {
        "title":       structured.get("title"),
        "description": structured.get("description"),
        "program":     structured.get("program"),
        "pax":         structured.get("pax"),
        "price":       structured.get("price"),
        "date_from":   structured.get("date_from"),
        "date_to":     structured.get("date_to"),
        "start_time":  structured.get("start_time"),
        "end_time":    structured.get("end_time"),
        "bus_plate":   structured.get("bus_plate"),
        "warnings":    warnings,
    }

    return jsonify(result)

# ------------------ CREATE / UPDATE ------------------
@bp.post("/create", endpoint="create")
def create():
    """
    Приема формата от /orders/entry.
    Ако има 'id' -> UPDATE (upsert), иначе INSERT.
    Поддържа и query ?force_id=<id> (използва се от /<id>/update).
    """
    form = request.form

    # общи полета
    oid_form = (form.get("id") or "").strip()
    if not oid_form:
        q_force = (request.args.get("force_id") or "").strip()
        if q_force:
            oid_form = q_force

    title = form.get("title", "")
    bus_plate = form.get("bus_plate", "")
    start_date = form.get("start_date", "")
    start_time = form.get("start_time", "")
    end_date = form.get("end_date", "")
    end_time = form.get("end_time", "")
    price = form.get("price", "0")
    program = form.get("program", "")
    special_needs = form.get("special_needs", "")
    client_requirements = form.get("client_requirements", "")

    # НОВО: PAX
    pax = _parse_int(form.get("pax"), default=None)

    # режими и флагове
    personnel_mode = form.get("personnel_mode", "daily")  # legacy поле
    second_driver = True if (form.get("second_driver") in ("1", "true", "True", "on")) else False
    round_trip = True if (form.get("round_trip") in ("1", "true", "True", "on")) else False

    # НОВО: Персонал (съвременния модул)
    staff_mode = (form.get("staff_mode") or "").strip() or personnel_mode
    staff_payload_json = (form.get("staff_payload_json") or "").strip()

    # legacy полета (back-compat; може да не се ползват от новия модул)
    daily_rate = form.get("daily_rate", "")
    hourly_rate = form.get("hourly_rate", "")
    hours_per_day = form.get("hours_per_day", "")
    daily_rate2 = form.get("daily_rate2", "")
    days_second = form.get("days_second", "")

    # бюджетни тагове
    budget1_tag_date = form.get("budget1_tag_date", "")
    budget2_tag_date = form.get("budget2_tag_date", "")

    # сегменти
    seg_country = form.getlist("seg_country[]")
    seg_km = form.getlist("seg_km[]")
    seg_toll = form.getlist("seg_toll_cost[]")
    seg_fuel = form.getlist("seg_fuel_cost[]")
    seg_scope = form.getlist("seg_toll_scope[]")

    # други разходи
    extra_desc = form.getlist("extra_desc[]")
    extra_amt = form.getlist("extra_amount[]")
    extra_scope = form.getlist("extra_scope[]")

    store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})

    # Подготви сегменти (държави/км)
    seg_len = max(len(seg_country), len(seg_km), len(seg_toll), len(seg_fuel), len(seg_scope), 0)
    segments = []
    for i in range(seg_len):
        ctry = seg_country[i] if i < len(seg_country) else ""
        kms = seg_km[i] if i < len(seg_km) else ""
        toll = seg_toll[i] if i < len(seg_toll) else "0"
        fuel = seg_fuel[i] if i < len(seg_fuel) else "0"
        scope_v = seg_scope[i] if i < len(seg_scope) else "firm"
        if not (ctry or kms or toll or fuel):
            continue
        segments.append(
            {
                "country": ctry,
                "km": kms or "0",
                "toll_cost": toll or "0",
                "fuel_cost": fuel or "0",
                "scope": scope_v or "firm",
            }
        )

    # Подготви "други разходи"
    extra_len = max(len(extra_desc), len(extra_amt), len(extra_scope), 0)
    extras = []
    for i in range(extra_len):
        desc = extra_desc[i] if i < len(extra_desc) else ""
        amt = extra_amt[i] if i < len(extra_amt) else ""
        scp = extra_scope[i] if i < len(extra_scope) else "firm"
        if not (desc or amt):
            continue
        extras.append({"desc": desc, "amount": amt or "0", "scope": scp or "firm"})

    # НОВО: парсирай staff_payload_json ако е подадено
    staff_payload = None
    if staff_payload_json:
        try:
            staff_payload = json.loads(staff_payload_json)
        except Exception:
            # ако е невалиден JSON, съхрани суровата стойност за диагностика
            staff_payload = {"_raw": staff_payload_json}

    # ====== Твърда валидация за PAX срещу капацитет ======
    cap = _bus_capacity_for_plate(bus_plate)
    if cap is not None and pax is not None and pax > cap:
        # Подготовка на „order“ обект за повторен рендер на формата с грешка
        try:
            buses_all = fetch_buses_list()
        except Exception:
            buses_all = []
        bus_plates = _bus_plates_from_buses_json(active_only=True)
        countries = _load_countries()
        payroll = _payroll_front_payload()
        flash(f"PAX ({pax}) надвишава капацитета на автобуса ({cap}). Изберете по-голям автобус или намалете PAX.", "error")

        order_obj = {
            "id": oid_form or "",
            "title": title,
            "bus_plate": bus_plate,
            "start_date": start_date,
            "start_time": start_time,
            "end_date": end_date or start_date,
            "end_time": end_time or start_time,
            "price": price,
            "program": program,
            "special_needs": special_needs,
            "client_requirements": client_requirements,
            "segments": segments,
            "extras": extras,
            "status": "Планирана",
            "round_trip": True if round_trip else False,
            "budget1_tag_date": budget1_tag_date,
            "budget2_tag_date": budget2_tag_date,
            "staff_mode": staff_mode,
            "staff_payload": staff_payload,
            "personnel_mode": staff_mode or personnel_mode,
            "second_driver": True if second_driver else False,
            "daily_rate": form.get("daily_rate", ""),
            "hourly_rate": form.get("hourly_rate", ""),
            "hours_per_day": form.get("hours_per_day", ""),
            "daily_rate2": form.get("daily_rate2", ""),
            "days_second": form.get("days_second", ""),
            "pax": pax,
        }
        return render_template(
            "orders/entry.html",
            order=order_obj,
            is_edit=bool(oid_form),
            heading="Редактиране на поръчка" if oid_form else "Нова поръчка",
            submit_label="Запази промените" if oid_form else "Създай поръчка",
            form_action=url_for("orders.update", order_id=oid_form) if oid_form else url_for("orders.create"),
            bus_plates=bus_plates,
            countries=countries,
            buses_all=buses_all,
            payroll=payroll,
        ), 400

    base_fields = {
        "title": title,
        "bus_plate": bus_plate,
        "start_date": start_date,
        "start_time": start_time,
        "end_date": end_date or start_date,
        "end_time": end_time or start_time,
        "price": price,
        "program": program,
        "special_needs": special_needs,
        "client_requirements": client_requirements,
        "segments": segments,
        "extras": extras,
        "status": "Планирана",
        # флагове/таг
        "round_trip": round_trip,
        "budget1_tag_date": budget1_tag_date,
        "budget2_tag_date": budget2_tag_date,
        # Персонал (НОВО)
        "staff_mode": staff_mode,                 # новото поле (за фронта и snapshot)
        "staff_payload": staff_payload,           # тук е тоталът и детайлите за дни/часове
        # Back-compat (оставени за стария код/репорти)
        "personnel_mode": staff_mode or personnel_mode,
        "second_driver": True if second_driver else False,
        "daily_rate": daily_rate,
        "hourly_rate": hourly_rate,
        "hours_per_day": hours_per_day,
        "daily_rate2": daily_rate2,
        "days_second": days_second,
        # НОВО: PAX
        "pax": pax,
    }

    if oid_form:
        # UPDATE (upsert)
        o = _find_order(store, oid_form)
        if o:
            for k, v in base_fields.items():
                o[k] = v
            o["id"] = o.get("id") or int(oid_form)
            flash(f"Поръчка #{o['id']} е обновена.", "success")
        else:
            flash(f"Поръчка #{oid_form} не е намерена – създадена е нова.", "warning")
            oid = store.get("next_id", 1)
            base_fields["id"] = oid
            store.setdefault("orders", []).append(base_fields)
            store["next_id"] = oid + 1
    else:
        # INSERT
        oid = store.get("next_id", 1)
        base_fields["id"] = oid
        store.setdefault("orders", []).append(base_fields)
        store["next_id"] = oid + 1
        flash("Поръчката е записана.", "success")

    _save_json(ORDERS_FILE, store)

    # Връщаме към списъка
    return redirect(url_for("orders.list"))


@bp.post("/<int:order_id>/update", endpoint="update")
def update(order_id: int):
    """
    Ясно отделен UPDATE ендпойнт (POST).
    Ако записът не съществува – създава нов с next_id и предупреждава.
    Логиката за четене на формата е идентична с /create.
    """
    return redirect(url_for("orders.create") + f"?force_id={order_id}", code=307)


# ------------------ DELETE (HTML + API) ------------------
@bp.post("/delete/<int:oid>", endpoint="delete")
def delete_order(oid: int):
    """Изтрива поръчка по ID + чисти всички свързани данни (дневници, токени, телеметрия)."""
    store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    o = _get_order(store, oid)
    if not o:
        flash(f"Поръчка #{oid} не беше намерена.", "warning")
        return redirect(url_for("orders.list"))

    # Първо почисти данните, свързани с поръчката
    did = o.get("driver_id")
    if did:
        from app.blueprints.drivers.routes import _purge_driver_order_data
        try:
            _purge_driver_order_data(int(did), int(oid))
        except Exception:
            # не блокирай изтриването, ако purge се провали
            pass
    else:
        # ако няма driver_id → чистим навсякъде по order_id
        from app.blueprints.drivers.routes import LOGS_FILE, TOKENS_FILE, TELEMETRY_FILE, _load_json as _dl, _save_json as _ds
        logs = _dl(LOGS_FILE, {"logs": []})
        logs["logs"] = [L for L in logs.get("logs", []) if str(L.get("order_id")) != str(oid)]
        _ds(LOGS_FILE, logs)
        tokens = _dl(TOKENS_FILE, {"tokens": []})
        tokens["tokens"] = [t for t in tokens.get("tokens", []) if str(t.get("order_id")) != str(oid)]
        _ds(TOKENS_FILE, tokens)
        try:
            tel = _dl(TELEMETRY_FILE, [])
            if isinstance(tel, list):
                tel = [x for x in tel if str(x.get("order_id")) != str(oid)]
                _ds(TELEMETRY_FILE, tel)
        except Exception:
            pass

    # Накрая – реалното изтриване на поръчката
    before = len(store.get("orders", []))
    store["orders"] = [x for x in store.get("orders", []) if int(x.get("id", -1)) != int(oid)]
    _save_json(ORDERS_FILE, store)
    if len(store.get("orders", [])) < before:
        flash("Поръчката е изтрита и всички свързани данни са премахнати.", "success")
    else:
        flash(f"Поръчка #{oid} не беше намерена.", "warning")
    return redirect(url_for("orders.list"))


@bp.post("/api/delete", endpoint="api_delete")
def api_delete():
    """
    JSON API: {id: <int>} -> трие записа и прави PURGE на свързаните данни (дневници, токени, телеметрия).
    Връща {"ok": true, "deleted": true/false, "purged": {"logs_deleted": N, "tokens_deleted": N, "telemetry_deleted": N}}
    """
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    oid = payload.get("id", None)
    try:
        if oid is not None:
            oid = int(oid)
    except Exception:
        oid = None

    if oid is None:
        return jsonify({"ok": False, "error": "missing or invalid id"}), 400

    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    o = _get_order(orders_store, oid)
    if not o:
        # няма такава поръчка
        return jsonify({"ok": True, "deleted": False, "purged": {"logs_deleted": 0, "tokens_deleted": 0, "telemetry_deleted": 0}})

    purged_stats = {"logs_deleted": 0, "tokens_deleted": 0, "telemetry_deleted": 0}

    did = o.get("driver_id")
    if did:
        # използваме централната функция за purge
        try:
            from app.blueprints.drivers.routes import _purge_driver_order_data
            purged_stats = _purge_driver_order_data(int(did), int(oid)) or purged_stats
        except Exception:
            # ако нещо се счупи, не спирай изтриването
            purged_stats = {"logs_deleted": 0, "tokens_deleted": 0, "telemetry_deleted": 0}
    else:
        # без driver_id → ръчно чистене по order_id
        try:
            from app.blueprints.drivers.routes import LOGS_FILE, TOKENS_FILE, TELEMETRY_FILE, _load_json as _dl, _save_json as _ds
            # logs
            logs = _dl(LOGS_FILE, {"logs": []})
            before_logs = len(logs.get("logs", []))
            logs["logs"] = [L for L in logs.get("logs", []) if str(L.get("order_id")) != str(oid)]
            after_logs = len(logs.get("logs", []))
            _ds(LOGS_FILE, logs)
            purged_stats["logs_deleted"] = before_logs - after_logs
            # tokens
            toks = _dl(TOKENS_FILE, {"tokens": []})
            before_tok = len(toks.get("tokens", []))
            toks["tokens"] = [t for t in toks.get("tokens", []) if str(t.get("order_id")) != str(oid)]
            after_tok = len(toks.get("tokens", []))
            _ds(TOKENS_FILE, toks)
            purged_stats["tokens_deleted"] = before_tok - after_tok
            # telemetry
            try:
                tel = _dl(TELEMETRY_FILE, [])
                if isinstance(tel, list):
                    before_tel = len(tel)
                    tel = [x for x in tel if str(x.get("order_id")) != str(oid)]
                    after_tel = len(tel)
                    _ds(TELEMETRY_FILE, tel)
                    purged_stats["telemetry_deleted"] = before_tel - after_tel
            except Exception:
                pass
        except Exception:
            # ако import-ите фейлнат
            purged_stats = {"logs_deleted": 0, "tokens_deleted": 0, "telemetry_deleted": 0}

    # изтрий самата поръчка
    before = len(orders_store.get("orders", []))
    orders_store["orders"] = [x for x in orders_store.get("orders", []) if int(x.get("id", -1)) != int(oid)]
    after = len(orders_store.get("orders", []))
    deleted = after < before
    if deleted:
        _save_json(ORDERS_FILE, orders_store)

    return jsonify({"ok": True, "deleted": deleted, "purged": purged_stats})


# ------------------ APIs: списъци и календар ------------------
@bp.get("/api/list", endpoint="api_list")
def api_orders_list():
    """Връща всички поръчки (точно както са записани)."""
    store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    return jsonify({"orders": store.get("orders", [])})


@bp.get("/api/calendar_flat", endpoint="api_calendar_flat")
def api_orders_calendar_flat():
    """Плосък списък от поръчки по дни (за календар) + driver данни за бара."""
    store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    raw = store.get("orders", []) or []

    flat = []
    for o in raw:
        title = (
            o.get("title")
            or (o.get("origin") and f"{o.get('origin')} \u2192 {o.get('destination')}")
            or f"Поръчка #{o.get('id')}"
        )
        plate = o.get("vehicle_plate") or o.get("bus_plate") or ""
        t_start = o.get("start_time") or o.get("startTime") or "08:00"
        t_end = o.get("end_time") or o.get("endTime") or "10:00"
        status = o.get("status") or "Планирана"
        desc = o.get("program") or o.get("description") or ""
        driver_id = o.get("driver_id")
        driver_name = o.get("driver_name") or ""
        if not driver_id:
            driver_name = ""

        sd = o.get("start_date") or o.get("date")
        ed = o.get("end_date") or o.get("date") or o.get("start_date")
        sdt = _parse_iso_date(sd)
        edt = _parse_iso_date(ed) or sdt
        if not sdt:
            continue

        for d in _daterange(sdt, edt):
            flat.append(
                {
                    "id": str(o.get("id")),
                    "title": title,
                    "date": _ymd(d),
                    "startTime": t_start,
                    "endTime": t_end,
                    "vehicle_plate": plate,
                    "status": status,
                    "description": desc,
                    "driver_id": driver_id,
                    "driver_name": driver_name,
                }
            )

    flat.sort(key=lambda x: (x["date"], x.get("vehicle_plate", ""), x["id"]))
    return jsonify({"orders": flat})


@bp.post("/api/update_range", endpoint="api_update_range")
def api_update_range():
    """Обновява диапазона (start/end) + по желание табела и статус."""
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    oid = str(payload.get("id") or "").strip()
    sd = payload.get("start_date")
    ed = payload.get("end_date")
    plate = payload.get("vehicle_plate", None)  # None -> не пипай табелата
    status = payload.get("status", None)  # None -> не пипай статуса

    if not oid or not sd:
        return jsonify({"ok": False, "error": "missing id or start_date"}), 400
    if not _parse_iso_date(sd) or (ed and not _parse_iso_date(ed)):
        return jsonify({"ok": False, "error": "invalid dates"}), 400

    store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    changed = False
    for o in store.get("orders", []):
        if str(o.get("id")) == oid:
            o["start_date"] = sd
            o["end_date"] = ed or sd
            if plate is not None:
                o["vehicle_plate"] = plate
                o["bus_plate"] = plate
            if status:
                o["status"] = status
            changed = True
            break

    if changed:
        _save_json(ORDERS_FILE, store)

    return jsonify({"ok": True, "changed": changed})


@bp.post("/api/set_status", endpoint="api_set_status")
def api_set_status():
    """Сетва статус на поръчка по id."""
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    oid = str(payload.get("id", "")).strip()
    status = (payload.get("status") or "").strip()
    if not oid or not status:
        return jsonify({"ok": False, "error": "missing fields"}), 400

    store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    changed = False
    for o in store.get("orders", []):
        if str(o.get("id")) == oid:
            o["status"] = status
            changed = True
            break

    if changed:
        _save_json(ORDERS_FILE, store)

    return jsonify({"ok": True, "changed": changed})


# =========================================================
# API: Assign driver to order (ползва се от календара и списъка)
# =========================================================
@bp.post("/api/assign_driver")
def api_assign_driver():
    """
    JSON body:
      { "id": <order_id>, "driver_id": <int> }

    Обновява полетата driver_id и driver_name в orders.json.
    Ако поръчката се прехвърля от друг шофьор → чисти (логове/токени/телеметрия) за стария.
    """
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"ok": False, "error": "invalid json"}), 400

    order_id = payload.get("id")
    driver_id = payload.get("driver_id")

    try:
        order_id = int(order_id)
        driver_id = int(driver_id)
    except Exception:
        return jsonify({"ok": False, "error": "missing or invalid id/driver_id"}), 400

    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    drivers_store = _load_json(DRIVERS_FILE, {"drivers": [], "next_id": 1})

    order = _get_order(orders_store, order_id)
    if not order:
        return jsonify({"ok": False, "error": "order not found"}), 404

    # намери шофьора по ID
    driver = next((d for d in drivers_store.get("drivers", []) if str(d.get("id")) == str(driver_id)), None)
    if not driver:
        return jsonify({"ok": False, "error": "driver not found"}), 404

    # ако прехвърляме – purge старите данни
    old_driver_id = order.get("driver_id")
    if old_driver_id and str(old_driver_id) != str(driver_id):
        try:
            from app.blueprints.drivers.routes import _purge_driver_order_data
            _purge_driver_order_data(int(old_driver_id), int(order_id))
        except Exception:
            pass

    # запиши
    driver_name = f"{(driver.get('first_name') or '').strip()} {(driver.get('last_name') or '').strip()}".strip()
    order["driver_id"] = driver_id
    order["driver_name"] = driver_name

    _save_json(ORDERS_FILE, orders_store)

    return jsonify({
        "ok": True,
        "order_id": order_id,
        "driver_id": driver_id,
        "driver_name": driver_name,
    })


# === UNASSIGN от списъка (orders/list) ===
@bp.post("/api/unassign_driver")
def api_unassign_driver():
    """
    JSON: { "id": <order_id> }
    Сваля поръчката от текущия шофьор:
      - purge на (logs/tokens/teleметрия) за стария шофьор
      - занулява driver_id и driver_name
    """
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"ok": False, "error": "invalid json"}), 400

    order_id = payload.get("id")
    try:
        order_id = int(order_id)
    except Exception:
        return jsonify({"ok": False, "error": "missing or invalid id"}), 400

    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    o = _get_order(orders_store, order_id)
    if not o:
        return jsonify({"ok": False, "error": "order not found"}), 404

    old_driver_id = o.get("driver_id")
    if not old_driver_id:
        return jsonify({"ok": True, "changed": False})

    # почисти всички свързани данни за стария шофьор и поръчката
    try:
        from app.blueprints.drivers.routes import _purge_driver_order_data
        _purge_driver_order_data(int(old_driver_id), int(order_id))
    except Exception:
        pass

    o["driver_id"] = None
    o["driver_name"] = ""
    _save_json(ORDERS_FILE, orders_store)
    return jsonify({"ok": True, "changed": True})


# === ИЗПРАЩАНЕ НА ТОКЕН (orders/list) с ограничения ===
@bp.post("/api/send_portal_token")
def api_send_portal_token():
    """
    JSON: { "id": <order_id> }
    Създава/изпраща токен към текущия шофьор на поръчката със следните правила:
      1) НЕ може да се прати след започване (today >= start_date)  -> отказ
      2) НЕ може да се прати по-рано от 72 часа преди старта       -> отказ
      3) Формата в портала може да се попълва само за АКТУАЛНИЯ ден и само до end_date (валидира се в portal_save)
      4) Ако има активен токен за (driver_id, order_id) -> не правим нов, връщаме съществуващия
    """
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"ok": False, "error": "invalid json"}), 400

    order_id = payload.get("id")
    try:
        order_id = int(order_id)
    except Exception:
        return jsonify({"ok": False, "error": "missing or invalid id"}), 400

    orders_store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    tokens_store = _load_json(TOKENS_FILE, {"tokens": []})

    o = _get_order(orders_store, order_id)
    if not o:
        return jsonify({"ok": False, "error": "order not found"}), 404

    driver_id = o.get("driver_id")
    if not driver_id:
        return jsonify({"ok": False, "error": "order has no driver"}), 400

    # Дати + прозорец за изпращане (now в локална дата на сървъра)
    try:
        sd = datetime.date.fromisoformat(str(o.get("start_date") or o.get("date"))[:10])
    except Exception:
        return jsonify({"ok": False, "error": "order has invalid start_date"}), 400

    today = datetime.date.today()
    if today >= sd:
        return jsonify({"ok": False, "error": "token cannot be sent after the order has started"}), 400

    # 72 часа преди старта => earliest_send = sd - 3 days
    earliest_send = sd - datetime.timedelta(days=3)
    if today < earliest_send:
        return jsonify({"ok": False, "error": "token cannot be sent earlier than 72 hours before start"}), 400

    # Ако вече има активен токен за същата (order, driver) → върни него
    def _token_is_active(token_obj: dict, order_obj: dict) -> bool:
        if not token_obj or not order_obj:
            return False
        base = order_obj.get("end_date") or order_obj.get("start_date")
        try:
            end_d = datetime.date.fromisoformat(str(base)[:10])
        except Exception:
            return False
        expires_on = end_d + datetime.timedelta(days=1)
        return datetime.date.today() < expires_on

    for t in tokens_store.get("tokens", []) or []:
        if str(t.get("order_id")) == str(order_id) and str(t.get("driver_id")) == str(driver_id):
            if _token_is_active(t, o):
                return jsonify({"ok": True, "token": t.get("token"), "already_exists": True})

    # Създай нов токен и маркирай като 'sent'
    import secrets, datetime as _dt
    token = secrets.token_urlsafe(24)
    tokens_store.setdefault("tokens", []).append({
        "token": token,
        "driver_id": int(driver_id),
        "order_id": int(order_id),
        "created_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "sent": True,
    })
    _save_json(TOKENS_FILE, tokens_store)

    return jsonify({"ok": True, "token": token, "already_exists": False})


# =========================================================
# Детайл на поръчка – таб „Кабинет“ (фронтендът ползва API-тата по-долу)
# =========================================================
@bp.get("/<int:order_id>", endpoint="detail")
def order_detail(order_id: int):
    """
    Детайл на поръчка: рендерира таб с „Кабинет“ (задачи, файлове, timeline, съобщения).
    Фронтендът ползва /orders/api/cabinet/snapshot?id=<id> и свързаните API-та.
    """
    store = _load_json(ORDERS_FILE, {"orders": [], "next_id": 1})
    o = _get_order(store, order_id)
    if not o:
        flash("Поръчката не е намерена.", "warning")
        return redirect(url_for("orders.list"))

    title = o.get("title") or f"Поръчка #{o.get('id')}"
    return render_template("orders/detail.html", order_id=order_id, order_title=title, page="orders")


# =========================================================
# „Кабинет“ – Snapshot + Files + Tasks + Messages (централен store)
# =========================================================
@bp.get("/api/cabinet/snapshot")
def api_cabinet_snapshot():
    """
    GET /orders/api/cabinet/snapshot?id=<order_id>
    Връща обобщена информация + cabinet данните (tasks, files, log) за order_id.
    """
    oid = request.args.get("id", type=int)
    if not oid:
        return jsonify({"ok": False, "error": "missing id"}), 400

    snap = _build_cabinet_snapshot(oid)
    if not snap:
        return jsonify({"ok": False, "error": "order not found"}), 404
    return jsonify(snap)


@bp.get("/api/cabinet/summary_html")
def api_cabinet_summary_html():
    """
    GET /orders/api/cabinet/summary_html?id=<order_id>
    Връща минимален HTML на резюмето, готов за печат (бутонът може да отвори нов прозорец с този HTML).
    """
    oid = request.args.get("id", type=int)
    if not oid:
        return "Missing id", 400
    snap = _build_cabinet_snapshot(oid)
    if not snap:
        return "Order not found", 404

    s = snap["summary"]

    # Безопасен HTML (escape)
    def esc(x): return html_escape(str(x if x is not None else ""))

    # Малък стил за печат
    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>Резюме поръчка #{esc(oid)}</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }}
  h1 {{ font-size: 20px; margin: 0 0 12px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
  .muted {{ color: #6b7280; }}
  .section {{ margin-top: 18px; }}
  .right {{ text-align: right; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:9999px; background:#eef2ff; color:#3730a3; font-size:12px; }}
  .btn {{ display:inline-block; padding:8px 12px; border:1px solid #cbd5e1; border-radius:8px; text-decoration:none; color:#111827; }}
  .btn-print {{ margin-bottom: 16px; }}
  @media print {{
    .btn-print {{ display: none; }}
  }}
</style>
</head>
<body>
<a href="#" class="btn btn-print" onclick="window.print();return false;">🖨 Разпечатай</a>
<h1>Резюме · Поръчка #{esc(oid)}</h1>

<table>
  <tr><th>Описание</th><td>{esc(s.get("title",""))}</td></tr>
  <tr><th>Диапазон</th><td>{esc(s.get("start_date",""))} → {esc(s.get("end_date",""))} ({esc(s.get("work_plan", {}).get("days",""))} дни)</td></tr>
  <tr><th>Автобус</th><td>{esc(s.get("bus_plate",""))}</td></tr>
  <tr><th>Статус</th><td>{esc(s.get("status",""))}</td></tr>
  <tr><th>Шофьор</th><td>{esc(s.get("driver_name") or "—")}</td></tr>
  <tr><th>PAX</th><td>{esc(s.get("pax") or "—")}</td></tr>
  <tr><th>Бюджет 1</th><td>{esc(s.get("budget1_tag_date") or "—")}</td></tr>
  <tr><th>Бюджет 2</th><td>{esc(s.get("budget2_tag_date") or "—")}</td></tr>
  <tr><th>Двупосочно</th><td>{'Да' if s.get("round_trip") else 'Не'}</td></tr>
</table>

<div class="section">
  <h2>Финанси</h2>
  <table>
    <tr><th>Цена (приход)</th><td class="right mono">{s['price']:.2f} €</td></tr>
    <tr><th>Директни разходи</th><td class="right mono">{s['direct_costs']:.2f} €</td></tr>
    <tr><th>Брутна печалба</th><td class="right mono">{s['gross_profit']:.2f} €</td></tr>
    <tr><th>Марж</th><td class="right mono">{s['margin_pct']:.2f} %</td></tr>
  </table>
  <div class="muted">Разбивка разходи: гориво {s['costs_breakdown']['fuel_sum']:.2f} €, пътни такси {s['costs_breakdown']['toll_firm']:.2f} €, други {s['costs_breakdown']['extras_firm']:.2f} €, персонал {s['costs_breakdown']['personnel_total']:.2f} €.</div>
</div>

<div class="section">
  <h2>Планирано работно време</h2>
  <table>
    <tr><th>Режим</th><td>{esc(s['work_plan']['mode'])}</td></tr>
    <tr><th>Дни</th><td>{esc(s['work_plan']['days'])}</td></tr>
    <tr><th>Часове/ден</th><td>{esc(s['work_plan']['hours_per_day'] or '—')}</td></tr>
    <tr><th>Планирани часове общо</th><td>{esc(s['work_plan']['planned_hours_total'] or '—')}</td></tr>
    <tr><th>Втори шофьор</th><td>{'Да' if s['work_plan']['second_driver'] else 'Не'}</td></tr>
    <tr><th>Дни втори шофьор</th><td>{esc(s['work_plan']['second_driver_days'] or '—')}</td></tr>
  </table>
</div>

</body>
</html>
"""
    resp = make_response(html, 200)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@bp.get("/api/cabinet/<int:order_id>")
def api_cabinet(order_id: int):
    """
    GET /orders/api/cabinet/<order_id>
    -> същият snapshot като /orders/api/cabinet/snapshot?id=...
    (удобно за стария фронтенд)
    """
    snap = _build_cabinet_snapshot(order_id)
    if not snap:
        return jsonify({"ok": False, "error": "order not found"}), 404
    return jsonify(snap)


# ---------------- Files: upload/download/delete (старите пътища, back-compat) ----------------
@bp.post("/api/files/upload")
def api_cabinet_files_upload():
    """
    POST /orders/api/files/upload
      form-data:
        - id: <order_id>
        - file: <uploaded file>
    Записва файла в data/order_files/<id>/ и добавя запис в cabinet store.
    """
    oid = request.form.get("id", type=int)
    if not oid:
        return jsonify({"ok": False, "error": "missing id"}), 400
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "missing file"}), 400

    base = _ensure_files_dir(oid)
    safe_name = _filename_unique(base, f.filename or "file.bin")
    full = base / safe_name
    f.save(full)

    cab_store = _cabinet_load()
    cab = _cabinet_get_order(cab_store, oid)

    size = full.stat().st_size if full.exists() else 0
    rec = {
        "name": safe_name,
        "size": size,
        "uploaded_at": _cabinet_now_iso(),
        "url": url_for("orders.api_cabinet_files_download", id=oid, name=safe_name, _external=False),
    }
    cab["files"] = [x for x in cab.get("files", []) if x.get("name") != safe_name] + [rec]
    _cabinet_save(cab_store)

    return jsonify({"ok": True, "files": cab["files"]})


@bp.get("/api/files/download")
def api_cabinet_files_download():
    """
    GET /orders/api/files/download?id=<order_id>&name=<filename>
    Връща файла за сваляне.
    """
    oid = request.args.get("id", type=int)
    name = request.args.get("name", type=str)
    if not oid or not name:
        return jsonify({"ok": False, "error": "missing id or name"}), 400
    base = _ensure_files_dir(oid)
    path = base / secure_filename(name)
    if not path.exists():
        return jsonify({"ok": False, "error": "file not found"}), 404
    return send_from_directory(base, path.name, as_attachment=True, download_name=path.name)


@bp.post("/api/files/delete")
def api_cabinet_files_delete():
    """
    POST /orders/api/files/delete
      JSON: { "id": <order_id>, "name": "<filename>" }
    Трие файла и записa от cabinet store.
    """
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    oid = payload.get("id")
    name = payload.get("name")
    try:
        oid = int(oid)
    except Exception:
        return jsonify({"ok": False, "error": "invalid id"}), 400
    if not name:
        return jsonify({"ok": False, "error": "missing name"}), 400

    base = _ensure_files_dir(oid)
    path = base / secure_filename(name)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass

    cab_store = _cabinet_load()
    cab = _cabinet_get_order(cab_store, oid)
    cab["files"] = [x for x in cab.get("files", []) if x.get("name") != name]
    _cabinet_save(cab_store)
    return jsonify({"ok": True, "files": cab["files"]})


# ---------------- NEW: CABINET Files (list/upload/delete по новите пътища) ----------------
@bp.get("/api/cabinet/files/list")
def api_cabinet_files_list_v2():
    """
    GET /orders/api/cabinet/files/list?id=<order_id>
    Връща {"ok":true,"files":[{id,name,url,uploaded_at,size}]}
    """
    oid = request.args.get("id", type=int)
    if not oid:
        return jsonify({"ok": False, "error": "missing id"}), 400

    store = _cabinet_load()
    cab = _cabinet_get_order(store, oid)

    if _cabinet_ensure_file_ids(cab):
        _cabinet_save(store)

    files = []
    for f in cab.get("files", []):
        files.append({
            "id": f.get("id"),
            "name": f.get("name") or f.get("filename") or "",
            "url": f.get("url") or url_for("orders.api_cabinet_files_download", id=oid, name=f.get("name"), _external=False),
            "uploaded_at": f.get("uploaded_at") or _cabinet_now_iso(),
            "size": f.get("size", 0),
        })
    return jsonify({"ok": True, "files": files})


@bp.post("/api/cabinet/files/upload")
def api_cabinet_files_upload_v2():
    """
    POST form-data: id, file
    Същото като /api/files/upload, но добавя 'id' към записа + връща {"ok":true, id, name, url}.
    """
    oid = request.form.get("id", type=int)
    if not oid:
        return jsonify({"ok": False, "error": "missing id"}), 400
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "missing file"}), 400

    base = _ensure_files_dir(oid)
    safe_name = _filename_unique(base, f.filename or "file.bin")
    full = base / safe_name
    f.save(full)

    store = _cabinet_load()
    cab = _cabinet_get_order(store, oid)
    if _cabinet_ensure_file_ids(cab):
        _cabinet_save(store)

    size = full.stat().st_size if full.exists() else 0
    fid = _cabinet_next_id(cab.get("files", []))
    rec = {
        "id": fid,
        "name": safe_name,
        "size": size,
        "uploaded_at": _cabinet_now_iso(),
        "url": url_for("orders.api_cabinet_files_download", id=oid, name=safe_name, _external=False),
    }
    cab["files"] = [x for x in cab.get("files", []) if x.get("name") != safe_name] + [rec]
    _cabinet_save(store)

    return jsonify({"ok": True, "id": fid, "name": safe_name, "url": rec["url"]})


@bp.post("/api/cabinet/files/delete")
def api_cabinet_files_delete_v2():
    """
    POST JSON: { id: <order_id>, file_id: <int> } ИЛИ { id, name }
    Трие файла физически + от store. Връща {"ok":true}.
    """
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    oid = payload.get("id")
    fid = payload.get("file_id")
    name = payload.get("name")

    try:
        oid = int(oid)
    except Exception:
        return jsonify({"ok": False, "error": "invalid id"}), 400

    store = _cabinet_load()
    cab = _cabinet_get_order(store, oid)
    _cabinet_ensure_file_ids(cab)

    target = None
    if fid is not None:
        try:
            fid = int(fid)
        except Exception:
            return jsonify({"ok": False, "error": "invalid file_id"}), 400
        for f in cab.get("files", []):
            if int(f.get("id", -1)) == fid:
                target = f
                break
    elif name:
        for f in cab.get("files", []):
            if f.get("name") == name:
                target = f
                break
    else:
        return jsonify({"ok": False, "error": "missing file_id or name"}), 400

    if not target:
        return jsonify({"ok": False, "error": "file not found"}), 404

    # delete from disk
    base = _ensure_files_dir(oid)
    path = base / secure_filename(target.get("name"))
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass

    # delete from store
    cab["files"] = [x for x in cab.get("files", []) if x is not target]
    _cabinet_save(store)
    return jsonify({"ok": True})


# ---------------- NEW: CABINET Tasks ----------------
@bp.get("/api/cabinet/tasks/list")
def api_cabinet_tasks_list_v2():
    oid = request.args.get("id", type=int)
    if not oid:
        return jsonify({"ok": False, "error": "missing id"}), 400
    store = _cabinet_load()
    cab = _cabinet_get_order(store, oid)
    if _cabinet_ensure_task_ids(cab):
        _cabinet_save(store)
    return jsonify({"ok": True, "tasks": cab.get("tasks", [])})


@bp.post("/api/cabinet/tasks/add")
def api_cabinet_tasks_add_v2():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    oid = payload.get("id")
    text = (payload.get("text") or "").strip()
    try:
        oid = int(oid)
    except Exception:
        return jsonify({"ok": False, "error": "invalid id"}), 400
    if not text:
        return jsonify({"ok": False, "error": "missing text"}), 400

    store = _cabinet_load()
    cab = _cabinet_get_order(store, oid)
    if _cabinet_ensure_task_ids(cab):
        _cabinet_save(store)

    tid = _cabinet_next_id(cab.get("tasks", []))
    cab.setdefault("tasks", []).append({
        "id": tid,
        "text": text,
        "done": False,
        "created_at": _cabinet_now_iso(),
    })
    _cabinet_save(store)
    return jsonify({"ok": True, "id": tid})


@bp.post("/api/cabinet/tasks/delete")
def api_cabinet_tasks_delete_v2():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    oid = payload.get("id")
    tid = payload.get("task_id")
    try:
        oid = int(oid); tid = int(tid)
    except Exception:
        return jsonify({"ok": False, "error": "invalid id/task_id"}), 400

    store = _cabinet_load()
    cab = _cabinet_get_order(store, oid)
    before = len(cab.get("tasks", []))
    cab["tasks"] = [t for t in cab.get("tasks", []) if int(t.get("id", -1)) != tid]
    _cabinet_save(store)
    return jsonify({"ok": True, "deleted": (len(cab.get("tasks", [])) < before)})


# ---------------- NEW: CABINET Log / Messages ----------------
@bp.get("/api/cabinet/log/list")
def api_cabinet_log_list_v2():
    oid = request.args.get("id", type=int)
    if not oid:
        return jsonify({"ok": False, "error": "missing id"}), 400
    store = _cabinet_load()
    cab = _cabinet_get_order(store, oid)
    out = []
    for m in cab.get("log", []):
        out.append({
            "ts": m.get("when") or m.get("ts") or _cabinet_now_iso(),
            "author": m.get("author") or "",
            "text": m.get("text") or "",
        })
    return jsonify({"ok": True, "log": out})


@bp.post("/api/cabinet/log/add")
def api_cabinet_log_add_v2():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    oid = payload.get("id")
    text = (payload.get("text") or "").strip()
    author = (payload.get("author") or "").strip() or "system"
    try:
        oid = int(oid)
    except Exception:
        return jsonify({"ok": False, "error": "invalid id"}), 400
    if not text:
        return jsonify({"ok": False, "error": "missing text"}), 400

    store = _cabinet_load()
    cab = _cabinet_get_order(store, oid)
    cab.setdefault("log", []).insert(0, {
        "when": _cabinet_now_iso(),
        "author": author,
        "text": text,
    })
    _cabinet_save(store)
    return jsonify({"ok": True})


# =========================================================
# Алиаси към по-старите /desk/... пътища (бек-совместимост)
# =========================================================
@bp.get("/api/desk/<int:oid>")
def api_desk_snapshot_alias(oid: int):
    """Алиас на /api/cabinet/snapshot?id=..."""
    snap = _build_cabinet_snapshot(oid)
    if not snap:
        return jsonify({"ok": False, "error": "order not found"}), 404
    return jsonify(snap)


@bp.get("/api/desk/<int:oid>/files")
def api_desk_files_list_alias(oid: int):
    """Връща списъка от файлове (използвай snapshot за консистентност)."""
    store = _cabinet_load()
    cab = _cabinet_get_order(store, oid)
    return jsonify({"ok": True, "files": cab.get("files", [])})


@bp.post("/api/desk/<int:oid>/files")
def api_desk_files_upload_alias(oid: int):
    """
    Алиас към /api/files/upload, но с URL параметър за id.
    """
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "missing file"}), 400
    base = _ensure_files_dir(oid)
    safe_name = _filename_unique(base, f.filename or "file.bin")
    full = base / safe_name
    f.save(full)
    cab_store = _cabinet_load()
    cab = _cabinet_get_order(cab_store, oid)
    size = full.stat().st_size if full.exists() else 0
    rec = {
        "name": safe_name,
        "size": size,
        "uploaded_at": _cabinet_now_iso(),
        "url": url_for("orders.api_cabinet_files_download", id=oid, name=safe_name, _external=False),
    }
    cab["files"] = [x for x in cab.get("files", []) if x.get("name") != safe_name] + [rec]
    _cabinet_save(cab_store)
    return jsonify({"ok": True, "files": cab["files"]})


@bp.post("/api/desk/<int:oid>/tasks")
def api_desk_tasks_add_alias(oid: int):
    """Алиас към /api/tasks/add (JSON: {text})."""
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "missing text"}), 400
    cab_store = _cabinet_load()
    cab = _cabinet_get_order(cab_store, oid)
    tid = _task_id(cab.get("tasks", []))
    cab["tasks"].append({"id": tid, "text": text, "done": False, "created_at": _cabinet_now_iso()})
    _cabinet_save(cab_store)
    return jsonify({"ok": True, "tasks": cab["tasks"]})


@bp.get("/api/desk/<int:oid>/tasks")
def api_desk_tasks_list_alias(oid: int):
    """
    GET /orders/api/desk/<oid>/tasks
    Връща {"ok": true, "tasks": [...]}, за да е съвместимо с фронта в list.html.
    Данните се четат от data/orders_cabinet.json (централния Cabinet store).
    """
    cab_store = _cabinet_load()
    cab = _cabinet_get_order(cab_store, oid)
    return jsonify({"ok": True, "tasks": cab.get("tasks", [])})


@bp.post("/api/desk/<int:oid>/tasks/toggle")
def api_desk_tasks_toggle_alias(oid: int):
    """Алиас към /api/tasks/toggle (JSON: {id/task_id})."""
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    tid = payload.get("id") or payload.get("task_id")
    try:
        tid = int(tid)
    except Exception:
        return jsonify({"ok": False, "error": "invalid task id"}), 400
    cab_store = _cabinet_load()
    cab = _cabinet_get_order(cab_store, oid)
    changed = False
    for t in cab.get("tasks", []):
        if int(t.get("id") or -1) == tid:
            t["done"] = not bool(t.get("done"))
            changed = True
            break
    if changed:
        _cabinet_save(cab_store)
    return jsonify({"ok": True, "tasks": cab["tasks"], "changed": changed})


@bp.get("/api/desk/<int:oid>/log")
def api_desk_log_list_alias(oid: int):
    store = _cabinet_load()
    cab = _cabinet_get_order(store, oid)
    return jsonify({"ok": True, "log": cab.get("log", [])})


@bp.post("/api/desk/<int:oid>/log")
def api_desk_log_add_alias(oid: int):
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    text = (payload.get("text") or "").strip()
    author = (payload.get("author") or "").strip() or "system"
    if not text:
        return jsonify({"ok": False, "error": "missing text"}), 400
    cab_store = _cabinet_load()
    cab = _cabinet_get_order(cab_store, oid)
    cab.setdefault("log", []).insert(0, {"when": _cabinet_now_iso(), "author": author, "text": text})
    _cabinet_save(cab_store)
    return jsonify({"ok": True, "log": cab["log"]})


@bp.after_request
def _orders_api_no_cache(resp):
    try:
        p = request.path
        if p.startswith("/orders/api/"):
            # Забраняваме кеширане на JSON отговорите на API-то
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
    except Exception:
        pass
    return resp

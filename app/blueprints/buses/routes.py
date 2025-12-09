from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from . import bp
import json, os
from datetime import datetime

# --------- helpers: пътища и storage ---------
def _data_dir_candidates():
    app_root  = current_app.root_path                      # .../app
    proj_root = os.path.abspath(os.path.join(app_root, os.pardir))  # проектен корен
    inst_root = current_app.instance_path                  # instance/
    cwd_root  = os.getcwd()
    env_dir   = os.environ.get("BUSOPS_DATA_DIR")

    # legacy корен (старото parents[3]) – за съвместимост, ако там е останал файлът
    legacy_root = os.path.abspath(os.path.join(__file__, os.pardir, os.pardir, os.pardir, os.pardir))

    dirs = [
        os.path.join(app_root,  "data"),
        os.path.join(proj_root, "data"),
        os.path.join(inst_root, "data"),
        os.path.join(cwd_root,  "data"),
        env_dir,
        os.path.join(legacy_root, "data"),
    ]
    # уникализирай, пази реда
    unique = []
    for d in dirs:
        if d and d not in unique:
            unique.append(d)
    return unique

def _pick_existing_buses_json():
    """Върни път към ПЪРВИЯ съществуващ и валиден buses.json с данни (buses != [])."""
    for d in _data_dir_candidates():
        path = os.path.join(d, "buses.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                buses = []
                if isinstance(data, dict):
                    buses = data.get("buses") or []
                elif isinstance(data, list):
                    # позволяваме чист списък от автобуси
                    buses = data
                if isinstance(buses, list) and len(buses) > 0:
                    return path
            except Exception:
                continue
    return None

def _first_writable_buses_json():
    """Върни път за запис в първата достъпна data/ директория (създава я при нужда)."""
    for d in _data_dir_candidates():
        try:
            if d:
                os.makedirs(d, exist_ok=True)
                return os.path.join(d, "buses.json")
        except Exception:
            continue
    os.makedirs("data", exist_ok=True)
    return os.path.join("data", "buses.json")

def _data_file_path():
    # 1) Ако вече има съществуващ с данни → ползваме него
    existing = _pick_existing_buses_json()
    if existing:
        return existing
    # 2) Ако няма – вземи първия валиден път и създай нов файл при запис
    return _first_writable_buses_json()

def _ensure_store_shape(store):
    # приемаме 2 форми: dict {"buses":[...], "next_bus_id":N} ИЛИ директно list [...]
    if isinstance(store, list):
        return {"buses": store, "next_bus_id": (max((b.get("id", 0) for b in store if isinstance(b, dict)), default=0) + 1)}
    if not isinstance(store, dict):
        store = {}
    store.setdefault("buses", [])
    store.setdefault("next_bus_id", 1)
    return store

def _load():
    path = _data_file_path()
    if not os.path.exists(path):
        _save({"buses": [], "next_bus_id": 1})
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"buses": [], "next_bus_id": 1}
    return _ensure_store_shape(data)

def _save(store):
    path = _data_file_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_ensure_store_shape(store), f, ensure_ascii=False, indent=2)

def _norm_plate(obj):
    for k in ("reg_no", "reg", "plate", "number", "registration", "bus_plate", "regnum"):
        v = obj.get(k) if isinstance(obj, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    return ""

def fetch_buses_list():
    """Унифициран loader за /buses/ и статистиката."""
    store = _load()
    buses = []
    for b in store.get("buses", []):
        reg = _norm_plate(b)
        if reg:
            b["reg_no"] = reg
        buses.append(b)
    buses.sort(key=lambda x: (x.get("reg_no") or "").lower())
    return buses

# --------- /buses ----------


@bp.route("/edit/<int:bus_id>", methods=["GET", "HEAD"], endpoint="edit")
def edit(bus_id):
    store = _load()
    bus = next((b for b in store.get("buses", []) if int(b.get("id", 0)) == int(bus_id)), None)
    if not bus:
        flash("Автобус не е намерен.", "warning")
        return redirect(url_for("buses.index"))
    # списъкът за таблицата
    buses = fetch_buses_list()
    # подаваме текущия автобус за предварително попълване
    return render_template("buses/index.html", page="buses", buses=buses, edit_bus=bus)


@bp.route("/", methods=["GET", "POST"])
def index():
    store = _load()

    if request.method == "POST":
        form = request.form

        def _num(v, cast=float):
            try:
                return cast(v) if v not in ("", None) else None
            except Exception:
                return None

        try:
            edit_id = int(form.get("edit_id")) if form.get("edit_id") else None
        except Exception:
            edit_id = None
        bus_id = edit_id or store.get("edit_bus_id") or store["next_bus_id"]

        bus = {
            "id": bus_id,
            "reg_no": (form.get("reg_no") or "").strip().upper(),
            "seats": _num(form.get("seats"), int),
            "tech_inspection_date": form.get("tech_inspection_date") or None,
            "fuel_consumption": _num(form.get("fuel_consumption")),
            "tank_size": _num(form.get("tank_size"), int),
            "insurance_cost": _num(form.get("insurance_cost")),
            "monthly_credit": _num(form.get("monthly_credit")),
        }

        existing = next((b for b in store["buses"] if int(b.get("id")) == int(bus_id)), None)
        if existing:
            persisted = {
                "service_log": existing.get("service_log", []),
                "inactive": existing.get("inactive", False),
                "has_orders": existing.get("has_orders", False),
            }
            existing.update(bus)
            existing.update(persisted)
            flash("Автобусът е обновен.", "success")
        else:
            bus.update({"service_log": [], "inactive": False, "has_orders": False})
            store["buses"].append(bus)
            store["next_bus_id"] = int(store.get("next_bus_id", 1)) + 1
            flash("Автобусът е добавен.", "success")

        _save(store)
        return redirect(url_for("buses.index"))

    # GET
    buses = fetch_buses_list()
    return render_template("buses/index.html", page="buses", buses=buses)

@bp.route("/delete/<int:bus_id>", methods=["POST"])
def delete_bus(bus_id):
    store = _load()
    bus = next((b for b in store["buses"] if int(b.get("id")) == int(bus_id)), None)
    if not bus:
        flash("Автобус не е намерен.", "warning")
        return redirect(url_for("buses.index"))

    if bus.get("has_orders"):
        bus["inactive"] = True
        flash("Автобусът има поръчки — преместен е в НЕАКТИВНИ.", "info")
    else:
        store["buses"] = [b for b in store["buses"] if int(b.get("id")) != int(bus_id)]
        flash("Автобусът е изтрит.", "success")

    _save(store)
    return redirect(url_for("buses.index"))

# --------- Сервизна книжка ----------
@bp.route("/service/<int:bus_id>", methods=["GET", "POST"])
def service_book(bus_id):
    store = _load()
    buses_sorted = sorted(store.get("buses", []), key=lambda x: int(x.get("id", 0)))
    bus = next((b for b in buses_sorted if int(b.get("id", 0)) == int(bus_id)), None)
    if not bus:
        flash("Автобус не е намерен.", "warning")
        return redirect(url_for("buses.index"))

    if request.method == "POST":
        form = request.form
        try:
            next_entry_id = max(e.get("id", 0) for e in bus.get("service_log", [])) + 1 if bus.get("service_log") else 1
        except Exception:
            next_entry_id = 1
        entry = {
            "id": next_entry_id,
            "date": form.get("date") or datetime.utcnow().date().isoformat(),
            "kind": form.get("kind") or "repair",  # repair | expense
            "title": (form.get("title") or "").strip(),
            "amount": float(form.get("amount")) if form.get("amount") else 0.0,
            "notes": (form.get("notes") or "").strip()
        }
        bus.setdefault("service_log", []).append(entry)
        _save(store)
        flash("Записът е добавен.", "success")
        return redirect(url_for("buses.service_book", bus_id=bus_id))

    idx = next((i for i, b in enumerate(buses_sorted) if int(b.get("id", 0)) == int(bus_id)), None)
    prev_id = buses_sorted[idx - 1]["id"] if idx is not None and idx > 0 else None
    next_id = buses_sorted[idx + 1]["id"] if idx is not None and idx < len(buses_sorted) - 1 else None

    total_repairs  = sum(e.get("amount", 0.0) for e in bus.get("service_log", []) if e.get("kind") == "repair")
    total_expenses = sum(e.get("amount", 0.0) for e in bus.get("service_log", []) if e.get("kind") == "expense")

    return render_template(
        "buses/service_book.html",
        page="buses",
        bus=bus,
        total_repairs=total_repairs,
        total_expenses=total_expenses,
        prev_id=prev_id,
        next_id=next_id
    )

@bp.route("/service/<int:bus_id>/delete/<int:entry_id>", methods=["POST"])
def delete_service_entry(bus_id, entry_id):
    store = _load()
    bus = next((b for b in store["buses"] if int(b.get("id")) == int(bus_id)), None)
    if not bus:
        flash("Невалиден автобус.", "danger")
        return redirect(url_for("buses.index"))

    before = len(bus.get("service_log", []))
    bus["service_log"] = [e for e in bus.get("service_log", []) if int(e.get("id", 0)) != int(entry_id)]
    _save(store)
    flash("Записът е изтрит." if len(bus.get("service_log", [])) < before else "Записът не е намерен.", "info")
    return redirect(url_for("buses.service_book", bus_id=bus_id))

# --------- API ----------
@bp.route('/api/list')
def api_list():
    buses = fetch_buses_list()
    active, inactive = [], []
    for b in buses:
        plate = _norm_plate(b)
        if not plate:
            continue
        (inactive if b.get("inactive") else active).append(plate)
    return jsonify({"active": active, "inactive": inactive, "buses": buses})

@bp.route('/api/mark_used', methods=['POST'])
def api_mark_used():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    plate = (payload.get("plate") or "").strip().upper()
    if not plate:
        return jsonify({"ok": False, "error": "missing plate"}), 400

    store = _load()
    changed = False
    for b in store.get("buses", []):
        if _norm_plate(b) == plate:
            if not b.get("has_orders"):
                b["has_orders"] = True
                changed = True
            break
    if changed:
        _save(store)
    return jsonify({"ok": True, "changed": changed})

@bp.route('/api/set_inactive', methods=['POST'])
def api_set_inactive():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    plate  = (payload.get("plate") or "").strip().upper()
    bus_id = payload.get("bus_id")

    store = _load()
    bus = None
    if plate:
        bus = next((b for b in store.get("buses", []) if _norm_plate(b) == plate), None)
    if not bus and bus_id is not None:
        bus = next((b for b in store.get("buses", []) if int(b.get("id")) == int(bus_id)), None)
    if not bus:
        return jsonify({"ok": False, "error": "bus not found"}), 404

    bus["inactive"] = True
    _save(store)
    return jsonify({"ok": True})

@bp.route('/set_inactive/<int:bus_id>', methods=['POST'])
def set_inactive(bus_id):
    store = _load()
    bus = next((b for b in store["buses"] if int(b.get("id")) == int(bus_id)), None)
    if not bus:
        flash("Автобус не е намерен.", "warning")
        return redirect(url_for("buses.index"))
    bus["inactive"] = True
    _save(store)
    flash("Автобусът е маркиран като неактивен.", "success")
    return redirect(url_for("buses.index"))

@bp.route('/set_active/<int:bus_id>', methods=['POST'])
def set_active(bus_id):
    store = _load()
    bus = next((b for b in store["buses"] if int(b.get("id")) == int(bus_id)), None)
    if not bus:
        flash("Автобус не е намерен.", "warning")
        return redirect(url_for("buses.index"))
    bus["inactive"] = False
    _save(store)
    flash("Автобусът е активиран.", "success")
    return redirect(url_for("buses.index"))

# --- DEBUG: виж кой файл се ползва ---
@bp.route('/api/debug_path')
def api_debug_path():
    return jsonify({"buses_json_path": _data_file_path()})

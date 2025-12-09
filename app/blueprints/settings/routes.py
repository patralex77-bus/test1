# -*- coding: utf-8 -*-
from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash
from pathlib import Path
import json

# Единствен blueprint за /settings
bp = Blueprint("settings_countries", __name__, url_prefix="/settings", template_folder="templates")

# Пътища към JSON
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
COUNTRIES_FILE = DATA_DIR / "settings.json"            # държави (стар файл)
PAYROLL_FILE   = DATA_DIR / "settings_payroll.json"    # ново: настройки за заплати


# ---------------- helpers ----------------
def _load_json(path: Path, default):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))

def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------- settings index ----------------
@bp.get("/")
def index():
    """Главна страница на настройките → показва меню с линкове."""
    return render_template("settings/index.html")


# ---------------- countries (старото подменю) ----------------
@bp.route("/countries", methods=["GET", "POST"])
def countries():
    store = _load_json(COUNTRIES_FILE, {"countries": []})

    if request.method == "POST":
        form = request.form
        name        = (form.get("name") or "").strip()
        fee_per_km  = float(form.get("fee_per_km") or 0.0)
        fee_per_day = float(form.get("fee_per_day") or 0.0)
        fuel_price  = float(form.get("fuel_price") or 0.0)
        vat_percent = float(form.get("vat_percent") or 0.0)

        if not name:
            flash("Въведете държава.", "warning")
            return redirect(url_for("settings_countries.countries"))

        existing = next((c for c in store["countries"] if c["name"].lower() == name.lower()), None)
        payload = {
            "name": name,
            "fee_per_km": fee_per_km,
            "fee_per_day": fee_per_day,
            "fuel_price": fuel_price,
            "vat_percent": vat_percent,
        }
        if existing:
            existing.update(payload)
            flash("Обновихте държавата.", "success")
        else:
            store["countries"].append(payload)
            flash("Добавихте държава.", "success")

        _save_json(COUNTRIES_FILE, store)
        return redirect(url_for("settings_countries.countries"))

    countries = sorted(store["countries"], key=lambda x: x["name"].lower())
    return render_template("settings/countries.html", page="settings", countries=countries)


@bp.post("/countries/delete/<name>")
def delete_country(name):
    store = _load_json(COUNTRIES_FILE, {"countries": []})
    before = len(store["countries"])
    store["countries"] = [c for c in store["countries"] if c["name"] != name]
    _save_json(COUNTRIES_FILE, store)
    flash("Изтрихте държавата." if len(store["countries"]) < before else "Държавата не е намерена.", "info")
    return redirect(url_for("settings_countries.countries"))


# ---------------- payroll (НОВО подменю „Заплати“) ----------------
@bp.route("/payroll", methods=["GET", "POST"])
def payroll():
    """
    Настройки за заплати (ползват се в драйверския детайл за проекции и в бюджети):
      - daily_fixed: дневна FIX ставка
      - hourly_contract: часова ставка по договор
      - hourly_custom: часова ставка по договореност
      - min_hours: минимални часове/ден (за проверки)
      - max_hours: максимални часове/ден (за проверки)
    """
    defaults = {
        "daily_fixed": 80.0,
        "hourly_contract": 10.0,
        "hourly_custom": 12.0,
        "min_hours": 0.0,
        "max_hours": 13.0,
    }
    data = _load_json(PAYROLL_FILE, defaults)
    # гарантирай ключове
    for k, v in defaults.items():
        data.setdefault(k, v)

    if request.method == "POST":
        try:
            daily_fixed     = float(request.form.get("daily_fixed") or 0)
            hourly_contract = float(request.form.get("hourly_contract") or 0)
            hourly_custom   = float(request.form.get("hourly_custom") or 0)
            min_hours       = float(request.form.get("min_hours") or 0)
            max_hours       = float(request.form.get("max_hours") or 0)

            if min_hours > max_hours:
                flash("Минималните часове не може да превишават максималните.", "warning")
                # покажи отново формата със старите стойности
                return render_template("settings/payroll.html", s=data)

            data.update(
                dict(
                    daily_fixed=daily_fixed,
                    hourly_contract=hourly_contract,
                    hourly_custom=hourly_custom,
                    min_hours=min_hours,
                    max_hours=max_hours,
                )
            )
            _save_json(PAYROLL_FILE, data)
            flash("Настройките за заплати са записани.", "success")
            return redirect(url_for("settings_countries.payroll"))
        except ValueError:
            flash("Въведете валидни числови стойности.", "warning")

    return render_template("settings/payroll.html", s=data)

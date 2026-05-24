import os
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from zoneinfo import ZoneInfo

from app.services.booking_importer import ImportEmailPayload, import_booking_email

from sqlalchemy.orm import Session
from sqlalchemy import func, text, case, or_, cast, String

from .db import Base, engine, get_db
from . import crud
from .excel_import import parse_xlsx
from .models import TripPassenger, Trip

Base.metadata.create_all(bind=engine)

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

app = FastAPI()

# ---- Sessions + Passwords ----
SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
DRIVER_PASSWORD = os.environ.get("DRIVER_PASSWORD", "").strip()
ADMIN_PASSWORD1 = os.environ.get("ADMIN_PASSWORD1", "").strip()

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


# =======================
# Helpers
# =======================
def _safe_int_passenger_no(v) -> int:
    try:
        if v is None:
            return 10**9
        s = str(v).strip()
        if s == "":
            return 10**9
        s = s.split(".")[0]
        return int(s)
    except Exception:
        return 10**9


def _manual_to_none(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s != "" else None


def _effective_text(manual_value, base_value):
    mv = (manual_value or "").strip() if manual_value is not None else ""
    return mv if mv != "" else (base_value or "")


def _effective_sql_text(manual_col, base_col):
    return func.coalesce(func.nullif(manual_col, ""), base_col, "")


def _ensure_admin(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(401, "Not authorized")


def _ensure_driver(request: Request):
    if not request.session.get("is_driver"):
        raise HTTPException(401, "Not authorized")


def _ensure_admin_or_redirect(request: Request):
    if not request.session.get("is_admin"):
        next_url = request.url.path
        if request.url.query:
            next_url += f"?{request.url.query}"
        return RedirectResponse(
            url=f"/admin/login?next={quote(next_url, safe='/?=&')}",
            status_code=303,
        )
    return None


def _today_vienna() -> date:
    return datetime.now(ZoneInfo("Europe/Vienna")).date()


def _ensure_resumee_or_redirect(request: Request):
    if not request.session.get("is_resumee"):
        next_url = request.url.path
        if request.url.query:
            next_url += f"?{request.url.query}"
        return RedirectResponse(
            url=f"/admin/resumee-login?next={quote(next_url, safe='/?=&')}",
            status_code=303,
        )
    return None


def _ensure_admin_or_driver(request: Request):
    if not request.session.get("is_admin") and not request.session.get("is_driver"):
        raise HTTPException(401, "Not authorized")


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _week_range(d: date) -> tuple[date, date]:
    ws = _monday_of(d)
    return ws, ws + timedelta(days=6)


def _dir_code(route_from: str, route_to: str) -> str:
    rf = (route_from or "").strip().lower()
    rt = (route_to or "").strip().lower()
    if rf == "innsbruck" and rt == "kyiv":
        return "IK"
    if rf == "kyiv" and rt == "innsbruck":
        return "KI"
    return "OTHER"


# =======================
# Blacklist helpers (bad_clients)
# =======================
def norm_phone(s: str | None) -> str | None:
    if not s:
        return None
    digits = re.sub(r"\D+", "", str(s))
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    return digits or None


def norm_name(s: str | None) -> str | None:
    if not s:
        return None
    x = str(s).strip().lower()
    x = re.sub(r"\s+", " ", x)
    return x or None


def decorate_passenger_dicts_with_bad_clients(db: Session, items: list[dict]) -> None:
    """
    Mutates items: adds badClient, badReason, badCount, badMatchedBy
    Matching policy:
      - phone match is primary
      - name match ONLY when passenger has no phone
        (and only against bad_clients rows where phone_norm IS NULL)
    """
    if not items:
        return

    phones: list[str] = []
    names: list[str] = []
    id_to_phone: dict[int, str | None] = {}
    id_to_name: dict[int, str | None] = {}

    for it in items:
        pid = it.get("id")
        pn = norm_phone(it.get("phone"))
        nn = norm_name(it.get("fullName"))
        id_to_phone[pid] = pn
        id_to_name[pid] = nn
        if pn:
            phones.append(pn)
        elif nn:
            names.append(nn)

    bad_by_phone = {}
    if phones:
        q = text("""
            SELECT phone_norm, reason, bad_count
            FROM bad_clients
            WHERE phone_norm = ANY(:phones)
        """)
        rows = db.execute(q, {"phones": list(set(phones))}).mappings().all()
        bad_by_phone = {r["phone_norm"]: r for r in rows}

    bad_by_name = {}
    if names:
        qn = text("""
            SELECT name_norm, reason, bad_count, updated_at
            FROM bad_clients
            WHERE phone_norm IS NULL
              AND name_norm = ANY(:names)
            ORDER BY updated_at DESC
        """)
        rows = db.execute(qn, {"names": list(set(names))}).mappings().all()
        for r in rows:
            bad_by_name.setdefault(r["name_norm"], r)

    for it in items:
        pid = it.get("id")
        pn = id_to_phone.get(pid)
        nn = id_to_name.get(pid)

        bc = None
        matched_by = None

        if pn:
            bc = bad_by_phone.get(pn)
            if bc:
                matched_by = "phone"
        else:
            if nn:
                bc = bad_by_name.get(nn)
                if bc:
                    matched_by = "name"

        it["badClient"] = bool(bc)
        it["badReason"] = (bc["reason"] if bc else None)
        it["badCount"] = int(bc["bad_count"]) if bc else 0
        it["badMatchedBy"] = matched_by


# =======================
# Passenger serialization helpers
# =======================
def _passenger_has_manual_override(p: TripPassenger) -> bool:
    return any([
        getattr(p, "manual_passenger_no", None),
        getattr(p, "manual_from_city", None),
        getattr(p, "manual_to_city", None),
        getattr(p, "manual_full_name", None),
        getattr(p, "manual_seat_no", None),
        getattr(p, "manual_phone", None),
        getattr(p, "manual_voucher_raw", None),
    ])


def _passenger_to_api_dict(p: TripPassenger, trip: Trip | None = None) -> dict:
    item = {
        "id": p.id,
        "uid": p.source_uid,
        "tripId": p.trip_id,

        "passengerNo": _effective_text(getattr(p, "manual_passenger_no", None), p.passenger_no),
        "fromCity": _effective_text(getattr(p, "manual_from_city", None), p.from_city),
        "toCity": _effective_text(getattr(p, "manual_to_city", None), p.to_city),
        "fullName": _effective_text(getattr(p, "manual_full_name", None), p.full_name),
        "seatNo": _effective_text(getattr(p, "manual_seat_no", None), p.seat_no),
        "phone": _effective_text(getattr(p, "manual_phone", None), p.phone),
        "voucherRaw": _effective_text(getattr(p, "manual_voucher_raw", None), p.voucher_or_amount_raw),

        "basePassengerNo": p.passenger_no,
        "baseFromCity": p.from_city,
        "baseToCity": p.to_city,
        "baseFullName": p.full_name,
        "baseSeatNo": p.seat_no,
        "basePhone": p.phone,
        "baseVoucherRaw": p.voucher_or_amount_raw,

        "manualPassengerNo": getattr(p, "manual_passenger_no", None),
        "manualFromCity": getattr(p, "manual_from_city", None),
        "manualToCity": getattr(p, "manual_to_city", None),
        "manualFullName": getattr(p, "manual_full_name", None),
        "manualSeatNo": getattr(p, "manual_seat_no", None),
        "manualPhone": getattr(p, "manual_phone", None),
        "manualVoucherRaw": getattr(p, "manual_voucher_raw", None),

        "voucherCode": p.voucher_code,
        "amountDue": float(p.amount_due) if p.amount_due is not None else None,
        "checkedIn": p.checked_in,
        "paid": p.paid,
        "amount": float(p.amount) if p.amount is not None else None,
        "currency": getattr(p, "currency", "EUR"),
        "oebb": bool(getattr(p, "oebb", False)),
        "hasManualOverride": _passenger_has_manual_override(p),
        "manualUpdatedAt": getattr(p, "manual_updated_at", None).isoformat() if getattr(p, "manual_updated_at", None) else None,
        "manualUpdatedBy": getattr(p, "manual_updated_by", None),
    }

    if trip is not None:
        item.update({
            "tripId": trip.id,
            "tripDate": trip.date_time.isoformat() if trip.date_time else None,
            "routeFrom": trip.route_from,
            "routeTo": trip.route_to,
        })

    return item


@app.get("/admin/bookings/test-import", response_class=HTMLResponse)
def admin_booking_test_import_page(request: Request):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    return templates.TemplateResponse(request, "admin/booking_test_import.html", {
        "result": None,
        "form_data": {
            "message_id": "",
            "sender": "",
            "subject": "",
            "received_at": "",
            "body_text": "",
            "allow_update_existing": True,
            "fail_on_parse_errors": False,
            "run_matcher": True,
            "run_sync": True,
            "strict_sync_replace_extra": False,
        },
    })


@app.post("/admin/bookings/test-import", response_class=HTMLResponse)
def admin_booking_test_import_submit(
    request: Request,
    message_id: str = Form(""),
    sender: str = Form(""),
    subject: str = Form(""),
    received_at: str = Form(""),
    body_text: str = Form(""),
    allow_update_existing: str | None = Form(None),
    fail_on_parse_errors: str | None = Form(None),
    run_matcher: str | None = Form(None),
    run_sync: str | None = Form(None),
    strict_sync_replace_extra: str | None = Form(None),
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    received_at_dt = None
    received_at = (received_at or "").strip()
    if received_at:
        try:
            received_at_dt = datetime.fromisoformat(received_at)
        except Exception:
            received_at_dt = None

    form_data = {
        "message_id": message_id,
        "sender": sender,
        "subject": subject,
        "received_at": received_at,
        "body_text": body_text,
        "allow_update_existing": bool(allow_update_existing),
        "fail_on_parse_errors": bool(fail_on_parse_errors),
        "run_matcher": bool(run_matcher),
        "run_sync": bool(run_sync),
        "strict_sync_replace_extra": bool(strict_sync_replace_extra),
    }

    result = import_booking_email(
        db,
        ImportEmailPayload(
            message_id=(message_id or "").strip(),
            sender=(sender or "").strip() or None,
            subject=(subject or "").strip() or None,
            received_at=received_at_dt,
            body_text=body_text or "",
            body_html=None,
        ),
        allow_update_existing=bool(allow_update_existing),
        fail_on_parse_errors=bool(fail_on_parse_errors),
        run_matcher=bool(run_matcher),
        run_sync=bool(run_sync),
        strict_sync_replace_extra=bool(strict_sync_replace_extra),
    )

    return templates.TemplateResponse(request, "admin/booking_test_import.html", {
        "result": result,
        "form_data": form_data,
    })


# =======================
# Admin login
# =======================
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    next_url = request.query_params.get("next", "/trips")
    if not next_url.startswith("/"):
        next_url = "/trips"

    return HTMLResponse(f"""
    <html><body style="font-family:system-ui;padding:24px">
      <h3>Admin login</h3>
      <form method="post" action="/admin/login">
        <input type="hidden" name="next" value="{next_url}" />
        <input type="password" name="password" placeholder="ADMIN_PASSWORD"
               style="padding:10px;border:1px solid #ccc;border-radius:10px" />
        <button type="submit"
                style="padding:10px 14px;border-radius:10px;border:1px solid #333;background:#111;color:#fff;margin-left:8px">
          Login
        </button>
      </form>
    </body></html>
    """)


@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(""), next: str = Form("/trips")):
    if not ADMIN_PASSWORD:
        raise HTTPException(500, "Missing ADMIN_PASSWORD env var")
    if password.strip() != ADMIN_PASSWORD:
        raise HTTPException(401, "Bad password")

    request.session["is_admin"] = True

    if not next or not next.startswith("/"):
        next = "/trips"

    return RedirectResponse(url=next, status_code=303)


@app.post("/admin/logout")
def admin_logout(request: Request):
    request.session.pop("is_admin", None)
    request.session.pop("is_resumee", None)
    return RedirectResponse(url="/", status_code=303)


# =======================
# Driver login
# =======================
@app.get("/drivers/login", response_class=HTMLResponse)
def drivers_login_page(_: Request):
    return HTMLResponse("""
    <html><body style="font-family:system-ui;padding:24px">
      <h3>Driver login</h3>
      <form method="post" action="/drivers/login">
        <input type="password" name="password" placeholder="DRIVER_PASSWORD"
               style="padding:10px;border:1px solid #ccc;border-radius:10px" />
        <button type="submit"
                style="padding:10px 14px;border-radius:10px;border:1px solid #333;background:#111;color:#fff;margin-left:8px">
          Login
        </button>
      </form>
    </body></html>
    """)


@app.post("/drivers/login")
def drivers_login(request: Request, password: str = Form("")):
    if not DRIVER_PASSWORD:
        raise HTTPException(500, "Missing DRIVER_PASSWORD env var")
    if password.strip() != DRIVER_PASSWORD:
        raise HTTPException(401, "Bad password")

    request.session["is_driver"] = True
    return RedirectResponse(url="/drivers", status_code=303)


@app.post("/drivers/logout")
def drivers_logout(request: Request):
    request.session.pop("is_driver", None)
    return RedirectResponse(url="/", status_code=303)


# =======================
# Resumee login (second password)
# =======================
@app.get("/admin/resumee-login", response_class=HTMLResponse)
def admin_resumee_login_page(request: Request):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    next_url = request.query_params.get("next", "/admin/resumee")
    if not next_url.startswith("/"):
        next_url = "/admin/resumee"

    err = request.query_params.get("err", "")

    hint = ""
    if not ADMIN_PASSWORD1:
        hint = "<div style='margin-top:10px;color:#b91c1c;font-weight:700'>Липсва ENV: ADMIN_PASSWORD1 (Render → Environment)</div>"
    elif err == "1":
        hint = "<div style='margin-top:10px;color:#b91c1c;font-weight:700'>Грешна парола.</div>"

    return HTMLResponse(f"""
    <html><body style="font-family:system-ui;padding:24px">
      <h3>Resumee login</h3>
      <div style="color:#64748b;margin-top:6px">Тази страница е защитена с ADMIN_PASSWORD1.</div>
      {hint}
      <form method="post" action="/admin/resumee-login" style="margin-top:14px">
        <input type="hidden" name="next" value="{next_url}" />
        <input type="password" name="password" placeholder="ADMIN_PASSWORD1"
               style="padding:10px;border:1px solid #ccc;border-radius:10px" />
        <button type="submit"
                style="padding:10px 14px;border-radius:10px;border:1px solid #333;background:#111;color:#fff;margin-left:8px">
          Login
        </button>
      </form>
      <div style="margin-top:14px;">
        <a href="/trips" style="color:#111;text-decoration:none;font-weight:700">← към Trips</a>
      </div>
    </body></html>
    """)


@app.post("/admin/resumee-login")
def admin_resumee_login(request: Request, password: str = Form(""), next: str = Form("/admin/resumee")):
    _ensure_admin(request)

    if not ADMIN_PASSWORD1:
        raise HTTPException(500, "Missing ADMIN_PASSWORD1 env var (Render → Environment)")

    if password.strip() != ADMIN_PASSWORD1:
        if not next or not next.startswith("/"):
            next = "/admin/resumee"
        return RedirectResponse(
            url=f"/admin/resumee-login?next={quote(next, safe='/?=&')}&err=1",
            status_code=303,
        )

    request.session["is_resumee"] = True

    if not next or not next.startswith("/"):
        next = "/admin/resumee"

    return RedirectResponse(url=next, status_code=303)


@app.post("/admin/resumee-logout")
def admin_resumee_logout(request: Request):
    request.session.pop("is_resumee", None)
    return RedirectResponse(url="/trips", status_code=303)


# =======================
# Admin resumee
# =======================
@app.get("/admin/resumee", response_class=HTMLResponse)
def admin_resumee_page(request: Request, db: Session = Depends(get_db)):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    r2 = _ensure_resumee_or_redirect(request)
    if r2:
        return r2

    def _bucket():
        return {
            "pax": 0,
            "trips": 0,
            "forecast": {"EUR": 0.0, "UAH": 0.0},
            "real": {"EUR": 0.0, "UAH": 0.0},
        }

    rows = (
        db.query(
            Trip.id.label("trip_id"),
            Trip.date_time.label("dt"),
            Trip.route_from.label("rf"),
            Trip.route_to.label("rt"),

            func.count(TripPassenger.id).label("pax"),

            func.coalesce(
                func.sum(
                    case(
                        (TripPassenger.currency == "EUR", TripPassenger.amount_due),
                        else_=0,
                    )
                ),
                0,
            ).label("forecast_eur"),

            func.coalesce(
                func.sum(
                    case(
                        (TripPassenger.currency == "UAH", TripPassenger.amount_due),
                        else_=0,
                    )
                ),
                0,
            ).label("forecast_uah"),

            func.coalesce(
                func.sum(
                    case(
                        (((TripPassenger.paid == True) & (TripPassenger.currency == "EUR")), TripPassenger.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("real_eur"),

            func.coalesce(
                func.sum(
                    case(
                        (((TripPassenger.paid == True) & (TripPassenger.currency == "UAH")), TripPassenger.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("real_uah"),
        )
        .outerjoin(TripPassenger, TripPassenger.trip_id == Trip.id)
        .group_by(Trip.id)
        .order_by(Trip.date_time.asc())
        .all()
    )

    months = {}

    for r0 in rows:
        if not r0.dt:
            continue

        d = r0.dt.date()
        month_key = f"{d.year:04d}-{d.month:02d}"
        month_label = d.strftime("%B %Y")
        ws, we = _week_range(d)

        dirc = _dir_code(r0.rf, r0.rt)
        if dirc not in ("IK", "KI"):
            continue

        if month_key not in months:
            months[month_key] = {
                "label": month_label,
                "weeks": {},
                "totals": {
                    "IK": _bucket(),
                    "KI": _bucket(),
                },
            }

        wk_key = (ws, we)
        if wk_key not in months[month_key]["weeks"]:
            months[month_key]["weeks"][wk_key] = {
                "IK": _bucket(),
                "KI": _bucket(),
            }

        pax = int(r0.pax or 0)
        f_eur = float(r0.forecast_eur or 0)
        f_uah = float(r0.forecast_uah or 0)
        a_eur = float(r0.real_eur or 0)
        a_uah = float(r0.real_uah or 0)

        months[month_key]["weeks"][wk_key][dirc]["trips"] += 1
        months[month_key]["weeks"][wk_key][dirc]["pax"] += pax
        months[month_key]["weeks"][wk_key][dirc]["forecast"]["EUR"] += f_eur
        months[month_key]["weeks"][wk_key][dirc]["forecast"]["UAH"] += f_uah
        months[month_key]["weeks"][wk_key][dirc]["real"]["EUR"] += a_eur
        months[month_key]["weeks"][wk_key][dirc]["real"]["UAH"] += a_uah

        months[month_key]["totals"][dirc]["trips"] += 1
        months[month_key]["totals"][dirc]["pax"] += pax
        months[month_key]["totals"][dirc]["forecast"]["EUR"] += f_eur
        months[month_key]["totals"][dirc]["forecast"]["UAH"] += f_uah
        months[month_key]["totals"][dirc]["real"]["EUR"] += a_eur
        months[month_key]["totals"][dirc]["real"]["UAH"] += a_uah

    month_items = []
    for mk in sorted(months.keys()):
        m = months[mk]
        week_items = []
        for (ws, we) in sorted(m["weeks"].keys()):
            week_items.append({
                "ws": ws,
                "we": we,
                "IK": m["weeks"][(ws, we)]["IK"],
                "KI": m["weeks"][(ws, we)]["KI"],
            })
        month_items.append({
            "key": mk,
            "label": m["label"],
            "weeks": week_items,
            "totals": m["totals"],
        })

    return templates.TemplateResponse(request, "resumee.html", {
        "months": month_items,
    })


# =======================
# Admin run-sync
# =======================
def _run_sync_job(force: bool):
    try:
        from app.scripts.sync_drive_xlsx_oauth import run_sync
    except Exception as e:
        raise RuntimeError(f"Sync import failed: {e}")
    run_sync(force=force)


@app.post("/admin/run-sync")
def admin_run_sync(request: Request, background: BackgroundTasks, force: int = 0):
    _ensure_admin(request)

    try:
        background.add_task(_run_sync_job, bool(force))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "started": True, "force": bool(force)}


# =======================
# UI routes
# =======================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "landing.html", {})


@app.get("/drivers", response_class=HTMLResponse)
def drivers_page(request: Request, db: Session = Depends(get_db)):
    _ensure_driver(request)

    trips = (
        db.query(Trip)
        .filter(Trip.is_finalized == True)
        .order_by(Trip.date_time.asc())
        .all()
    )

    trip_ids = [t.id for t in trips if getattr(t, "id", None) is not None]
    totals_by_trip: dict[int, int] = {}

    if trip_ids:
        rows = (
            db.query(TripPassenger.trip_id, func.count(TripPassenger.id))
            .filter(TripPassenger.trip_id.in_(trip_ids))
            .group_by(TripPassenger.trip_id)
            .all()
        )
        totals_by_trip = {int(tid): int(cnt) for tid, cnt in rows}

    for t in trips:
        t.total_passengers = int(totals_by_trip.get(int(t.id), 0))

    return templates.TemplateResponse(request, "drivers_trips.html", {
        "trips": trips,
    })


@app.get("/drivers/trips/{trip_id}", response_class=HTMLResponse)
def driver_trip_detail(request: Request, trip_id: int, db: Session = Depends(get_db)):
    _ensure_driver(request)

    trip = crud.get_trip(db, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    if not trip.is_finalized:
        raise HTTPException(403, "Trip is not released (no Freigabe)")

    return templates.TemplateResponse(request, "driver_trip_detail.html", {
        "trip": trip,
    })


@app.get("/trips", response_class=HTMLResponse)
def trips_page(request: Request, db: Session = Depends(get_db)):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    trips = crud.list_trips(db)

    trip_ids = [t.id for t in trips if getattr(t, "id", None) is not None]
    totals_by_trip: dict[int, int] = {}

    if trip_ids:
        rows = (
            db.query(TripPassenger.trip_id, func.count(TripPassenger.id))
            .filter(TripPassenger.trip_id.in_(trip_ids))
            .group_by(TripPassenger.trip_id)
            .all()
        )
        totals_by_trip = {int(tid): int(cnt) for tid, cnt in rows}

    for t in trips:
        t.total_passengers = int(totals_by_trip.get(int(t.id), 0))

    return templates.TemplateResponse(request, "trips.html", {
        "trips": trips,
    })


@app.get("/trips/{trip_id}", response_class=HTMLResponse)
def trip_detail(request: Request, trip_id: int, db: Session = Depends(get_db)):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    trip = crud.get_trip(db, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    return templates.TemplateResponse(request, "trip_detail.html", {
        "trip": trip,
    })


# =======================
# Trips CRUD (admin-only)
# =======================
@app.post("/trips")
def create_trip(
    request: Request,
    route_from: str = Form(None),
    route_to: str = Form(None),
    date_time: str = Form(None),
    note: str = Form(None),
    db: Session = Depends(get_db),
):
    _ensure_admin(request)

    dt = None
    if date_time:
        dt = datetime.fromisoformat(date_time)
    crud.create_trip(db, route_from=route_from, route_to=route_to, date_time=dt, note=note)
    return RedirectResponse(url="/trips", status_code=303)


@app.post("/trips/{trip_id}/delete")
def delete_trip(request: Request, trip_id: int, db: Session = Depends(get_db)):
    _ensure_admin(request)

    ok = crud.delete_trip(db, trip_id)
    if not ok:
        raise HTTPException(404, "Trip not found")
    return RedirectResponse(url="/trips", status_code=303)


# =======================
# API: summary (admin or driver; driver only if finalized)
# Uses effective from/to (manual override if present)
# =======================
@app.get("/api/trips/{trip_id}/summary")
def api_trip_summary(trip_id: int, request: Request, db: Session = Depends(get_db)):
    is_admin = bool(request.session.get("is_admin"))
    is_driver = bool(request.session.get("is_driver"))

    if not is_admin and not is_driver:
        raise HTTPException(401, "Not authorized")

    trip = crud.get_trip(db, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")

    if is_driver and not is_admin and not trip.is_finalized:
        raise HTTPException(403, "Trip not released")

    effective_from = _effective_sql_text(TripPassenger.manual_from_city, TripPassenger.from_city)
    effective_to = _effective_sql_text(TripPassenger.manual_to_city, TripPassenger.to_city)

    from_rows = (
        db.query(
            effective_from.label("city"),
            func.count(TripPassenger.id).label("count"),
        )
        .filter(TripPassenger.trip_id == trip_id)
        .group_by(effective_from)
        .all()
    )

    to_rows = (
        db.query(
            effective_to.label("city"),
            func.count(TripPassenger.id).label("count"),
        )
        .filter(TripPassenger.trip_id == trip_id)
        .group_by(effective_to)
        .all()
    )

    from_counts = [
        {"city": (c or ""), "count": int(n)}
        for c, n in from_rows
        if (c or "").strip() != ""
    ]

    to_counts = [
        {"city": (c or ""), "count": int(n)}
        for c, n in to_rows
        if (c or "").strip() != ""
    ]

    total = (
        db.query(func.count(TripPassenger.id))
        .filter(TripPassenger.trip_id == trip_id)
        .scalar()
        or 0
    )

    return {
        "tripId": trip_id,
        "total": int(total),
        "from": from_counts,
        "to": to_counts,
    }


# =======================
# API: passengers list (admin or driver; driver only if finalized)
# Uses effective/manual values
# =======================
@app.get("/api/trips/{trip_id}/passengers")
def api_list_passengers(trip_id: int, request: Request, db: Session = Depends(get_db)):
    is_admin = bool(request.session.get("is_admin"))
    is_driver = bool(request.session.get("is_driver"))

    if not is_admin and not is_driver:
        raise HTTPException(401, "Not authorized")

    trip = crud.get_trip(db, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")

    if is_driver and not is_admin and not trip.is_finalized:
        raise HTTPException(403, "Trip not released")

    passengers = crud.list_passengers(db, trip_id)
    passengers = sorted(
        passengers,
        key=lambda p: (
            _safe_int_passenger_no(_effective_text(getattr(p, "manual_passenger_no", None), p.passenger_no)),
            p.id,
        ),
    )

    out = [_passenger_to_api_dict(p) for p in passengers]
    decorate_passenger_dicts_with_bad_clients(db, out)
    return JSONResponse(out)


# =======================
# API: passenger search (admin-only)
# =======================
@app.get("/api/passengers/search")
def api_search_passengers(
    request: Request,
    q: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
):
    _ensure_admin(request)

    q = (q or "").strip()
    if not q:
        return {"ok": True, "items": []}

    limit = max(1, min(int(limit or 100), 200))
    pattern = f"%{q}%"

    effective_passenger_no = _effective_sql_text(TripPassenger.manual_passenger_no, TripPassenger.passenger_no)
    effective_from = _effective_sql_text(TripPassenger.manual_from_city, TripPassenger.from_city)
    effective_to = _effective_sql_text(TripPassenger.manual_to_city, TripPassenger.to_city)
    effective_full_name = _effective_sql_text(TripPassenger.manual_full_name, TripPassenger.full_name)
    effective_seat_no = _effective_sql_text(TripPassenger.manual_seat_no, TripPassenger.seat_no)
    effective_phone = _effective_sql_text(TripPassenger.manual_phone, TripPassenger.phone)
    effective_voucher = _effective_sql_text(TripPassenger.manual_voucher_raw, TripPassenger.voucher_or_amount_raw)

    rows = (
        db.query(TripPassenger, Trip)
        .join(Trip, Trip.id == TripPassenger.trip_id)
        .filter(
            or_(
                TripPassenger.source_uid.ilike(pattern),
                effective_passenger_no.ilike(pattern),
                effective_from.ilike(pattern),
                effective_to.ilike(pattern),
                effective_full_name.ilike(pattern),
                effective_seat_no.ilike(pattern),
                effective_phone.ilike(pattern),
                effective_voucher.ilike(pattern),
            )
        )
        .order_by(Trip.date_time.desc(), TripPassenger.id.desc())
        .limit(limit)
        .all()
    )

    items = []
    for p, trip in rows:
        item = _passenger_to_api_dict(p, trip)
        items.append(item)

    decorate_passenger_dicts_with_bad_clients(db, items)
    return {"ok": True, "items": items}


# =======================
# API: import passengers (admin-only)
# =======================
@app.post("/api/trips/{trip_id}/passengers/import")
async def api_import(trip_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    _ensure_admin(request)

    trip = crud.get_trip(db, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")

    content = await file.read()
    rows = parse_xlsx(content)

    inserted = crud.import_passengers(db, trip_id, rows, replace=True)
    return {"ok": True, "inserted": int(inserted)}


# =======================
# API: patch passenger (admin or driver with whitelist + finalized)
# =======================
@app.patch("/api/passengers/{passenger_id}")
async def api_patch_passenger(passenger_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    is_admin = bool(request.session.get("is_admin"))
    is_driver = bool(request.session.get("is_driver"))

    if not is_admin and not is_driver:
        raise HTTPException(401, "Not authorized")

    p0 = db.query(TripPassenger).filter(TripPassenger.id == passenger_id).first()
    if not p0:
        raise HTTPException(404, "Passenger not found")

    trip = db.query(Trip).filter(Trip.id == p0.trip_id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")

    if is_driver and not is_admin and not trip.is_finalized:
        raise HTTPException(403, "Trip not released")

    if is_driver and not is_admin:
        allowed = {"checkedIn", "paid", "amount", "currency"}
        bad_keys = set(payload.keys()) - allowed
        if bad_keys:
            raise HTTPException(403, f"Driver cannot modify: {sorted(bad_keys)}")

    p = crud.patch_passenger(
        db,
        passenger_id,
        checked_in=payload.get("checkedIn"),
        paid=payload.get("paid"),
        amount=payload.get("amount"),
        currency=payload.get("currency"),
        oebb=payload.get("oebb"),
    )
    if not p:
        raise HTTPException(404, "Passenger not found")

    return {"ok": True}


# =======================
# API: manual override patch (admin-only)
# Saves from/to/fullName/phone/voucherRaw at once
# =======================
@app.patch("/api/passengers/{passenger_id}/manual")
async def api_patch_passenger_manual(
    passenger_id: int,
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
):
    _ensure_admin(request)

    p = db.query(TripPassenger).filter(TripPassenger.id == passenger_id).first()
    if not p:
        raise HTTPException(404, "Passenger not found")

    trip = db.query(Trip).filter(Trip.id == p.trip_id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")

    if trip.date_time and trip.date_time.date() < _today_vienna():
        raise HTTPException(403, "Manual edit is allowed only for today and future trips")

    if "fromCity" in payload:
        p.manual_from_city = _manual_to_none(payload.get("fromCity"))

    if "toCity" in payload:
        p.manual_to_city = _manual_to_none(payload.get("toCity"))

    if "fullName" in payload:
        p.manual_full_name = _manual_to_none(payload.get("fullName"))

    if "phone" in payload:
        p.manual_phone = _manual_to_none(payload.get("phone"))

    if "seatNo" in payload:
        p.manual_seat_no = _manual_to_none(payload.get("seatNo"))

    if "voucherRaw" in payload:
        p.manual_voucher_raw = _manual_to_none(payload.get("voucherRaw"))

    p.manual_updated_at = datetime.utcnow()
    p.manual_updated_by = "admin"

    db.commit()
    db.refresh(p)

    trip = db.query(Trip).filter(Trip.id == p.trip_id).first()
    item = _passenger_to_api_dict(p, trip)
    decorate_passenger_dicts_with_bad_clients(db, [item])

    return {"ok": True, "item": item}


# =======================
# API: clear manual override (admin-only)
# =======================
@app.delete("/api/passengers/{passenger_id}/manual")
def api_clear_passenger_manual(
    passenger_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _ensure_admin(request)

    p = db.query(TripPassenger).filter(TripPassenger.id == passenger_id).first()
    if not p:
        raise HTTPException(404, "Passenger not found")

    trip = db.query(Trip).filter(Trip.id == p.trip_id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")

    if trip.date_time and trip.date_time.date() < _today_vienna():
        raise HTTPException(403, "Manual reset is allowed only for today and future trips")

    p.manual_passenger_no = None
    p.manual_from_city = None
    p.manual_to_city = None
    p.manual_full_name = None
    p.manual_seat_no = None
    p.manual_phone = None
    p.manual_voucher_raw = None
    p.manual_updated_at = datetime.utcnow()
    p.manual_updated_by = "admin-reset"

    db.commit()
    return {"ok": True}


# =======================
# API: bulk update (admin-only)
# =======================
@app.post("/api/trips/{trip_id}/passengers/bulk_update")
async def api_bulk_update(trip_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    _ensure_admin(request)

    updates = payload.get("updates", [])
    if not isinstance(updates, list):
        raise HTTPException(400, "updates must be a list")

    ids = [u.get("id") for u in updates if u.get("id")]
    if not ids:
        return {"ok": True, "updated": 0}

    passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.trip_id == trip_id, TripPassenger.id.in_(ids))
        .all()
    )
    by_id = {p.id: p for p in passengers}

    updated = 0
    for u in updates:
        pid = u.get("id")
        p = by_id.get(pid)
        if not p:
            continue

        if "checkedIn" in u:
            p.checked_in = bool(u["checkedIn"])
        if "paid" in u:
            p.paid = bool(u["paid"])
        if "amount" in u:
            a = u["amount"]
            if a is None or a == "":
                p.amount = None
            else:
                p.amount = float(a)
        if "currency" in u:
            p.currency = str(u["currency"] or "EUR").upper()

        updated += 1

    db.commit()
    return {"ok": True, "updated": updated}


# =======================
# API: finalize (Freigabe) admin-only
# =======================
@app.post("/api/trips/{trip_id}/finalize")
def api_finalize_trip(trip_id: int, request: Request, db: Session = Depends(get_db)):
    _ensure_admin(request)

    trip = crud.get_trip(db, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")

    trip.is_finalized = True
    trip.finalized_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "finalizedAt": trip.finalized_at.isoformat()}


# =======================
# API: renumber (admin-only)
# =======================
@app.post("/api/trips/{trip_id}/passengers/renumber")
def api_renumber(trip_id: int, request: Request, db: Session = Depends(get_db)):
    _ensure_admin(request)

    passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.trip_id == trip_id)
        .all()
    )

    passengers.sort(
        key=lambda p: (
            _safe_int_passenger_no(_effective_text(getattr(p, "manual_passenger_no", None), p.passenger_no)),
            p.id,
        )
    )

    for i, p in enumerate(passengers, start=1):
        p.passenger_no = str(i)

    db.commit()
    return {"ok": True, "count": len(passengers)}


# =======================
# API: blacklist (admin-only)
# =======================
@app.post("/api/passengers/{passenger_id}/blacklist")
def api_blacklist_passenger(passenger_id: int, request: Request, payload: dict | None = None, db: Session = Depends(get_db)):
    _ensure_admin(request)

    payload = payload or {}
    reason = str(payload.get("reason") or "no-show").strip()

    p = db.query(TripPassenger).filter(TripPassenger.id == passenger_id).first()
    if not p:
        raise HTTPException(404, "Passenger not found")

    phone_for_match = _effective_text(getattr(p, "manual_phone", None), getattr(p, "phone", None))
    name_for_match = _effective_text(getattr(p, "manual_full_name", None), getattr(p, "full_name", None))

    pn = norm_phone(phone_for_match)
    nn = norm_name(name_for_match)

    if not pn and not nn:
        raise HTTPException(400, "Passenger няма телефон/име за blacklist")

    if pn:
        q = text("""
            INSERT INTO bad_clients (phone_norm, name_norm, reason, bad_count, created_at, updated_at)
            VALUES (:pn, :nn, :reason, 1, now(), now())
            ON CONFLICT (phone_norm)
            DO UPDATE SET
              bad_count = bad_clients.bad_count + 1,
              reason = COALESCE(EXCLUDED.reason, bad_clients.reason),
              name_norm = COALESCE(EXCLUDED.name_norm, bad_clients.name_norm),
              updated_at = now()
            RETURNING bad_count;
        """)
        row = db.execute(q, {"pn": pn, "nn": nn, "reason": reason}).first()
        db.commit()
        return {"ok": True, "matchedBy": "phone", "badCount": int(row[0])}

    qsel = text("""
        SELECT id
        FROM bad_clients
        WHERE phone_norm IS NULL AND name_norm = :nn
        ORDER BY updated_at DESC
        LIMIT 1
    """)
    existing = db.execute(qsel, {"nn": nn}).mappings().first()

    if existing:
        qup = text("""
            UPDATE bad_clients
            SET bad_count = bad_count + 1,
                reason = COALESCE(:reason, reason),
                updated_at = now()
            WHERE id = :id
            RETURNING bad_count
        """)
        row = db.execute(qup, {"id": existing["id"], "reason": reason}).first()
        db.commit()
        return {"ok": True, "matchedBy": "name", "badCount": int(row[0])}

    qins = text("""
        INSERT INTO bad_clients (phone_norm, name_norm, reason, bad_count, created_at, updated_at)
        VALUES (NULL, :nn, :reason, 1, now(), now())
        RETURNING bad_count
    """)
    row = db.execute(qins, {"nn": nn, "reason": reason}).first()
    db.commit()
    return {"ok": True, "matchedBy": "name", "badCount": int(row[0])}


@app.delete("/api/passengers/{passenger_id}/blacklist")
def api_unblacklist_passenger(passenger_id: int, request: Request, db: Session = Depends(get_db)):
    _ensure_admin(request)

    p = db.query(TripPassenger).filter(TripPassenger.id == passenger_id).first()
    if not p:
        raise HTTPException(404, "Passenger not found")

    phone_for_match = _effective_text(getattr(p, "manual_phone", None), getattr(p, "phone", None))
    name_for_match = _effective_text(getattr(p, "manual_full_name", None), getattr(p, "full_name", None))

    pn = norm_phone(phone_for_match)
    nn = norm_name(name_for_match)

    if pn:
        q = text("DELETE FROM bad_clients WHERE phone_norm = :pn")
        res = db.execute(q, {"pn": pn})
        db.commit()
        removed = bool(getattr(res, "rowcount", 0) or 0)
        return {"ok": True, "removed": removed, "by": "phone"}

    if nn:
        qsel = text("""
            SELECT id
            FROM bad_clients
            WHERE phone_norm IS NULL AND name_norm = :nn
            ORDER BY updated_at DESC
            LIMIT 1
        """)
        row = db.execute(qsel, {"nn": nn}).mappings().first()
        if not row:
            return {"ok": True, "removed": False, "by": "name"}

        qdel = text("DELETE FROM bad_clients WHERE id = :id")
        res = db.execute(qdel, {"id": row["id"]})
        db.commit()
        removed = bool(getattr(res, "rowcount", 0) or 0)
        return {"ok": True, "removed": removed, "by": "name"}

    return {"ok": True, "removed": False, "by": None}


# =======================
# API: bad clients list (admin-only)
# =======================
@app.get("/api/bad-clients")
def api_list_bad_clients(
    request: Request,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    _ensure_admin(request)

    limit = max(1, min(int(limit or 200), 500))
    offset = max(0, int(offset or 0))

    qtxt = (q or "").strip().lower()
    params = {"limit": limit, "offset": offset}

    if qtxt:
        params["q"] = f"%{qtxt}%"
        sql = text("""
            SELECT id, phone_norm, name_norm, reason, bad_count, created_at, updated_at
            FROM bad_clients
            WHERE COALESCE(phone_norm,'') ILIKE :q
               OR COALESCE(name_norm,'') ILIKE :q
               OR COALESCE(reason,'') ILIKE :q
            ORDER BY updated_at DESC
            LIMIT :limit OFFSET :offset
        """)
        rows = db.execute(sql, params).mappings().all()

        cnt_sql = text("""
            SELECT COUNT(*)
            FROM bad_clients
            WHERE COALESCE(phone_norm,'') ILIKE :q
               OR COALESCE(name_norm,'') ILIKE :q
               OR COALESCE(reason,'') ILIKE :q
        """)
        total = int(db.execute(cnt_sql, {"q": params["q"]}).scalar() or 0)
    else:
        sql = text("""
            SELECT id, phone_norm, name_norm, reason, bad_count, created_at, updated_at
            FROM bad_clients
            ORDER BY updated_at DESC
            LIMIT :limit OFFSET :offset
        """)
        rows = db.execute(sql, params).mappings().all()
        total = int(db.execute(text("SELECT COUNT(*) FROM bad_clients")).scalar() or 0)

    items = []
    for r in rows:
        items.append({
            "id": int(r["id"]),
            "phoneNorm": r["phone_norm"],
            "nameNorm": r["name_norm"],
            "reason": r["reason"],
            "badCount": int(r["bad_count"] or 0),
            "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
            "updatedAt": r["updated_at"].isoformat() if r["updated_at"] else None,
        })

    return {"ok": True, "total": total, "limit": limit, "offset": offset, "items": items}
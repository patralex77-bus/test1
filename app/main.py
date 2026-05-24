
import os
import re
import io
import json
import uuid
import qrcode
import hmac
import hashlib
import qrcode.image.svg
from datetime import datetime, date, timedelta, time
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel

from decimal import Decimal, InvalidOperation

from fastapi import FastAPI, Request, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.booking_importer import ImportEmailPayload, import_booking_email
from app.services.booking_matcher import rematch_booking_to_trip
from app.services.booking_sync import sync_booking_to_trip_passengers_by_id
from app.services.booking_import_runner import run_booking_import

from app.i18n import TRANSLATIONS

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF, renderSVG 



from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from sqlalchemy.orm import Session
from sqlalchemy import func, text, case, or_, cast, String


from .db import Base, engine, get_db
from . import crud
from .excel_import import parse_xlsx
from .models import (
    TripPassenger,
    Trip,
    Booking,
    BookingSeat,
    BookingTicketLine,
    BookingCancellation,
    IncomingEmail,
    PaymentProof,
)

Base.metadata.create_all(bind=engine)

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

UPLOADS_DIR = APP_DIR / "static" / "uploads" / "payment_proofs"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

DRIVER_MANIFESTS_DIR = APP_DIR / "data" / "driver_manifests"
DRIVER_MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_PAYMENT_PROOF_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}

app = FastAPI()

# ---- Sessions + Passwords ----
SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me")
ADMIN_PASSWORD = "1234"
DRIVER_PASSWORD = "1234"
ADMIN_PASSWORD1 = os.environ.get("ADMIN_PASSWORD1", "").strip()

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


SUPPORTED_LANGS = {"uk", "en"}
DEFAULT_LANG = "uk"


def _normalize_lang(value: str | None) -> str:
    lang = (value or "").strip().lower()
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def _get_lang(request: Request | None = None) -> str:
    if request is None:
        return DEFAULT_LANG

    try:
        return _normalize_lang(request.session.get("lang"))
    except Exception:
        return DEFAULT_LANG


def _set_lang(request: Request, lang: str | None) -> None:
    request.session["lang"] = _normalize_lang(lang)


def _t(request: Request | None, key: str, default: str | None = None, **kwargs) -> str:
    lang = _get_lang(request)
    text = (
        TRANSLATIONS.get(lang, {}).get(key)
        or TRANSLATIONS.get(DEFAULT_LANG, {}).get(key)
        or default
        or key
    )

    if kwargs:
        try:
            text = str(text).format(**kwargs)
        except Exception:
            pass

    return text


templates.env.globals["t"] = _t
templates.env.globals["get_lang"] = _get_lang
templates.env.globals["current_lang"] = _get_lang

SEAT_LAYOUT = [
    [49, 45, 41, 37, 33, 29, 25, 23, 21, 17, 13, 9, 5, 1],
    [50, 46, 42, 38, 34, 30, 26, 24, 22, 18, 14, 10, 6, 2],
    [51, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [52, 47, 43, 39, 35, 31, 27, None, None, 19, 15, 11, 7, 3],
    [53, 48, 44, 40, 36, 32, 28, None, None, 20, 16, 12, 8, 4],
]



STOP_ADDRESS_BOOK = {
    "kyiv": {
        "label": "Київ",
        "address": 'Автовокзал "Київ", вул. Симона Петлюри 32',
    },
    "zhytomyr": {
        "label": "Житомир",
        "address": 'Автовокзал "Житомир" (Житомирська АС-1)',
    },
    "rivne": {
        "label": "Рівне",
        "address": "вулиця Київська, 40, Рівне, Рівненська область, 33000",
    },
    "lviv": {
        "label": "Львів",
        "address": "вулиця Стрийська, 109, Львів, Львівська область, 79000",
    },
    "wien": {
        "label": "Вiдень",
        "address": "Südtiroler Platz, Busbahnhof Wiedner Gürtel, Platform B5",
    },
    "stpolten": {
        "label": "Ст. Пьоелтен",
        "address": "St.Pölten Mariazeller Straße/P+R Süd",
    },
    "linz": {
        "label": "Лінц",
        "address": "Industriezeile 84",
    },
    "wels": {
        "label": "Вельс",
        "address": "Eisenfeldstrasse 9",
    },
    "salzburg": {
        "label": "Зальцбург",
        "address": "P&R Süd Salzburg",
    },
    "innsbruck": {
        "label": "Інсбрук",
        "address": "Olympia World Innsbruck",
    },
    "bruck": {
        "label": "Брук ан дер Мур",
        "address": "8600 Брук-ан-дер-Мур, Австрія",
    },
    "graz": {
        "label": "Грац",
        "address": "P+R Webling Graz",
    },
    "klagenfurt": {
        "label": "Клагенфурт",
        "address": "Klagenfurt Hbf (Busbahnhof)",
    },
    "villach": {
        "label": "Філлах",
        "address": "Villach Hbf (Busbahnhof)",
    },
}



def _build_qr_svg_bytes(qr_text: str, size: int = 220) -> bytes:
    qr = QrCodeWidget(qr_text)
    bounds = qr.getBounds()
    x1, y1, x2, y2 = bounds
    width = x2 - x1
    height = y2 - y1

    drawing = Drawing(
        size,
        size,
        transform=[size / width, 0, 0, size / height, 0, 0],
    )
    drawing.add(qr)

    svg = renderSVG.drawToString(drawing)
    if isinstance(svg, str):
        return svg.encode("utf-8")
    return svg


TICKET_QR_SECRET = (
    os.getenv("TICKET_QR_SECRET")
    or os.getenv("SECRET_KEY")
    or "change-me-ticket-secret"
)


def _ticket_payload_signable_dict(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k != "sig"}


def _sign_ticket_payload(payload: dict) -> str:
    raw = json.dumps(
        _ticket_payload_signable_dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hmac.new(
        TICKET_QR_SECRET.encode("utf-8"),
        raw,
        hashlib.sha256,
    ).hexdigest()


def _verify_ticket_payload_signature(payload: dict) -> bool:
    sig = (payload or {}).get("sig")
    if not sig:
        return False

    expected = _sign_ticket_payload(payload)
    return hmac.compare_digest(str(sig), str(expected))


# =======================
# Backend route за admin seat change
# =======================

class AdminAssignSeatPayload(BaseModel):
    seat_no: str


def _dashboard_virtual_passenger_id(booking_id: int, seat_index: int) -> int:
    """
    Отрицателен pseudo passenger id за dashboard ред, когато има BookingSeat,
    но липсва реален TripPassenger row.

    Пример: booking_id=123, seat_index=1 -> -123002
    """
    return -((int(booking_id) * 1000) + int(seat_index) + 1)


def _decode_dashboard_virtual_passenger_id(value: int) -> tuple[int, int] | None:
    """
    Връща (booking_id, seat_index) за отрицателен pseudo id.
    """
    try:
        raw = abs(int(value))
    except Exception:
        return None

    if raw < 1001:
        return None

    booking_id = raw // 1000
    seat_pos = raw % 1000
    if booking_id <= 0 or seat_pos <= 0:
        return None

    return booking_id, seat_pos - 1


def _assign_dashboard_virtual_booking_seat(
    db: Session,
    booking_id: int,
    seat_index: int,
    seat_no: str,
) -> dict:
    """
    Позволява бутонът „Смени място“ да работи и за synthetic dashboard редове.
    Това са случаи, в които booking има места/qty, но няма достатъчно TripPassenger rows.
    """
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if not re.fullmatch(r"\d{1,2}", seat_no):
        raise HTTPException(status_code=400, detail="Invalid seat number")

    resolved_trip_id = getattr(booking, "trip_id", None) or _resolve_booking_trip_id(db, booking)
    if resolved_trip_id:
        booking.trip_id = resolved_trip_id

    if not _ensure_booking_has_service(db, booking):
        raise HTTPException(status_code=400, detail="Booking has no trip/service")

    allowed = set(_service_default_seat_map(booking))
    if seat_no not in allowed:
        raise HTTPException(status_code=400, detail="Invalid seat number")

    required_count = max(_booking_passenger_count(db, booking), int(seat_index) + 1, 1)
    rows = _ensure_booking_seat_rows(db, booking, required_count)
    rows = sorted(rows, key=lambda r: int(getattr(r, "id", 0) or 0))

    # Проверка срещу други bookings в същия service.
    taken_by_others = _service_taken_seats(db, booking, exclude_booking_id=booking.id)
    if seat_no in taken_by_others:
        raise HTTPException(status_code=409, detail="Seat already taken")

    # Проверка срещу други места в същия booking.
    for idx, row in enumerate(rows):
        if idx == seat_index:
            continue
        existing = str(getattr(row, "seat_no", None) or "").strip()
        if existing and existing == seat_no:
            raise HTTPException(status_code=409, detail="Seat already taken")

    target = rows[seat_index]
    target.trip_id = getattr(booking, "trip_id", None)
    target.seat_no = seat_no
    target.is_final = True
    target.selection_mode = "admin_dashboard"

    normalized_seats: list[str] = []
    for row in rows:
        s = str(getattr(row, "seat_no", None) or "").strip()
        if s and s not in normalized_seats:
            normalized_seats.append(s)

    _sync_booking_seats_to_trip_passengers(db, booking.id, normalized_seats)
    db.commit()

    return {
        "ok": True,
        "passenger_id": _dashboard_virtual_passenger_id(booking.id, seat_index),
        "booking_id": booking.id,
        "seat_index": seat_index,
        "seat_no": seat_no,
        "seat_locked_by_admin": False,
        "virtual": True,
    }


@app.post("/admin/passengers/{passenger_id}/assign-seat")
def admin_assign_passenger_seat(
    passenger_id: int,
    payload: AdminAssignSeatPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        raise HTTPException(status_code=403, detail="Admin only")

    seat_no = (payload.seat_no or "").strip()
    if not re.fullmatch(r"\d{1,2}", seat_no):
        raise HTTPException(status_code=400, detail="Invalid seat number")

    # Negative IDs are synthetic dashboard rows for bookings that have seat/qty,
    # but do not yet have a corresponding TripPassenger row.
    if int(passenger_id) < 0:
        decoded = _decode_dashboard_virtual_passenger_id(passenger_id)
        if not decoded:
            raise HTTPException(status_code=404, detail="Passenger not found")
        booking_id, seat_index = decoded
        return _assign_dashboard_virtual_booking_seat(db, booking_id, seat_index, seat_no)

    passenger = db.query(TripPassenger).filter(TripPassenger.id == passenger_id).first()
    if not passenger:
        raise HTTPException(status_code=404, detail="Passenger not found")

    trip_id = getattr(passenger, "trip_id", None)

    if not trip_id and getattr(passenger, "booking_id", None):
        booking = (
            db.query(Booking)
            .filter(Booking.id == passenger.booking_id)
            .first()
        )

        if booking:
            trip_id = getattr(booking, "trip_id", None) or _resolve_booking_trip_id(db, booking)

            if trip_id:
                passenger.trip_id = trip_id
                db.flush()

    if not trip_id:
        raise HTTPException(status_code=400, detail="Passenger has no trip")

    others = (
        db.query(TripPassenger)
        .filter(TripPassenger.trip_id == trip_id)
        .filter(TripPassenger.id != passenger.id)
        .all()
    )

    for other in others:
        other_effective_seat = str(
            getattr(other, "manual_seat_no", None)
            or getattr(other, "seat_no", None)
            or ""
        ).strip()

        if other_effective_seat == seat_no:
            raise HTTPException(status_code=409, detail="Seat already taken")

    if hasattr(passenger, "manual_seat_no"):
        passenger.manual_seat_no = seat_no
    else:
        passenger.seat_no = seat_no

    if hasattr(passenger, "seat_locked_by_admin"):
        passenger.seat_locked_by_admin = True

    # ВАЖНО:
    # Админ промяната вече се записва и в BookingSeat,
    # за да може portal Seat Map / ticket / booking final seats да виждат същото място.
    if getattr(passenger, "booking_id", None):
        _sync_admin_passenger_seat_to_booking_seat(
            db=db,
            passenger=passenger,
            seat_no=seat_no,
        )

    db.commit()

    return {
        "ok": True,
        "passenger_id": passenger.id,
        "seat_no": seat_no,
        "seat_locked_by_admin": True,
    }



def _effective_trip_passenger_seat(p: TripPassenger) -> str:
    return str(getattr(p, "manual_seat_no", None) or getattr(p, "seat_no", None) or "").strip()


def _empty_dashboard_direction_payload(label: str = "—", key: str = "") -> dict:
    return {
        "present": False,
        "key": key,
        "label": label,
        "issue_count": 0,
        "booking_count": 0,
        "total_confirmed": 0,
        "bank_paypal_missing_proof_le72": [],
        "bank_paypal_missing_proof_gt72": [],
        "cash_not_confirmed_le72": [],
        "cash_not_confirmed_gt72": [],
        "dispatcher_seat_assignment_needed": [],
        "taken_seats": [],
        "passengers": [],
    }


def _dashboard_booking_base_date(booking: Booking, trip_by_id: dict[int, Trip] | None = None) -> date | None:
    booking_date = getattr(booking, "booking_date", None)
    if booking_date:
        if isinstance(booking_date, datetime):
            return booking_date.date()
        if isinstance(booking_date, date):
            return booking_date
        try:
            return datetime.fromisoformat(str(booking_date)).date()
        except Exception:
            pass

    dep_dt = _booking_departure_dt_for_dispatch(None, booking)
    if dep_dt:
        return dep_dt.date()

    trip_id = getattr(booking, "trip_id", None)
    if trip_id and trip_by_id:
        trip = trip_by_id.get(int(trip_id))
        if trip and getattr(trip, "date_time", None):
            try:
                return trip.date_time.date()
            except Exception:
                pass

    return None


def _dashboard_trip_base_date(trip: Trip | None) -> date | None:
    if not trip or not getattr(trip, "date_time", None):
        return None
    try:
        return trip.date_time.date()
    except Exception:
        return None


def _dashboard_stop_country_group(value: str | None) -> str | None:
    key = _norm_stop_key(value)
    if not key:
        return None

    ua_keys = {"kyiv", "zhytomyr", "rivne", "lviv"}
    at_keys = {
        "wien", "stpolten", "linz", "wels", "salzburg",
        "innsbruck", "bruck", "graz", "klagenfurt", "villach",
    }

    if key in ua_keys:
        return "UA"
    if key in at_keys:
        return "AT"
    return None


def _dashboard_direction_meta_from_values(from_value: str | None, to_value: str | None) -> dict:
    from_meta = _stop_meta(from_value)
    to_meta = _stop_meta(to_value)

    from_key = (from_meta.get("key") or _norm_service_part(from_value) or "unknown_from").strip()
    to_key = (to_meta.get("key") or _norm_service_part(to_value) or "unknown_to").strip()
    from_label = (from_meta.get("label") or (from_value or "—")).strip() or "—"
    to_label = (to_meta.get("label") or (to_value or "—")).strip() or "—"

    from_group = _dashboard_stop_country_group(from_value)
    to_group = _dashboard_stop_country_group(to_value)

    if from_group == "AT" and to_group == "UA":
        return {
            "key": "AT->UA",
            "label": "AT → UA",
            "country_from": from_group,
            "country_to": to_group,
            "from_key": from_key,
            "to_key": to_key,
        }

    if from_group == "UA" and to_group == "AT":
        return {
            "key": "UA->AT",
            "label": "UA → AT",
            "country_from": from_group,
            "country_to": to_group,
            "from_key": from_key,
            "to_key": to_key,
        }

    return {
        "key": f"{from_key}->{to_key}",
        "label": f"{from_label} → {to_label}",
        "country_from": from_group,
        "country_to": to_group,
        "from_key": from_key,
        "to_key": to_key,
    }


def _dashboard_direction_meta_for_trip(trip: Trip | None) -> dict:
    if not trip:
        return _dashboard_direction_meta_from_values(None, None)

    return _dashboard_direction_meta_from_values(
        getattr(trip, "route_from", None),
        getattr(trip, "route_to", None),
    )


def _dashboard_direction_meta_for_booking(booking: Booking, trip_by_id: dict[int, Trip] | None = None) -> dict:
    trip_id = getattr(booking, "trip_id", None)
    if trip_id and trip_by_id:
        trip = trip_by_id.get(int(trip_id))
        if trip and (getattr(trip, "route_from", None) or getattr(trip, "route_to", None)):
            return _dashboard_direction_meta_for_trip(trip)

    candidates = [
        (getattr(booking, "route_from", None), getattr(booking, "route_to", None)),
        (getattr(booking, "bus_from", None), getattr(booking, "bus_to", None)),
    ]

    for from_value, to_value in candidates:
        if str(from_value or "").strip() and str(to_value or "").strip():
            return _dashboard_direction_meta_from_values(from_value, to_value)

    return _dashboard_direction_meta_from_values(
        getattr(booking, "route_from", None) or getattr(booking, "bus_from", None),
        getattr(booking, "route_to", None) or getattr(booking, "bus_to", None),
    )


def _dashboard_direction_sort_key(item: dict) -> tuple:
    key = str(item.get("key") or "")
    if key == "AT->UA":
        group_order = 0
    elif key == "UA->AT":
        group_order = 1
    else:
        group_order = 2

    return (group_order, str(item.get("label") or "").lower(), key.lower())


def _get_booking_trip_passengers_for_seat_control(db: Session, booking: Booking) -> list[TripPassenger]:
    passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking.id)
        .order_by(TripPassenger.id.asc())
        .all()
    )
    return sorted(passengers, key=_trip_passenger_sort_key)


def _booking_has_admin_locked_seat(db: Session, booking: Booking) -> bool:
    passengers = _get_booking_trip_passengers_for_seat_control(db, booking)
    return any(bool(getattr(p, "seat_locked_by_admin", False)) for p in passengers)


def _set_booking_trip_passengers_admin_seat_lock(db: Session, booking_id: int, is_locked: bool = True) -> None:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        return

    passengers = _get_booking_trip_passengers_for_seat_control(db, booking)
    for p in passengers:
        if hasattr(p, "seat_locked_by_admin"):
            p.seat_locked_by_admin = bool(is_locked)
        if getattr(p, "booking_id", None) is None:
            p.booking_id = booking.id


def _build_dashboard_direction_payload(
    label: str,
    items: list[Booking],
    trip_passengers: list[TripPassenger],
    bank_paypal_missing_proof_le72: list[dict],
    cash_not_confirmed_le72: list[dict],
    dispatcher_seat_assignment_needed: list[dict] | None = None,
    bank_paypal_missing_proof_gt72: list[dict] | None = None,
    cash_not_confirmed_gt72: list[dict] | None = None,
    extra_taken_seats: set[str] | list[str] | None = None,
    total_confirmed: int | None = None,
):
    dispatcher_seat_assignment_needed = dispatcher_seat_assignment_needed or []
    bank_paypal_missing_proof_gt72 = bank_paypal_missing_proof_gt72 or []
    cash_not_confirmed_gt72 = cash_not_confirmed_gt72 or []

    taken_seats = set(str(x).strip() for x in (extra_taken_seats or []) if str(x).strip())
    passengers_payload: list[dict] = []
    represented_booking_ids: set[int] = set()
    represented_count_by_booking_id: dict[int, int] = {}
    booking_confirmed_total = 0

    def _split_name_parts(full_name: str) -> tuple[str | None, str | None]:
        full_name = (full_name or "").strip()
        if not full_name:
            return None, None
        parts = full_name.split(None, 1)
        if len(parts) == 1:
            return parts[0], None
        return parts[0], parts[1]

    booking_by_id_for_dashboard: dict[int, Booking] = {}
    booking_by_external_id_for_dashboard: dict[str, Booking] = {}
    for booking in items or []:
        bid = getattr(booking, "id", None)
        if bid is not None:
            booking_by_id_for_dashboard[int(bid)] = booking

        ext_key = _booking_external_id_key(booking)
        if ext_key and ext_key not in booking_by_external_id_for_dashboard:
            booking_by_external_id_for_dashboard[ext_key] = booking

    for p in sorted(list(trip_passengers or []), key=_trip_passenger_sort_key):
        seat_no = _effective_trip_passenger_seat(p)
        if seat_no:
            taken_seats.add(seat_no)

        booking_id = getattr(p, "booking_id", None)
        effective_booking_id_for_count = None

        if booking_id is not None:
            effective_booking_id_for_count = int(booking_id)
        else:
            # Ако TripPassenger редът още не е linked с booking_id,
            # броим го към booking-а чрез external_id, за да не създаваме
            # duplicate synthetic ред в dashboard.
            p_ext_key = _trip_passenger_external_id_key(
                p,
                booking_by_id=booking_by_id_for_dashboard,
            )
            matched_booking = booking_by_external_id_for_dashboard.get(p_ext_key or "")
            if matched_booking and getattr(matched_booking, "id", None) is not None:
                effective_booking_id_for_count = int(matched_booking.id)

        if effective_booking_id_for_count is not None:
            represented_booking_ids.add(effective_booking_id_for_count)
            represented_count_by_booking_id[effective_booking_id_for_count] = (
                represented_count_by_booking_id.get(effective_booking_id_for_count, 0) + 1
            )

        full_name = _effective_text(
            getattr(p, "manual_full_name", None),
            getattr(p, "full_name", None),
        ).strip()

        first_name = getattr(p, "first_name", None)
        last_name = getattr(p, "last_name", None)
        if not (first_name or last_name):
            first_name, last_name = _split_name_parts(full_name)

        passenger_name = f"{first_name or ''} {last_name or ''}".strip() or full_name or "—"
        phone = _effective_text(
            getattr(p, "manual_phone", None),
            getattr(p, "phone", None),
        ).strip() or None

        passengers_payload.append({
            "id": int(getattr(p, "id", 0) or 0),
            "trip_id": getattr(p, "trip_id", None),
            "booking_id": getattr(p, "booking_id", None),
            "first_name": first_name,
            "last_name": last_name,
            "passenger_name": passenger_name,
            "phone": phone,
            "seat_no": seat_no or None,
            "seat_locked_by_admin": bool(getattr(p, "seat_locked_by_admin", False)),
        })

    for booking in items or []:
        booking_id = getattr(booking, "id", None)
        booking_id_int = int(booking_id or 0)
        booking_pax_count = max(1, int(getattr(booking, "_dashboard_passenger_count", 0) or 1))
        booking_confirmed_total += booking_pax_count

        final_seats = [
            str(x or "").strip()
            for x in list(getattr(booking, "_dashboard_final_seats", None) or _booking_selected_seats(booking) or [])
            if str(x or "").strip()
        ]

        for seat_str in final_seats:
            taken_seats.add(seat_str)

        if not booking_id_int:
            continue

        represented_count = int(represented_count_by_booking_id.get(booking_id_int, 0) or 0)
        missing_count = max(0, booking_pax_count - represented_count)
        if missing_count <= 0:
            continue

        # Ако booking има места/qty, но няма достатъчно TripPassenger rows,
        # показваме synthetic редове в dashboard Passengers. Така Seat Map и
        # Passengers таблицата не се разминават. ID-то е отрицателно и route-ът
        # /admin/passengers/{id}/assign-seat го обработва като booking-seat ред.
        booking_first_name = getattr(booking, "first_name", None)
        booking_last_name = getattr(booking, "last_name", None)
        base_name = f"{booking_first_name or ''} {booking_last_name or ''}".strip() or "—"
        booking_phone = str(getattr(booking, "phone", None) or "").strip() or None

        for offset in range(missing_count):
            passenger_index = represented_count + offset
            seat_no = final_seats[passenger_index] if passenger_index < len(final_seats) else None

            display_last_name = booking_last_name
            passenger_name = base_name
            if booking_pax_count > 1:
                passenger_name = f"{base_name} ({passenger_index + 1})"

            passengers_payload.append({
                "id": _dashboard_virtual_passenger_id(booking_id_int, passenger_index),
                "virtual": True,
                "trip_id": getattr(booking, "trip_id", None),
                "booking_id": booking_id_int,
                "first_name": booking_first_name,
                "last_name": display_last_name,
                "passenger_name": passenger_name,
                "phone": booking_phone,
                "seat_no": seat_no or None,
                "seat_locked_by_admin": False,
            })

    if total_confirmed is None:
        total_confirmed = max(booking_confirmed_total, len(passengers_payload))

    actionable_issue_count = (
        len(bank_paypal_missing_proof_le72)
        + len(cash_not_confirmed_le72)
        + len(dispatcher_seat_assignment_needed)
    )

    def _seat_sort_value(x: str):
        s = str(x or "").strip()
        return int(s) if s.isdigit() else 9999

    return {
        "present": True,
        "label": label,
        "issue_count": actionable_issue_count,
        "booking_count": int(len(items or [])),
        "bank_paypal_missing_proof_le72": bank_paypal_missing_proof_le72,
        "bank_paypal_missing_proof_gt72": bank_paypal_missing_proof_gt72,
        "cash_not_confirmed_le72": cash_not_confirmed_le72,
        "cash_not_confirmed_gt72": cash_not_confirmed_gt72,
        "dispatcher_seat_assignment_needed": dispatcher_seat_assignment_needed,
        "total_confirmed": int(total_confirmed or 0),
        "taken_seats": sorted(taken_seats, key=_seat_sort_value),
        "passengers": passengers_payload,
    }

# =======================
# QR Payment
# =======================

def _format_epc_amount_eur(value) -> str:
    if value is None:
        return ""
    try:
        amt = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return ""
    if amt <= 0:
        return ""
    return f"EUR{amt}"


def _portal_payment_epc_payload(booking: Booking) -> str:
    fields = [
        "BCD",
        "002",
        "1",
        "SCT",
        "",
        "AUSTRIAN INCENTIVE SERVICE",
        "AT192011129351217600",
        "",
        "",
        "",
        str(getattr(booking, "external_id", "") or "").strip()[:140],
    ]
    while fields and fields[-1] == "":
        fields.pop()
    return "\n".join(fields)


@app.get("/portal/payment-qr-debug")
def portal_payment_qr_debug(request: Request, db: Session = Depends(get_db)):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    payload = _portal_payment_epc_payload(booking)
    return Response(content=payload, media_type="text/plain; charset=utf-8")

@app.get("/portal/payment-qr.svg")
def portal_payment_qr_svg(request: Request, db: Session = Depends(get_db)):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    payload = _portal_payment_epc_payload(booking)
    svg_bytes = _build_qr_svg_bytes(payload, size=220)

    return Response(
        content=svg_bytes,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )

# =======================
# QR Ticket
# =======================

def _portal_ticket_qr_svg_response(
    request: Request,
    db: Session,
    as_attachment: bool = False,
):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    if not _can_portal_view_ticket(booking):
        return Response(status_code=404)

    selected_seat = _booking_selected_seat(booking)
    if not selected_seat or not _ticket_qr_available(booking):
        return Response(status_code=404)

    payload = _portal_ticket_payload(booking, selected_seat)
    qr_data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    svg_bytes = _build_qr_svg_bytes(qr_data, size=260)

    headers = {"Cache-Control": "no-store"}
    if as_attachment:
        headers["Content-Disposition"] = f'attachment; filename="ticket-qr-{booking.external_id}.svg"'

    return Response(
        content=svg_bytes,
        media_type="image/svg+xml",
        headers=headers,
    )



def _booking_is_cancelled_or_pending_cancellation(booking: Booking | None) -> bool:
    if not booking:
        return False

    status = str(getattr(booking, "booking_status", None) or "").strip().lower()
    return status in {"cancelled", "cancellation_requested"}


def _split_customer_name_for_booking_edit(value: str) -> tuple[str | None, str | None]:
    raw = (value or "").strip()
    if not raw:
        return None, None

    parts = raw.split()
    if len(parts) == 1:
        return parts[0], None

    return parts[0], " ".join(parts[1:])


def _booking_total_input_value(value) -> str:
    if value is None:
        return ""
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    except Exception:
        return str(value)


def _booking_departure_date_input_value(booking: Booking) -> str:
    booking_date = getattr(booking, "booking_date", None)
    if not booking_date:
        return ""

    try:
        if isinstance(booking_date, datetime):
            return booking_date.date().strftime("%Y-%m-%d")
        return booking_date.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _booking_departure_time_input_value(booking: Booking, dispatch_departure_dt: datetime | None = None) -> str:
    if dispatch_departure_dt:
        try:
            return dispatch_departure_dt.strftime("%H:%M")
        except Exception:
            pass

    first_time = _extract_first_departure_time(getattr(booking, "time_range_raw", None))
    if first_time:
        try:
            return first_time.strftime("%H:%M")
        except Exception:
            return ""

    return ""


@app.post("/admin/bookings/{booking_id}/update-basic")
def admin_booking_update_basic(
    booking_id: int,
    request: Request,
    customer_name: str = Form(""),
    departure_date: str = Form(""),
    departure_time: str = Form(""),
    phone: str = Form(""),
    total: str = Form(""),
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(404, "Booking not found")

    customer_name = (customer_name or "").strip()
    departure_date = (departure_date or "").strip()
    departure_time = (departure_time or "").strip()
    phone = (phone or "").strip()
    total = (total or "").strip()

    if not customer_name:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?edit_err=customer",
            status_code=303,
        )

    if not departure_date:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?edit_err=departure_date",
            status_code=303,
        )

    if not departure_time:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?edit_err=departure_time",
            status_code=303,
        )

    if not total:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?edit_err=total",
            status_code=303,
        )

    try:
        parsed_departure_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
    except Exception:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?edit_err=departure_date",
            status_code=303,
        )

    try:
        parsed_departure_time = datetime.strptime(departure_time, "%H:%M").time()
        normalized_departure_time = parsed_departure_time.strftime("%H:%M")
    except Exception:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?edit_err=departure_time",
            status_code=303,
        )

    total_norm = total.replace(" ", "").replace(",", ".")
    try:
        parsed_total = Decimal(total_norm).quantize(Decimal("0.01"))
    except Exception:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?edit_err=total",
            status_code=303,
        )

    first_name, last_name = _split_customer_name_for_booking_edit(customer_name)
    if not first_name:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?edit_err=customer",
            status_code=303,
        )

    old_customer_name = f"{booking.first_name or ''} {booking.last_name or ''}".strip()
    old_departure_date = _booking_departure_date_input_value(booking)
    old_departure_time = _booking_departure_time_input_value(booking)
    old_phone = (booking.phone or "").strip()
    old_total = _booking_total_input_value(getattr(booking, "total", None))

    booking.first_name = first_name
    booking.last_name = last_name
    booking.booking_date = parsed_departure_date
    booking.time_range_raw = normalized_departure_time
    booking.phone = phone or None
    booking.total = parsed_total

    change_log = []

    if old_customer_name != customer_name:
        change_log.append(f"Customer: {old_customer_name or '—'} -> {customer_name}")

    if old_departure_date != departure_date:
        change_log.append(f"Departure Date: {old_departure_date or '—'} -> {departure_date}")

    if old_departure_time != normalized_departure_time:
        change_log.append(f"Departure Time: {old_departure_time or '—'} -> {normalized_departure_time}")

    if old_phone != phone:
        change_log.append(f"Phone: {old_phone or '—'} -> {phone or '—'}")

    if old_total != str(parsed_total):
        change_log.append(f"Total: {old_total or '—'} -> {parsed_total}")

    if change_log:
        stamp = _vienna_now_naive().strftime("%d.%m.%Y %H:%M")
        audit_block = "[ADMIN BOOKING EDIT " + stamp + "]\n" + "\n".join(change_log)

        old_notes = (booking.notes or "").strip()
        booking.notes = f"{old_notes}\n\n{audit_block}".strip() if old_notes else audit_block

    try:
        rematch_booking_to_trip(db, booking.id)
        db.flush()
        db.refresh(booking)

        if booking.trip_id:
            sync_booking_to_trip_passengers_by_id(
                db,
                booking.id,
                strict_replace_extra=False,
            )
            db.flush()
    except Exception:
        pass

    db.commit()

    return RedirectResponse(
        url=f"/admin/bookings/{booking_id}?edit_ok=1",
        status_code=303,
    )

# =======================
# Delete Booking 
# =======================

def _pg_table_exists(db: Session, table_name: str) -> bool:
    row = db.execute(
        text("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
            )
        """),
        {"table_name": table_name},
    ).scalar()
    return bool(row)


def _pg_column_exists(db: Session, table_name: str, column_name: str) -> bool:
    row = db.execute(
        text("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = :column_name
            )
        """),
        {"table_name": table_name, "column_name": column_name},
    ).scalar()
    return bool(row)


def _delete_where_booking_id(db: Session, table_name: str, booking_id: int) -> int:
    if not _pg_table_exists(db, table_name):
        return 0
    if not _pg_column_exists(db, table_name, "booking_id"):
        return 0

    result = db.execute(
        text(f'DELETE FROM "{table_name}" WHERE booking_id = :booking_id'),
        {"booking_id": booking_id},
    )
    return int(result.rowcount or 0)


def _delete_where_passenger_ids(db: Session, table_name: str, passenger_ids: list[int]) -> int:
    if not passenger_ids:
        return 0
    if not _pg_table_exists(db, table_name):
        return 0
    if not _pg_column_exists(db, table_name, "passenger_id"):
        return 0

    result = db.execute(
        text(f'DELETE FROM "{table_name}" WHERE passenger_id = ANY(:passenger_ids)'),
        {"passenger_ids": passenger_ids},
    )
    return int(result.rowcount or 0)


def _collect_trip_passenger_ids_for_booking(db: Session, booking_id: int) -> list[int]:
    if not _pg_table_exists(db, "trip_passengers"):
        return []
    if not _pg_column_exists(db, "trip_passengers", "booking_id"):
        return []

    rows = db.execute(
        text("""
            SELECT id
            FROM trip_passengers
            WHERE booking_id = :booking_id
            ORDER BY id
        """),
        {"booking_id": booking_id},
    ).fetchall()

    return [int(r[0]) for r in rows if r and r[0] is not None]


@app.post("/admin/bookings/{booking_id}/delete")
def admin_booking_delete(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        return RedirectResponse(url="/admin/bookings/list", status_code=303)

    incoming_email_id = getattr(booking, "incoming_email_id", None)
    passenger_ids = _collect_trip_passenger_ids_for_booking(db, booking_id)

    try:
        # 1) най-дълбоките child записи по passenger_id
        _delete_where_passenger_ids(db, "driver_boarding_state", passenger_ids)

        # 2) child записи по booking_id
        _delete_where_booking_id(db, "payment_proofs", booking_id)
        _delete_where_booking_id(db, "booking_ticket_lines", booking_id)
        _delete_where_booking_id(db, "driver_boarding_state", booking_id)
        _delete_where_booking_id(db, "trip_passengers", booking_id)

        # 3) самата booking
        db.delete(booking)
        db.flush()

        # 4) incoming_email само ако никой друг booking не го ползва
        if incoming_email_id and _pg_table_exists(db, "incoming_emails"):
            still_used = db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM bookings
                    WHERE incoming_email_id = :incoming_email_id
                """),
                {"incoming_email_id": incoming_email_id},
            ).scalar()

            if not still_used:
                db.execute(
                    text("DELETE FROM incoming_emails WHERE id = :incoming_email_id"),
                    {"incoming_email_id": incoming_email_id},
                )

        db.commit()

    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/bookings/list?err=delete_{booking_id}",
            status_code=303,
        )

    return RedirectResponse(url="/admin/bookings/list?ok=deleted", status_code=303)



# =======================
# Booking Cancellation Helpers
# =======================


def _booking_departure_datetime(booking: Booking, db: Session) -> datetime | None:
    trip = None
    if getattr(booking, "trip_id", None):
        trip = db.query(Trip).filter(Trip.id == booking.trip_id).first()

    if trip and getattr(trip, "date_time", None):
        return trip.date_time

    booking_date = getattr(booking, "booking_date", None)
    time_from = (getattr(booking, "time_from", None) or "").strip()

    if booking_date:
        if isinstance(booking_date, datetime):
            base_date = booking_date.date()
        else:
            base_date = booking_date

        if time_from:
            try:
                hh, mm = time_from.split(":")[:2]
                return datetime.combine(base_date, time(int(hh), int(mm)))
            except Exception:
                pass

        return datetime.combine(base_date, time(0, 0))

    return None


def _portal_cancellation_policy(booking: Booking, db: Session) -> dict:
    departure_at = _booking_departure_datetime(booking, db)
    now = datetime.now()

    if not departure_at:
        return {
            "allowed": False,
            "refund_percent": 0,
            "hours_left": None,
            "message": "Липсва дата на пътуване и анулация не може да бъде изчислена.",
        }

    hours_left = (departure_at - now).total_seconds() / 3600.0

    total = getattr(booking, "total", None)
    currency = getattr(booking, "currency", None)

    refund_percent = 0
    allowed = False
    message = ""

    if hours_left >= 72:
        allowed = True
        refund_percent = 100
        message = "Възможна е 100% анулация."
    elif hours_left >= 24:
        allowed = True
        refund_percent = 50
        message = "Възможна е 50% анулация."
    else:
        allowed = False
        refund_percent = 0
        message = "По-малко от 24 часа до пътуването. Анулация не е възможна."

    refund_amount = None
    if total is not None:
        try:
            refund_amount = (Decimal(str(total)) * Decimal(refund_percent) / Decimal("100")).quantize(Decimal("0.01"))
        except Exception:
            refund_amount = None

    return {
        "allowed": allowed,
        "refund_percent": refund_percent,
        "refund_amount": refund_amount,
        "currency": currency,
        "hours_left": hours_left,
        "departure_at": departure_at,
        "message": message,
        "too_late": hours_left < 24,
    }




@app.get("/portal/cancellation", response_class=HTMLResponse)
def portal_cancellation_page(request: Request, db: Session = Depends(get_db)):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    cancel_ok = request.query_params.get("ok", "")
    cancel_err = request.query_params.get("err", "")

    existing_cancellation = (
        db.query(BookingCancellation)
        .filter(BookingCancellation.booking_id == booking.id)
        .order_by(BookingCancellation.id.desc())
        .first()
    )

    cancel_policy = _portal_cancellation_policy(booking, db)

    return templates.TemplateResponse(
        request,
        "portal/cancellation.html",
        {
            "booking": booking,
            "cancel_policy": cancel_policy,
            "existing_cancellation": existing_cancellation,
            "cancel_ok": cancel_ok,
            "cancel_err": cancel_err,
        },
    )


@app.post("/portal/cancel-booking")
def portal_cancel_booking(
    request: Request,
    reason: str = Form(""),
    db: Session = Depends(get_db),
):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    if getattr(booking, "booking_status", None) in {"cancelled", "cancellation_requested"}:
        return RedirectResponse(url="/portal/cancellation?err=exists", status_code=303)

    existing = (
        db.query(BookingCancellation)
        .filter(BookingCancellation.booking_id == booking.id)
        .filter(BookingCancellation.admin_status.in_(["pending", "approved", "processed"]))
        .first()
    )
    if existing:
        return RedirectResponse(url="/portal/cancellation?err=exists", status_code=303)

    cancel_policy = _portal_cancellation_policy(booking, db)
    if not cancel_policy.get("allowed"):
        return RedirectResponse(url="/portal/cancellation?err=late", status_code=303)

    cancellation = BookingCancellation(
        booking_id=booking.id,
        external_id=getattr(booking, "external_id", None),
        requested_at=datetime.utcnow(),
        travel_at=cancel_policy.get("departure_at"),
        hours_before_departure=round(cancel_policy["hours_left"], 2) if cancel_policy.get("hours_left") is not None else None,
        refund_percent=cancel_policy.get("refund_percent") or 0,
        refund_amount=cancel_policy.get("refund_amount"),
        currency=cancel_policy.get("currency"),
        reason=(reason or "").strip() or None,
        admin_status="pending",
        passenger_email_sent=False,
    )
    db.add(cancellation)

    booking.booking_status = "cancellation_requested"
    db.commit()
    db.refresh(cancellation)

    try:
        from app.services.mail_sender import send_booking_cancellation_email

        send_booking_cancellation_email(
            to_email=(booking.email or "").strip(),
            passenger_name=f"{booking.first_name or ''} {booking.last_name or ''}".strip(),
            external_id=str(booking.external_id or ""),
            refund_percent=cancel_policy.get("refund_percent") or 0,
            refund_amount=cancel_policy.get("refund_amount"),
            currency=cancel_policy.get("currency"),
            departure_at=cancel_policy.get("departure_at"),
        )

        cancellation.passenger_email_sent = True
        db.commit()
    except Exception:
        db.rollback()

    return RedirectResponse(url="/portal/cancellation?ok=1", status_code=303)


@app.get("/admin/bookings/cancellations", response_class=HTMLResponse)
def admin_booking_cancellations_page(
    request: Request,
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    items = (
        db.query(BookingCancellation)
        .order_by(BookingCancellation.requested_at.desc(), BookingCancellation.id.desc())
        .all()
    )

    return templates.TemplateResponse(request, "admin/booking_cancellations.html", {
        "items": items,
    })


# =======================
# Helpers
# =======================

def _service_seat_layout(_: Booking | None = None) -> list[list[int | None]]:
    return SEAT_LAYOUT


def _service_default_seat_map(_: Booking | None = None) -> list[str]:
    out: list[str] = []
    for row in SEAT_LAYOUT:
        for seat in row:
            if seat is not None:
                out.append(str(seat))
    return out


def _norm_stop_key(value: str | None) -> str:
    if not value:
        return ""

    s = str(value).strip().lower()
    s = re.sub(r"\s+", " ", s)

    aliases = {
        "kyiv": ["kyiv", "kiev", "київ", "киев"],
        "zhytomyr": ["zhytomyr", "zhitomir", "житомир"],
        "rivne": ["rivne", "rovno", "рівне", "ривне", "ровно"],
        "lviv": ["lviv", "lvov", "львів", "львов"],

        "wien": ["wien", "vienna", "відень", "вiдень", "видень"],
        "stpolten": ["st. pölten", "st pölten", "st.polten", "st polten", "sankt polten", "ст. пьоелтен", "ст пьоелтен"],
        "linz": ["linz", "лінц", "линц"],
        "wels": ["wels", "вельс"],
        "salzburg": ["salzburg", "salzburg sud", "sud", "p&r süd salzburg", "зальцбург"],
        "innsbruck": ["innsbruck", "інсбрук", "инсбрук"],
        "bruck": ["bruck", "bruck an der mur", "брук", "брук ан дер мур"],
        "graz": ["graz", "грац"],
        "klagenfurt": ["klagenfurt", "клагенфурт"],
        "villach": ["villach", "філлах", "филлах"],
    }

    for key, variants in aliases.items():
        for v in variants:
            if s == v or v in s:
                return key

    return s

def _stop_meta(value: str | None) -> dict:
    key = _norm_stop_key(value)
    data = STOP_ADDRESS_BOOK.get(key)

    if data:
        return {
            "key": key,
            "label": data["label"],
            "address": data["address"],
        }

    raw = (value or "").strip()
    return {
        "key": key,
        "label": raw or "—",
        "address": "Адресът предстои да бъде уточнен",
    }


def _booking_stop_points(booking: Booking) -> dict:
    from_value = getattr(booking, "route_from", None) or getattr(booking, "bus_from", None)
    to_value = getattr(booking, "route_to", None) or getattr(booking, "bus_to", None)

    departure = _stop_meta(from_value)
    arrival = _stop_meta(to_value)

    return {
        "departure": departure,
        "arrival": arrival,
    }



def _contains_any_token(text: str, variants: list[str]) -> bool:
    return any(v in text for v in variants)


def _direction_code_from_values(from_value: str | None, to_value: str | None) -> str | None:
    f = _norm_service_part(from_value)
    t = _norm_service_part(to_value)

    if not f or not t:
        return None

    innsbruck_variants = ["innsbruck", "інсбрук", "инсбрук", "iнсбрук"]
    kyiv_variants = ["kyiv", "kiev", "київ", "киев", "киïв", "київ"]

    if _contains_any_token(f, innsbruck_variants) and _contains_any_token(t, kyiv_variants):
        return "IK"

    if _contains_any_token(f, kyiv_variants) and _contains_any_token(t, innsbruck_variants):
        return "KI"

    return None


def _booking_direction_code(booking: Booking) -> str:
    candidates = [
        (getattr(booking, "bus_from", None), getattr(booking, "bus_to", None)),
        (getattr(booking, "route_from", None), getattr(booking, "route_to", None)),
    ]

    for from_value, to_value in candidates:
        code = _direction_code_from_values(from_value, to_value)
        if code:
            return code

    bus_name = _norm_service_part(getattr(booking, "bus_name", None))
    if bus_name:
        innsbruck_variants = ["innsbruck", "інсбрук", "инсбрук", "iнсбрук"]
        kyiv_variants = ["kyiv", "kiev", "київ", "киев", "киïв"]

        has_innsbruck = _contains_any_token(bus_name, innsbruck_variants)
        has_kyiv = _contains_any_token(bus_name, kyiv_variants)

        if has_innsbruck and has_kyiv:
            bus_from = _norm_service_part(getattr(booking, "bus_from", None))
            route_from = _norm_service_part(getattr(booking, "route_from", None))

            if _contains_any_token(bus_from, kyiv_variants) or _contains_any_token(route_from, kyiv_variants):
                return "KI"

            if _contains_any_token(bus_from, innsbruck_variants) or _contains_any_token(route_from, innsbruck_variants):
                return "IK"

    return "OTHER"


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


def _now_local_naive() -> datetime:
    """
    Опитва Europe/Vienna.
    Ако tzdata липсва (често на Windows), пада обратно към локалното време.
    Връща naive datetime.
    """
    try:
        return datetime.now(ZoneInfo("Europe/Vienna")).replace(tzinfo=None)
    except ZoneInfoNotFoundError:
        return datetime.now()


def _today_vienna() -> date:
    return _now_local_naive().date()


def _vienna_now_naive() -> datetime:
    return _now_local_naive()


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



def _portal_booking_or_redirect(request: Request, db: Session):
    booking_id = request.session.get("portal_booking_id")
    if not booking_id:
        return None, RedirectResponse(url="/portal/login", status_code=303)

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        request.session.pop("portal_booking_id", None)
        return None, RedirectResponse(url="/portal/login?err=notfound", status_code=303)

    return booking, None

def _booking_external_id_key(booking: Booking | None) -> str | None:
    if not booking:
        return None

    external_id = getattr(booking, "external_id", None)
    if external_id is None:
        return None

    s = str(external_id).strip()
    return s or None


def _seat_sort_key(value: str):
    s = str(value or "").strip()
    if s.isdigit():
        return (0, int(s))
    return (1, s)


def _booking_selected_seats(booking: Booking) -> list[str]:
    """
    Връща всички FINAL seats за booking-а.
    """
    seats = list(getattr(booking, "seats", []) or [])
    out: list[str] = []

    for s in seats:
        seat_no = (getattr(s, "seat_no", None) or "").strip()
        is_final = bool(getattr(s, "is_final", False))
        if seat_no and is_final:
            out.append(seat_no)

    out = sorted(list(dict.fromkeys(out)), key=_seat_sort_key)
    return out


def _booking_selected_seat(booking: Booking) -> str | None:
    """
    Backward-compatible helper:
    връща първото FINAL seat, ако има такова.
    """
    seats = _booking_selected_seats(booking)
    return seats[0] if seats else None

def _booking_passenger_count(
    db: Session,
    booking: Booking,
    qty_map: dict[int, int] | None = None,
) -> int:
    """
    Определя колко пътници/места трябва да има booking-ът.

    Приоритет:
    1) BookingTicketLine.qty sum (ако е наличен предварително в qty_map)
    2) BookingTicketLine.qty sum от DB
    3) брой свързани TripPassenger rows
    4) брой BookingSeat rows
    5) fallback = 1
    """
    if not booking:
        return 1

    booking_id = getattr(booking, "id", None)
    if booking_id is None:
        return 1

    # 1) precomputed qty_map
    if qty_map is not None:
        cached = qty_map.get(int(booking_id))
        if cached is not None and int(cached) > 0:
            return int(cached)

    # 2) ticket lines sum
    total_qty = (
        db.query(func.coalesce(func.sum(BookingTicketLine.qty), 0))
        .filter(BookingTicketLine.booking_id == booking_id)
        .scalar()
    )
    if total_qty and int(total_qty) > 0:
        return int(total_qty)

    # 3) linked passengers
    pax_count = (
        db.query(func.count(TripPassenger.id))
        .filter(TripPassenger.booking_id == booking_id)
        .scalar()
        or 0
    )
    if int(pax_count) > 0:
        return int(pax_count)

    # 4) booking seats rows
    seat_count = (
        db.query(func.count(BookingSeat.id))
        .filter(BookingSeat.booking_id == booking_id)
        .scalar()
        or 0
    )
    if int(seat_count) > 0:
        return int(seat_count)

    # 5) optional direct booking field fallback
    for attr in ("passenger_count", "pax_count", "seats_count", "qty"):
        value = getattr(booking, attr, None)
        try:
            if value is not None and int(value) > 0:
                return int(value)
        except Exception:
            pass

    return 1


def _create_booking_seat_row(
    db: Session,
    booking: Booking,
    seat_no: str | None = None,
    is_final: bool = False,
    selection_mode: str = "imported",
) -> BookingSeat:
    resolved_trip_id = getattr(booking, "trip_id", None) or _resolve_booking_trip_id(db, booking)
    if resolved_trip_id:
        booking.trip_id = resolved_trip_id

    row = BookingSeat(
        booking_id=booking.id,
        trip_id=resolved_trip_id,
        seat_no=seat_no,
        is_final=is_final,
        selection_mode=selection_mode,
    )
    db.add(row)
    db.flush()
    return row



def _trip_taken_seats(db: Session, trip_id: int, exclude_booking_id: int | None = None) -> set[str]:
    """
    Взима вече заетите места по конкретен trip от TripPassenger.
    exclude_booking_id позволява текущият booking да не си блокира собственото място.
    """
    q = (
        db.query(TripPassenger)
        .filter(
            TripPassenger.trip_id == trip_id,
            TripPassenger.seat_no.isnot(None),
        )
    )

    if exclude_booking_id is not None:
        q = q.filter(
            or_(
                TripPassenger.booking_id.is_(None),
                TripPassenger.booking_id != exclude_booking_id,
            )
        )

    rows = q.all()
    taken: set[str] = set()

    for p in rows:
        seat = (p.seat_no or "").strip()
        if seat:
            taken.add(seat)

    return taken


def _candidate_bus_seats() -> list[str]:
    """
    MVP карта на места: 1..60
    """
    return [str(i) for i in range(1, 61)]


def _ensure_booking_seat_rows(db: Session, booking: Booking, required_count: int) -> list[BookingSeat]:
    """
    Осигурява booking-а да има поне required_count BookingSeat реда.
    """
    rows = (
        db.query(BookingSeat)
        .filter(BookingSeat.booking_id == booking.id)
        .order_by(BookingSeat.id.asc())
        .all()
    )

    while len(rows) < required_count:
        row = BookingSeat(
            booking_id=booking.id,
            trip_id=booking.trip_id,
            seat_no=None,
            is_final=False,
            selection_mode="imported",
        )
        db.add(row)
        db.flush()
        rows.append(row)

    return rows

def _ensure_booking_seat_row(db: Session, booking: Booking) -> BookingSeat:
    """
    Backward-compatible:
    връща първия ред, ако има; иначе създава placeholder.
    """
    row = (
        db.query(BookingSeat)
        .filter(BookingSeat.booking_id == booking.id)
        .order_by(BookingSeat.id.asc())
        .first()
    )
    if row:
        return row

    return _create_booking_seat_row(
        db=db,
        booking=booking,
        seat_no=None,
        is_final=False,
        selection_mode="imported",
    )


def _extract_first_departure_time(raw: str | None):
    """
    Взима първия час от time range, напр.:
      "07:30 - 10:30" -> time(7, 30)
      "7:30-10:30"    -> time(7, 30)
      "07.30 - 10.30" -> time(7, 30)
    """
    if not raw:
        return None

    s = str(raw).strip()
    if not s:
        return None

    m = re.search(r"(\d{1,2})[:.](\d{2})", s)
    if not m:
        return None

    try:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return datetime.strptime(f"{hh:02d}:{mm:02d}", "%H:%M").time()
    except Exception:
        return None

    return None


def _sync_booking_seats_to_trip_passengers(
    db: Session,
    booking_id: int,
    seat_nos: list[str],
) -> None:
    """
    Sync-ва FINAL seats към linked TripPassenger rows.

    Логика:
    1) първо търси rows по booking_id
    2) ако няма такива, пробва fallback по trip_id + external_id
       и автоматично ги link-ва към booking-а
    3) записва seat в manual_seat_no, ако полето съществува
    """
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        return

    resolved_trip_id = booking.trip_id or _resolve_booking_trip_id(db, booking)
    ext_key = _booking_external_id_key(booking)

    passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking_id)
        .order_by(TripPassenger.id.asc())
        .all()
    )

    if not passengers and resolved_trip_id and ext_key:
        candidates = (
            db.query(TripPassenger)
            .filter(TripPassenger.trip_id == resolved_trip_id)
            .all()
        )

        temp_booking_map = {booking.id: booking}
        matched: list[TripPassenger] = []

        for p in candidates:
            p_ext_key = _trip_passenger_external_id_key(
                p,
                booking_by_id=temp_booking_map,
            )
            if p_ext_key == ext_key:
                matched.append(p)

        matched = sorted(matched, key=_trip_passenger_sort_key)

        for p in matched:
            if not getattr(p, "booking_id", None):
                p.booking_id = booking.id

        passengers = matched

    if not passengers:
        return

    normalized: list[str] = []
    seen = set()

    for seat in seat_nos or []:
        s = (seat or "").strip()
        if s and s not in seen:
            normalized.append(s)
            seen.add(s)

    for idx, p in enumerate(passengers):
        if resolved_trip_id:
            p.trip_id = resolved_trip_id

        seat_value = normalized[idx] if idx < len(normalized) else None

        if hasattr(p, "manual_seat_no"):
            p.manual_seat_no = seat_value
        else:
            p.seat_no = seat_value

def _sync_booking_seat_to_trip_passengers(
    db: Session,
    booking_id: int,
    seat_no: str | None,
) -> None:
    """
    Backward-compatible wrapper.
    """
    seats = [seat_no] if seat_no else []
    _sync_booking_seats_to_trip_passengers(db, booking_id, seats)

def _pick_free_service_seats(
    booking: Booking,
    taken_seats: set[str],
    count: int,
    preferred_first: str | None = None,
) -> list[str]:
    """
    Връща count на брой свободни места.
    Ако има preferred_first и то е валидно/свободно, слага го първо.
    """
    chosen: list[str] = []
    allowed = set(_service_default_seat_map(booking))

    if preferred_first:
        preferred_first = str(preferred_first).strip()
        if preferred_first and preferred_first in allowed and preferred_first not in taken_seats:
            chosen.append(preferred_first)

    for seat_no in _service_default_seat_map(booking):
        if preferred_first and seat_no == preferred_first:
            continue
        if seat_no in taken_seats:
            continue
        chosen.append(seat_no)
        if len(chosen) >= count:
            break

    return chosen[:count]


def _apply_booking_seat_assignment(
    db: Session,
    booking: Booking,
    seat_nos: list[str],
    selection_mode: str,
) -> list[str]:
    """
    Записва всички seat rows за booking-а и ги sync-ва към TripPassenger.
    """
    resolved_trip_id = getattr(booking, "trip_id", None) or _resolve_booking_trip_id(db, booking)
    if resolved_trip_id:
        booking.trip_id = resolved_trip_id

    normalized: list[str] = []
    seen = set()

    for seat in seat_nos:
        s = str(seat or "").strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        normalized.append(s)

    required_count = max(_booking_passenger_count(db, booking), len(normalized), 1)
    rows = _ensure_booking_seat_rows(db, booking, required_count)

    for idx, row in enumerate(rows):
        row.trip_id = getattr(booking, "trip_id", None)
        if idx < len(normalized):
            row.seat_no = normalized[idx]
            row.is_final = True
            row.selection_mode = selection_mode
        else:
            row.seat_no = None
            row.is_final = False
            row.selection_mode = selection_mode

    _sync_booking_seats_to_trip_passengers(db, booking.id, normalized)
    return normalized



def _sync_admin_passenger_seat_to_booking_seat(
    db: Session,
    passenger: TripPassenger,
    seat_no: str,
) -> None:
    """
    Когато админ сменя място директно върху TripPassenger,
    синхронизираме и BookingSeat row-а.

    Без това:
      - admin dashboard вижда мястото
      - Seat Map го вижда частично
      - portal / ticket / booking final seats може да останат стари

    С това:
      - TripPassenger.manual_seat_no
      - BookingSeat.seat_no
      - portal seat state
      - ticket seat logic

    остават в синхрон.
    """
    booking_id = getattr(passenger, "booking_id", None)
    if not booking_id:
        return

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        return

    resolved_trip_id = (
        getattr(booking, "trip_id", None)
        or getattr(passenger, "trip_id", None)
        or _resolve_booking_trip_id(db, booking)
    )

    if resolved_trip_id:
        booking.trip_id = resolved_trip_id
        passenger.trip_id = resolved_trip_id

    linked_passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking.id)
        .order_by(TripPassenger.id.asc())
        .all()
    )

    linked_passengers = sorted(linked_passengers, key=_trip_passenger_sort_key)

    passenger_index = 0
    for idx, p in enumerate(linked_passengers):
        if int(getattr(p, "id", 0) or 0) == int(getattr(passenger, "id", 0) or 0):
            passenger_index = idx
            break

    required_count = max(
        _booking_passenger_count(db, booking),
        len(linked_passengers),
        passenger_index + 1,
        1,
    )

    rows = _ensure_booking_seat_rows(db, booking, required_count)
    rows = sorted(rows, key=lambda r: int(getattr(r, "id", 0) or 0))

    target_row = rows[passenger_index]
    target_row.trip_id = resolved_trip_id
    target_row.seat_no = str(seat_no or "").strip() or None
    target_row.is_final = bool(target_row.seat_no)
    target_row.selection_mode = "admin_dashboard"

    # Ако има linked passengers със seats, пазим ги синхронизирани към BookingSeat.
    # Това НЕ трие други съществуващи seat rows, а само допълва/поправя съответните индекси.
    for idx, p in enumerate(linked_passengers):
        if idx >= len(rows):
            break

        p_seat = _effective_trip_passenger_seat(p)
        p_seat = str(p_seat or "").strip()

        if not p_seat:
            continue

        rows[idx].trip_id = resolved_trip_id
        rows[idx].seat_no = p_seat
        rows[idx].is_final = True

        if not getattr(rows[idx], "selection_mode", None):
            rows[idx].selection_mode = "admin_dashboard"

    db.flush()


def _resolve_booking_trip_id(db: Session, booking: Booking) -> int | None:
    """
    Осигурява booking.trip_id.

    Логика:
    1. ако booking.trip_id вече е наличен -> връща го
    2. ако няма -> пробва rematch service
    3. ако още няма -> пробва да вземе trip_id от linked TripPassenger
    4. ако още няма -> пробва директен match по route + booking_date
    """
    if booking.trip_id:
        return booking.trip_id

    # 1) service rematch
    try:
        rematch_booking_to_trip(db, booking.id)
        db.flush()
        db.refresh(booking)
    except Exception:
        pass

    if booking.trip_id:
        return booking.trip_id

    # 2) fallback през linked passengers
    linked_p = (
        db.query(TripPassenger)
        .filter(
            TripPassenger.booking_id == booking.id,
            TripPassenger.trip_id.isnot(None),
        )
        .order_by(TripPassenger.id.asc())
        .first()
    )

    if linked_p and linked_p.trip_id:
        booking.trip_id = linked_p.trip_id
        db.flush()
        return booking.trip_id

    # 3) direct DB fallback: match по route + booking_date
    route_from = (booking.route_from or "").strip().lower()
    route_to = (booking.route_to or "").strip().lower()
    booking_date = booking.booking_date

    if route_from and route_to and booking_date:
        trip = (
            db.query(Trip)
            .filter(
                func.lower(func.coalesce(Trip.route_from, "")) == route_from,
                func.lower(func.coalesce(Trip.route_to, "")) == route_to,
                func.date(Trip.date_time) == booking_date,
            )
            .order_by(Trip.date_time.asc(), Trip.id.asc())
            .first()
        )

        if trip:
            booking.trip_id = trip.id
            db.flush()
            return booking.trip_id

    return None


def _norm_service_part(value: str | None) -> str:
    if not value:
        return ""
    s = str(value).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _booking_service_key(db_or_booking, booking: Booking | None = None):
    """
    Backward-compatible service key helper.

    Поддържа и двата варианта:
      _booking_service_key(booking)
      _booking_service_key(db, booking)

    Приоритет:
      1) ако booking има trip_id -> service key е по trip_id
      2) ако има db, пробва resolve на trip_id
      3) fallback към старото: booking_date + direction_code
    """
    if booking is None:
        db = None
        booking = db_or_booking
    else:
        db = db_or_booking

    if not booking:
        return None

    trip_id = getattr(booking, "trip_id", None)

    if not trip_id and db is not None:
        try:
            trip_id = _resolve_booking_trip_id(db, booking)
            if trip_id:
                booking.trip_id = trip_id
        except Exception:
            trip_id = getattr(booking, "trip_id", None)

    if trip_id:
        return ("trip", str(int(trip_id)))

    booking_date = getattr(booking, "booking_date", None)
    direction_code = _booking_direction_code(booking)

    if booking_date is None or direction_code not in {"IK", "KI"}:
        return None

    if isinstance(booking_date, datetime):
        date_key = booking_date.date().isoformat()
    else:
        date_key = booking_date.isoformat()

    return (date_key, direction_code)


def _service_taken_seats(
    db: Session,
    booking: Booking,
    exclude_booking_id: int | None = None,
) -> set[str]:
    """
    Взима всички заети места за същия service/trip.

    ВАЖНО:
    Комбинира:
      1) BookingSeat final seats - portal/admin booking seat rows
      2) TripPassenger effective seats - manual_seat_no/seat_no от admin dashboard

    Това оправя проблема:
    - админът сменя място в Dashboard чрез TripPassenger.manual_seat_no
    - portal/seats/state вече вижда тази промяна
    - Seat Map refresh показва новото заето място веднага
    """
    if not booking:
        return set()

    resolved_trip_id = getattr(booking, "trip_id", None)

    if not resolved_trip_id:
        try:
            resolved_trip_id = _resolve_booking_trip_id(db, booking)
            if resolved_trip_id:
                booking.trip_id = resolved_trip_id
                db.flush()
        except Exception:
            resolved_trip_id = getattr(booking, "trip_id", None)

    service_key = _booking_service_key(db, booking)
    if not service_key:
        return set()

    taken: set[str] = set()

    current_external_id = _booking_external_id_key(booking)

    # -------------------------------------------------------
    # 1) BookingSeat final seats
    # -------------------------------------------------------
    seat_rows = (
        db.query(BookingSeat, Booking)
        .join(Booking, Booking.id == BookingSeat.booking_id)
        .filter(
            BookingSeat.is_final == True,
            BookingSeat.seat_no.isnot(None),
        )
        .all()
    )

    for seat_row, other_booking in seat_rows:
        other_booking_id = getattr(other_booking, "id", None)

        if (
            exclude_booking_id is not None
            and other_booking_id is not None
            and int(other_booking_id) == int(exclude_booking_id)
        ):
            continue

        include_row = False

        seat_trip_id = getattr(seat_row, "trip_id", None)
        if resolved_trip_id and seat_trip_id and int(seat_trip_id) == int(resolved_trip_id):
            include_row = True

        if not include_row:
            try:
                other_key = _booking_service_key(db, other_booking)
            except Exception:
                other_key = None

            if other_key == service_key:
                include_row = True

        if not include_row:
            continue

        seat_no = str(getattr(seat_row, "seat_no", "") or "").strip()
        if seat_no:
            taken.add(seat_no)

    # -------------------------------------------------------
    # 2) TripPassenger seats from admin/manual dashboard
    # -------------------------------------------------------
    passenger_rows: list[TripPassenger] = []

    if resolved_trip_id:
        passenger_rows = (
            db.query(TripPassenger)
            .filter(TripPassenger.trip_id == resolved_trip_id)
            .all()
        )
    else:
        # Legacy fallback: passengers linked to bookings in same service
        linked_rows = (
            db.query(TripPassenger, Booking)
            .join(Booking, Booking.id == TripPassenger.booking_id)
            .all()
        )

        for p, b in linked_rows:
            try:
                if _booking_service_key(db, b) == service_key:
                    passenger_rows.append(p)
            except Exception:
                continue

    passenger_booking_ids = {
        int(getattr(p, "booking_id"))
        for p in passenger_rows
        if getattr(p, "booking_id", None)
    }

    passenger_booking_by_id: dict[int, Booking] = {}
    if passenger_booking_ids:
        passenger_bookings = (
            db.query(Booking)
            .filter(Booking.id.in_(list(passenger_booking_ids)))
            .all()
        )
        passenger_booking_by_id = {int(b.id): b for b in passenger_bookings}

    for p in passenger_rows:
        p_booking_id = getattr(p, "booking_id", None)

        if (
            exclude_booking_id is not None
            and p_booking_id is not None
            and int(p_booking_id) == int(exclude_booking_id)
        ):
            continue

        # Ако има unlinked TripPassenger със същия external_id като текущия booking,
        # не трябва да блокира собственото място на клиента в portal.
        if exclude_booking_id is not None and current_external_id:
            try:
                p_external_id = _trip_passenger_external_id_key(
                    p,
                    booking_by_id=passenger_booking_by_id,
                )
            except Exception:
                p_external_id = None

            if p_external_id and str(p_external_id).strip() == str(current_external_id).strip():
                continue

        seat_no = _effective_trip_passenger_seat(p)
        seat_no = str(seat_no or "").strip()

        if seat_no:
            taken.add(seat_no)

    return taken

def _ensure_booking_has_service(db_or_booking, booking: Booking | None = None) -> bool:
    """
    Backward-compatible helper.

    Поддържа и двата начина на извикване:
      _ensure_booking_has_service(booking)
      _ensure_booking_has_service(db, booking)
    """
    if booking is None:
        db = None
        booking = db_or_booking
    else:
        db = db_or_booking

    return _booking_service_key(db, booking) is not None




def _booking_service_label(booking: Booking) -> str:
    booking_date = getattr(booking, "booking_date", None)

    if isinstance(booking_date, datetime):
        date_str = booking_date.strftime("%d.%m.%Y")
    elif booking_date:
        try:
            date_str = booking_date.strftime("%d.%m.%Y")
        except Exception:
            date_str = str(booking_date)
    else:
        date_str = "—"

    bus_from = getattr(booking, "bus_from", None) or "—"
    bus_to = getattr(booking, "bus_to", None) or "—"

    return f"{date_str} • {bus_from} → {bus_to}"


def _portal_ticket_payload(
    booking: Booking,
    selected_seat: str,
    passenger: TripPassenger | None = None,
    trip: Trip | None = None,
) -> dict:
    booking_date = getattr(booking, "booking_date", None)
    if isinstance(booking_date, datetime):
        booking_date_iso = booking_date.date().isoformat()
    elif booking_date:
        try:
            booking_date_iso = booking_date.isoformat()
        except Exception:
            booking_date_iso = str(booking_date)
    else:
        booking_date_iso = None

    trip_date_iso = None
    if trip and getattr(trip, "date_time", None):
        try:
            trip_date_iso = trip.date_time.date().isoformat()
        except Exception:
            trip_date_iso = str(trip.date_time)

    passenger_name = f"{booking.first_name or ''} {booking.last_name or ''}".strip()
    payment_status = getattr(booking, "payment_status", None)
    payment_status_norm = str(payment_status or "").strip().lower()

    payload = {
        "type": "boarding_ticket",
        "version": 1,

        "booking_id": booking.id,
        "passenger_id": getattr(passenger, "id", None),

        "trip_id": booking.trip_id,
        "external_id": booking.external_id,

        "first_name": booking.first_name,
        "last_name": booking.last_name,
        "passenger_name": passenger_name,

        "booking_date": booking_date_iso,
        "trip_date": trip_date_iso,

        "route_from": booking.route_from,
        "route_to": booking.route_to,
        "direction": f"{booking.route_from or '-'} -> {booking.route_to or '-'}",

        "bus_from": booking.bus_from,
        "bus_to": booking.bus_to,

        "seat_no": selected_seat,

        "paid": payment_status_norm in {"paid", "approved", "payment_approved"},
        "payment_status": payment_status,
        "booking_status": getattr(booking, "booking_status", None),
    }

    payload["sig"] = _sign_ticket_payload(payload)
    return payload


def _norm_payment_method(value: str | None) -> str:
    v = (value or "").strip().lower()

    if v in {"cash", "cash payment", "gotivka", "готівка", "налични", "cash on bus"}:
        return "cash"

    if v in {"bank", "bank transfer", "wire", "iban"}:
        return "bank"

    if v in {"paypal", "pay pal", "pay-pal"}:
        return "paypal"

    return v or ""


def _normalize_payment_method(value: str | None) -> str:
    # backward-compatible alias
    return _norm_payment_method(value)


def _booking_departure_dt(booking: Booking) -> datetime | None:
    booking_date = getattr(booking, "booking_date", None)
    first_time = _extract_first_departure_time(getattr(booking, "time_range_raw", None))

    if not booking_date:
        return None

    try:
        if isinstance(booking_date, datetime):
            booking_date = booking_date.date()

        if first_time:
            return datetime.combine(booking_date, first_time)

        return datetime.combine(booking_date, datetime.min.time())
    except Exception:
        return None


def _hours_until_departure(booking: Booking) -> float | None:
    dep = _booking_departure_dt(booking)
    if not dep:
        return None

    now_vienna = _vienna_now_naive()
    return (dep - now_vienna).total_seconds() / 3600.0


def _can_upload_payment_proof(booking: Booking) -> bool:
    if _booking_is_cancelled_or_pending_cancellation(booking):
        return False

    method = _norm_payment_method(getattr(booking, "payment_method", None))
    return method in {"bank", "paypal"}


def _can_portal_select_seat(booking: Booking) -> bool:
    if _booking_is_cancelled_or_pending_cancellation(booking):
        return False

    method = _norm_payment_method(getattr(booking, "payment_method", None))
    if method not in {"bank", "paypal"}:
        return False

    if getattr(booking, "payment_status", None) != "paid":
        return False

    if not _ensure_booking_has_service(booking):
        return False

    return True


def _can_portal_change_seat(booking: Booking) -> bool:
    if _booking_is_cancelled_or_pending_cancellation(booking):
        return False

    if not _can_portal_select_seat(booking):
        return False

    selected_seat = _booking_selected_seat(booking)
    if not selected_seat:
        return False

    hours_left = _hours_until_departure(booking)
    if hours_left is None:
        return True

    return hours_left >= 24


def _can_change_seat(booking: Booking) -> bool:
    # backward-compatible alias
    return _can_portal_change_seat(booking)


def _cash_notice_active(booking: Booking) -> bool:
    return _norm_payment_method(getattr(booking, "payment_method", None)) == "cash"

def _booking_departure_dt_for_dispatch(db: Session, booking: Booking) -> datetime | None:
    """
    За dispatcher window НЕ ползваме trip.date_time.
    Ползваме:
      booking.booking_date + първия час от booking.time_range_raw

    Пример:
      19.04.2026 + "07:30 - 10:30" -> 19.04.2026 07:30
    """
    booking_date = getattr(booking, "booking_date", None)
    first_time = _extract_first_departure_time(getattr(booking, "time_range_raw", None))

    if not booking_date or not first_time:
        return None

    try:
        if isinstance(booking_date, datetime):
            booking_date = booking_date.date()

        return datetime.combine(booking_date, first_time)
    except Exception:
        return None


def _dispatch_hours_until_departure(db: Session, booking: Booking) -> float | None:
    dep = _booking_departure_dt_for_dispatch(db, booking)
    if not dep:
        return None

    now_vienna = _vienna_now_naive()
    return (dep - now_vienna).total_seconds() / 3600.0


def _can_dispatch_assign_cash_seat(db: Session, booking: Booking) -> bool:
    """
    Dispatcher/admin може да assign-ва seat за CASH booking само:
    - ако е cash
    - ако booking е confirmed
    - ако има service
    - ако има trip/departure datetime
    - ако сме в прозорец 24h до 10h преди тръгване
    """
    if _booking_is_cancelled_or_pending_cancellation(booking):
        return False

    if _norm_payment_method(getattr(booking, "payment_method", None)) != "cash":
        return False

    if getattr(booking, "booking_status", None) != "confirmed":
        return False

    if not _ensure_booking_has_service(booking):
        return False

    hours_left = _dispatch_hours_until_departure(db, booking)
    if hours_left is None:
        return False

    return 10 <= hours_left <= 24



def _cash_booking_confirmed(booking: Booking) -> bool:
    return _cash_notice_active(booking) and (getattr(booking, "booking_status", None) == "confirmed")


def _can_portal_view_ticket(booking: Booking) -> bool:
    if _booking_is_cancelled_or_pending_cancellation(booking):
        return False

    if not _ensure_booking_has_service(booking):
        return False

    if _cash_notice_active(booking):
        return _cash_booking_confirmed(booking)

    selected_seat = _booking_selected_seat(booking)
    return getattr(booking, "payment_status", None) == "paid" and bool(selected_seat)


def _ticket_qr_available(booking: Booking) -> bool:
    if _booking_is_cancelled_or_pending_cancellation(booking):
        return False

    if not _ensure_booking_has_service(booking):
        return False

    selected_seat = _booking_selected_seat(booking)
    if not selected_seat:
        return False

    if _cash_notice_active(booking):
        return _cash_booking_confirmed(booking)

    return getattr(booking, "payment_status", None) == "paid"


def _parse_ticket_payload(raw: str) -> dict | None:
    """
    Очаква JSON payload от /portal/ticket/qr.
    Връща нормализиран dict или None.
    """

    raw = (raw or "").strip()
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    if data.get("type") != "boarding_ticket":
        return None

    def _as_int(v):
        if v is None or v == "":
            return None
        try:
            return int(v)
        except Exception:
            return None

    payload = {
        "type": "boarding_ticket",
        "version": _as_int(data.get("version")) or 1,

        "booking_id": _as_int(data.get("booking_id")),
        "passenger_id": _as_int(data.get("passenger_id")),
        "trip_id": _as_int(data.get("trip_id")),

        "external_id": (data.get("external_id") or "").strip() or None,

        "first_name": (data.get("first_name") or "").strip() or None,
        "last_name": (data.get("last_name") or "").strip() or None,
        "passenger_name": (data.get("passenger_name") or "").strip() or None,

        "booking_date": (data.get("booking_date") or "").strip() or None,
        "trip_date": (data.get("trip_date") or "").strip() or None,

        "route_from": (data.get("route_from") or "").strip() or None,
        "route_to": (data.get("route_to") or "").strip() or None,
        "direction": (data.get("direction") or "").strip() or None,

        "bus_from": (data.get("bus_from") or "").strip() or None,
        "bus_to": (data.get("bus_to") or "").strip() or None,

        "seat_no": str(data.get("seat_no") or "").strip() or None,

        "paid": bool(data.get("paid", False)),
        "payment_status": (data.get("payment_status") or "").strip() or None,
        "booking_status": (data.get("booking_status") or "").strip() or None,

        "sig": (data.get("sig") or "").strip() or None,
    }

    # Минимална валидност
    if not payload["booking_id"] and not payload["external_id"]:
        return None

    # Ако има подпис, проверяваме го.
    # Така старите QR без sig още ще работят.
    if payload.get("sig"):
        if not _verify_ticket_payload_signature(payload):
            return None

    # Ако искаш СТРОГО да приемаш само подписани QR, ползвай това вместо горния блок:
    # if not payload.get("sig"):
    #     return None
    # if not _verify_ticket_payload_signature(payload):
    #     return None

    return payload


def _check_in_by_ticket_payload(db: Session, payload: dict) -> tuple[bool, str, Booking | None, list[TripPassenger]]:
    """
    Check-in по QR payload.

    Валидира:
      - booking_id
      - external_id
      - seat_no

    Маркира linked TripPassenger rows като checked_in=True.
    """
    booking_id = payload.get("booking_id")
    external_id = payload.get("external_id")
    seat_no = (payload.get("seat_no") or "").strip()

    if not booking_id:
        return False, "Missing booking_id", None, []

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        return False, "Booking not found", None, []

    if external_id is not None and booking.external_id != external_id:
        return False, "External ID mismatch", booking, []

    selected_seat = _booking_selected_seat(booking)
    if not selected_seat:
        return False, "Booking has no final seat", booking, []

    if seat_no and selected_seat != seat_no:
        return False, "Seat mismatch", booking, []

    passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking.id)
        .order_by(TripPassenger.id.asc())
        .all()
    )

    if not passengers:
        return False, "No linked passengers for booking", booking, []

    for p in passengers:
        p.checked_in = True

    db.flush()
    return True, "Passenger checked in successfully", booking, passengers

def _ensure_pdf_unicode_fonts() -> tuple[str, str]:
    """
    Регистрира Unicode TTF шрифт за кирилица.
    Връща (regular_font_name, bold_font_name).
    """
    regular_name = "TicketUnicode"
    bold_name = "TicketUnicode-Bold"

    registered = set(pdfmetrics.getRegisteredFontNames())
    if regular_name in registered and bold_name in registered:
        return regular_name, bold_name

    candidates = [
        # app-local fonts (най-добре)
        (
            APP_DIR / "fonts" / "DejaVuSans.ttf",
            APP_DIR / "fonts" / "DejaVuSans-Bold.ttf",
        ),
        (
            APP_DIR / "static" / "fonts" / "DejaVuSans.ttf",
            APP_DIR / "static" / "fonts" / "DejaVuSans-Bold.ttf",
        ),

        # Windows
        (
            Path(r"C:\Windows\Fonts\arial.ttf"),
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
        ),
        (
            Path(r"C:\Windows\Fonts\calibri.ttf"),
            Path(r"C:\Windows\Fonts\calibrib.ttf"),
        ),

        # Linux common
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        ),
    ]

    for reg_path, bold_path in candidates:
        if reg_path.exists() and bold_path.exists():
            pdfmetrics.registerFont(TTFont(regular_name, str(reg_path)))
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
            return regular_name, bold_name

    raise RuntimeError(
        "No Unicode TTF font found for PDF generation. "
        "Add DejaVuSans.ttf and DejaVuSans-Bold.ttf to app/fonts/ "
        "or install a system font with Cyrillic support."
    )


def _effective_passenger_seat(p: TripPassenger) -> str:
    return _effective_text(
        getattr(p, "manual_seat_no", None),
        getattr(p, "seat_no", None),
    ).strip()


def _ensure_driver_boarding_state_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS driver_boarding_state (
            passenger_id INTEGER PRIMARY KEY,
            trip_id INTEGER NOT NULL,
            booking_id INTEGER,
            boarding_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            refused_reason TEXT,
            last_qr_payload TEXT,
            oebb_checked BOOLEAN NOT NULL DEFAULT FALSE,
            cash_collected_amount NUMERIC(12,2),
            cash_collected_currency VARCHAR(10),
            updated_at TIMESTAMP NOT NULL,
            updated_by VARCHAR(50)
        )
    """))
    db.flush()


def _get_driver_boarding_state_map(db: Session, trip_id: int) -> dict[int, dict]:
    _ensure_driver_boarding_state_table(db)

    rows = db.execute(
        text("""
            SELECT
                passenger_id,
                trip_id,
                booking_id,
                boarding_status,
                refused_reason,
                last_qr_payload,
                oebb_checked,
                cash_collected_amount,
                cash_collected_currency,
                updated_at,
                updated_by
            FROM driver_boarding_state
            WHERE trip_id = :trip_id
        """),
        {"trip_id": trip_id},
    ).mappings().all()

    out: dict[int, dict] = {}
    for r in rows:
        pid = int(r["passenger_id"])
        out[pid] = {
            "boarding_status": r["boarding_status"] or "pending",
            "refused_reason": r["refused_reason"],
            "last_qr_payload": r["last_qr_payload"],
            "oebb_checked": bool(r["oebb_checked"]),
            "cash_collected_amount": float(r["cash_collected_amount"]) if r["cash_collected_amount"] is not None else None,
            "cash_collected_currency": r["cash_collected_currency"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            "updated_by": r["updated_by"],
        }
    return out


def _get_driver_boarding_state_row(db: Session, passenger_id: int) -> dict | None:
    _ensure_driver_boarding_state_table(db)

    row = db.execute(
        text("""
            SELECT
                passenger_id,
                trip_id,
                booking_id,
                boarding_status,
                refused_reason,
                last_qr_payload,
                oebb_checked,
                cash_collected_amount,
                cash_collected_currency,
                updated_at,
                updated_by
            FROM driver_boarding_state
            WHERE passenger_id = :passenger_id
        """),
        {"passenger_id": passenger_id},
    ).mappings().first()

    if not row:
        return None

    return {
        "boarding_status": row["boarding_status"] or "pending",
        "refused_reason": row["refused_reason"],
        "last_qr_payload": row["last_qr_payload"],
        "oebb_checked": bool(row["oebb_checked"]),
        "cash_collected_amount": float(row["cash_collected_amount"]) if row["cash_collected_amount"] is not None else None,
        "cash_collected_currency": row["cash_collected_currency"],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "updated_by": row["updated_by"],
    }


def _upsert_driver_boarding_state(
    db: Session,
    passenger_id: int,
    trip_id: int,
    booking_id: int | None,
    boarding_status: str,
    refused_reason: str | None,
    last_qr_payload: str | None,
    oebb_checked: bool,
    cash_collected_amount: float | None,
    cash_collected_currency: str | None,
    updated_by: str = "driver",
) -> None:
    _ensure_driver_boarding_state_table(db)

    db.execute(
        text("""
            INSERT INTO driver_boarding_state (
                passenger_id,
                trip_id,
                booking_id,
                boarding_status,
                refused_reason,
                last_qr_payload,
                oebb_checked,
                cash_collected_amount,
                cash_collected_currency,
                updated_at,
                updated_by
            )
            VALUES (
                :passenger_id,
                :trip_id,
                :booking_id,
                :boarding_status,
                :refused_reason,
                :last_qr_payload,
                :oebb_checked,
                :cash_collected_amount,
                :cash_collected_currency,
                :updated_at,
                :updated_by
            )
            ON CONFLICT (passenger_id) DO UPDATE SET
                trip_id = EXCLUDED.trip_id,
                booking_id = EXCLUDED.booking_id,
                boarding_status = EXCLUDED.boarding_status,
                refused_reason = EXCLUDED.refused_reason,
                last_qr_payload = EXCLUDED.last_qr_payload,
                oebb_checked = EXCLUDED.oebb_checked,
                cash_collected_amount = EXCLUDED.cash_collected_amount,
                cash_collected_currency = EXCLUDED.cash_collected_currency,
                updated_at = EXCLUDED.updated_at,
                updated_by = EXCLUDED.updated_by
        """),
        {
            "passenger_id": passenger_id,
            "trip_id": trip_id,
            "booking_id": booking_id,
            "boarding_status": boarding_status,
            "refused_reason": refused_reason,
            "last_qr_payload": last_qr_payload,
            "oebb_checked": oebb_checked,
            "cash_collected_amount": cash_collected_amount,
            "cash_collected_currency": cash_collected_currency,
            "updated_at": datetime.utcnow(),
            "updated_by": updated_by,
        },
    )
    db.flush()



def _resolve_trip_passenger_by_ticket_payload(
    db: Session,
    payload: dict,
) -> tuple[Booking | None, TripPassenger | None]:
    if not payload:
        return None, None

    # ако има подпис и той е невалиден -> режем QR-а
    if payload.get("sig") and not _verify_ticket_payload_signature(payload):
        return None, None

    booking_id = payload.get("booking_id")
    passenger_id = payload.get("passenger_id")
    trip_id = payload.get("trip_id")
    external_id = payload.get("external_id")
    seat_no = (payload.get("seat_no") or "").strip()

    booking = None
    if booking_id:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking and external_id:
        booking = db.query(Booking).filter(Booking.external_id == external_id).first()

    if not booking:
        return None, None

    # 1) най-силен match: passenger_id
    if passenger_id:
        passenger = (
            db.query(TripPassenger)
            .filter(TripPassenger.id == passenger_id)
            .first()
        )
        if passenger:
            if booking.id and getattr(passenger, "booking_id", None) not in (None, booking.id):
                return booking, None
            if trip_id and getattr(passenger, "trip_id", None) not in (None, trip_id):
                return booking, None
            return booking, passenger

    # 2) booking_id match
    passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking.id)
        .order_by(TripPassenger.id.asc())
        .all()
    )

    # 3) fallback: external_id within trip
    if not passengers and booking.trip_id:
        ext_key = _booking_external_id_key(booking)
        if ext_key:
            candidates = (
                db.query(TripPassenger)
                .filter(TripPassenger.trip_id == booking.trip_id)
                .all()
            )
            matched = []
            booking_by_id = {booking.id: booking}
            for p in candidates:
                p_ext = _trip_passenger_external_id_key(p, booking_by_id=booking_by_id)
                if p_ext == ext_key:
                    matched.append(p)
            passengers = sorted(matched, key=_trip_passenger_sort_key)

    if not passengers:
        return booking, None

    # 4) seat match
    if seat_no:
        for p in passengers:
            if (_effective_passenger_seat(p) or "").strip() == seat_no:
                return booking, p

    # 5) ако няма seat match -> първия passenger
    return booking, passengers[0]


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

def _trip_passenger_sort_key(p: TripPassenger):
    return (
        _safe_int_passenger_no(
            _effective_text(
                getattr(p, "manual_passenger_no", None),
                getattr(p, "passenger_no", None),
            )
        ),
        int(getattr(p, "id", 0) or 0),
    )


def _build_trip_booking_seat_overlay(db: Session, trip_id: int) -> dict[int, str]:
    """
    Връща overlay map:
      passenger_id -> final booking seat

    Логика:
    - взимаме всички TripPassenger rows за trip-а, които имат booking_id
    - групираме ги по booking_id
    - взимаме final seats от BookingSeat
    - закачаме местата към passenger rows по стабилен ред
    """
    passengers = (
        db.query(TripPassenger)
        .filter(
            TripPassenger.trip_id == trip_id,
            TripPassenger.booking_id.isnot(None),
        )
        .all()
    )

    if not passengers:
        return {}

    grouped: dict[int, list[TripPassenger]] = {}
    booking_ids: set[int] = set()

    for p in passengers:
        bid = int(p.booking_id)
        grouped.setdefault(bid, []).append(p)
        booking_ids.add(bid)

    seat_rows = (
        db.query(BookingSeat.booking_id, BookingSeat.seat_no)
        .filter(
            BookingSeat.booking_id.in_(list(booking_ids)),
            BookingSeat.is_final == True,
            BookingSeat.seat_no.isnot(None),
        )
        .order_by(BookingSeat.booking_id.asc(), BookingSeat.id.asc())
        .all()
    )

    seats_by_booking: dict[int, list[str]] = {}
    for bid, seat_no in seat_rows:
        if bid is None or not seat_no:
            continue
        seats_by_booking.setdefault(int(bid), []).append(str(seat_no).strip())

    overlay: dict[int, str] = {}

    for booking_id, rows in grouped.items():
        final_seats = seats_by_booking.get(booking_id, [])
        if not final_seats:
            continue

        rows_sorted = sorted(rows, key=_trip_passenger_sort_key)

        for idx, p in enumerate(rows_sorted):
            if idx < len(final_seats):
                overlay[int(p.id)] = final_seats[idx]

    return overlay


def _passenger_to_api_dict(
    p: TripPassenger,
    trip: Trip | None = None,
    booking_seat_no: str | None = None,
) -> dict:
    effective_seat_no = booking_seat_no or _effective_text(
        getattr(p, "manual_seat_no", None),
        p.seat_no,
    )

    item = {
        "id": p.id,
        "uid": p.source_uid,
        "tripId": p.trip_id,

        "passengerNo": _effective_text(getattr(p, "manual_passenger_no", None), p.passenger_no),
        "fromCity": _effective_text(getattr(p, "manual_from_city", None), p.from_city),
        "toCity": _effective_text(getattr(p, "manual_to_city", None), p.to_city),
        "fullName": _effective_text(getattr(p, "manual_full_name", None), p.full_name),
        "seatNo": effective_seat_no,
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

        "bookingSeatNo": booking_seat_no,

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

def _booking_final_seats_map_for_trip(db: Session, trip_id: int) -> dict[int, list[str]]:
    """
    Връща booking_id -> [final seats...] за конкретен trip.
    Ползва BookingSeat, за да виждаме portal/admin seat assignment в trips_detail.
    """
    rows = (
        db.query(BookingSeat.booking_id, BookingSeat.seat_no)
        .filter(
            BookingSeat.trip_id == trip_id,
            BookingSeat.is_final == True,
            BookingSeat.seat_no.isnot(None),
        )
        .order_by(BookingSeat.booking_id.asc(), BookingSeat.id.asc())
        .all()
    )

    out: dict[int, list[str]] = {}
    for booking_id, seat_no in rows:
        if booking_id is None:
            continue
        seat_str = (seat_no or "").strip()
        if not seat_str:
            continue
        out.setdefault(int(booking_id), []).append(seat_str)

    for bid in list(out.keys()):
        unique = list(dict.fromkeys(out[bid]))
        unique.sort(key=_seat_sort_key)
        out[bid] = unique

    return out


def _build_trip_portal_overlay(
    db: Session,
    trip_id: int,
    passengers: list[TripPassenger],
) -> dict[int, dict]:
    """
    Overlay за trips/trips_detail:
    - seatNo идва от final BookingSeat
    - paymentApproved идва от Booking.payment_status == 'paid'

    ВАЖНО:
    Работи и ако TripPassenger.booking_id липсва,
    стига да може да се извади Unique ID от реда.
    """
    overlay: dict[int, dict] = {}

    if not passengers:
        return overlay

    direct_booking_ids = sorted({
        int(p.booking_id)
        for p in passengers
        if getattr(p, "booking_id", None)
    })

    booking_by_id: dict[int, Booking] = {}
    if direct_booking_ids:
        direct_bookings = (
            db.query(Booking)
            .filter(Booking.id.in_(direct_booking_ids))
            .all()
        )
        booking_by_id = {int(b.id): b for b in direct_bookings}

    passenger_ext_map: dict[int, str] = {}
    ext_keys: set[str] = set()

    for p in passengers:
        ext_key = _trip_passenger_external_id_key(
            p,
            booking_by_id=booking_by_id,
        )
        if ext_key:
            passenger_ext_map[int(p.id)] = ext_key
            ext_keys.add(ext_key)

    if not ext_keys:
        return overlay

    matched_bookings = (
        db.query(Booking)
        .filter(cast(Booking.external_id, String).in_(list(ext_keys)))
        .all()
    )

    booking_by_ext: dict[str, Booking] = {}
    for b in matched_bookings:
        ext_key = _booking_external_id_key(b)
        if ext_key and ext_key not in booking_by_ext:
            booking_by_ext[ext_key] = b

    booking_ids = [int(b.id) for b in booking_by_ext.values()]
    seats_by_booking_id: dict[int, list[str]] = {}

    if booking_ids:
        seat_rows = (
            db.query(BookingSeat.booking_id, BookingSeat.seat_no)
            .filter(
                BookingSeat.booking_id.in_(booking_ids),
                BookingSeat.is_final == True,
                BookingSeat.seat_no.isnot(None),
            )
            .order_by(BookingSeat.booking_id.asc(), BookingSeat.id.asc())
            .all()
        )

        for booking_id, seat_no in seat_rows:
            if booking_id is None or not seat_no:
                continue
            seats_by_booking_id.setdefault(int(booking_id), []).append(str(seat_no).strip())

    grouped_passengers: dict[str, list[TripPassenger]] = {}
    for p in passengers:
        ext_key = passenger_ext_map.get(int(p.id))
        if ext_key:
            grouped_passengers.setdefault(ext_key, []).append(p)

    for ext_key, pax_rows in grouped_passengers.items():
        booking = booking_by_ext.get(ext_key)
        if not booking:
            continue

        final_seats = seats_by_booking_id.get(int(booking.id), [])
        pax_rows_sorted = sorted(pax_rows, key=_trip_passenger_sort_key)
        paid_flag = (getattr(booking, "payment_status", None) == "paid")

        for idx, p in enumerate(pax_rows_sorted):
            ov: dict = {}

            if idx < len(final_seats):
                ov["seatNo"] = final_seats[idx]

            if paid_flag:
                ov["paymentApproved"] = True

            overlay[int(p.id)] = ov

    return overlay


def _driver_manifest_path(trip_id: int) -> Path:
    return DRIVER_MANIFESTS_DIR / f"trip_{int(trip_id)}.json"


def _read_driver_manifest(trip_id: int) -> dict | None:
    path = _driver_manifest_path(trip_id)
    if not path.exists():
        return None

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        return None

    return None


def _write_driver_manifest(trip_id: int, payload: dict) -> None:
    path = _driver_manifest_path(trip_id)
    tmp_path = path.with_suffix(".json.tmp")

    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _build_admin_trip_live_passengers(db: Session, trip_id: int) -> list[dict]:
    """
    Това е live/admin view на Trips:
    - базови TripPassenger редове
    - overlay от portal/admin booking seats
    - payment approved badge
    """
    trip = crud.get_trip(db, trip_id)
    if not trip:
        return []

    passengers = crud.list_passengers(db, trip_id)
    passengers = sorted(
        passengers,
        key=lambda p: (
            _safe_int_passenger_no(
                _effective_text(
                    getattr(p, "manual_passenger_no", None),
                    getattr(p, "passenger_no", None),
                )
            ),
            p.id,
        ),
    )

    portal_overlay = _build_trip_portal_overlay(db, trip_id, passengers)

    out: list[dict] = []
    for p in passengers:
        item = _passenger_to_api_dict(p, trip)

        ov = portal_overlay.get(p.id, {})

        seat_override = (ov.get("seatNo") or "").strip()
        if seat_override:
            item["seatNo"] = seat_override

        item["paymentApproved"] = bool(ov.get("paymentApproved"))
        item["paymentBadgeLabel"] = "PAYMENT APPROVED" if item["paymentApproved"] else ""

        out.append(item)

    decorate_passenger_dicts_with_bad_clients(db, out)
    return out



# =======================
# Driver merge helpers
# =======================
_UNIQUE_ID_RE = re.compile(r"\b(17\d{5,})\b")


def _extract_external_id_from_text(value) -> str | None:
    if value is None:
        return None

    s = str(value).strip()
    if not s:
        return None

    m = _UNIQUE_ID_RE.search(s)
    if not m:
        return None

    return m.group(1)


def _booking_customer_name(booking: Booking) -> str:
    name = f"{booking.first_name or ''} {booking.last_name or ''}".strip()
    return name or "—"


def _trip_passenger_external_id_key(
    p: TripPassenger,
    booking_by_id: dict[int, Booking] | None = None,
) -> str | None:
    """
    Опитва да намери booking-group key за TripPassenger.

    Приоритет:
    1) linked booking_id -> booking.external_id
    2) p.external_id (ако вече има такова поле в model-а)
    3) parse от source_uid
    4) parse от voucher/info полетата
    """
    booking_id = getattr(p, "booking_id", None)
    if booking_id and booking_by_id and int(booking_id) in booking_by_id:
        booking = booking_by_id[int(booking_id)]
        if getattr(booking, "external_id", None) is not None:
            return str(booking.external_id).strip()

    direct_external_id = getattr(p, "external_id", None)
    if direct_external_id is not None and str(direct_external_id).strip():
        return str(direct_external_id).strip()

    source_uid = getattr(p, "source_uid", None)
    found = _extract_external_id_from_text(source_uid)
    if found:
        return found

    found = _extract_external_id_from_text(getattr(p, "manual_voucher_raw", None))
    if found:
        return found

    found = _extract_external_id_from_text(getattr(p, "voucher_or_amount_raw", None))
    if found:
        return found

    return None


def _trip_passenger_merge_rank(p: TripPassenger) -> tuple:
    """
    По-голям rank = по-предпочитан ред за driver view.
    Идея:
    - предпочитаме Excel/manual rows
    - ако има duplicate от booking sync, държим по-богатия ред
    """
    booking_id = getattr(p, "booking_id", None)
    source_uid = (getattr(p, "source_uid", None) or "").strip()

    passenger_no = _effective_text(getattr(p, "manual_passenger_no", None), getattr(p, "passenger_no", None))
    full_name = _effective_text(getattr(p, "manual_full_name", None), getattr(p, "full_name", None))
    phone = _effective_text(getattr(p, "manual_phone", None), getattr(p, "phone", None))
    seat_no = _effective_text(getattr(p, "manual_seat_no", None), getattr(p, "seat_no", None))
    voucher_raw = _effective_text(getattr(p, "manual_voucher_raw", None), getattr(p, "voucher_or_amount_raw", None))

    return (
        1 if booking_id is None else 0,     # manual/excel rows first
        1 if source_uid else 0,
        1 if passenger_no else 0,
        1 if full_name else 0,
        1 if phone else 0,
        1 if seat_no else 0,
        1 if voucher_raw else 0,
        1 if getattr(p, "checked_in", False) else 0,
        1 if getattr(p, "paid", False) else 0,
        1 if getattr(p, "amount", None) not in (None, "") else 0,
        -(int(getattr(p, "id", 0) or 0)),   # по-старият id е по-предпочитан
    )


def build_driver_trip_projection(db: Session, trip_id: int) -> dict:
    """
    Обединява:
    - TripPassenger rows (Excel/manual/synced)
    - Booking rows

    Резултат:
    - passengers: deduped rows за driver table
    - booking_pending: booking groups, които още не са напълно покрити от passengers
    - display_total = deduped passengers + missing passengers
    """
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        return {
            "trip": None,
            "passengers": [],
            "booking_pending": [],
            "booking_coverage": [],
            "raw_passenger_count": 0,
            "kept_passenger_count": 0,
            "missing_passenger_count": 0,
            "display_total": 0,
        }

    raw_passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.trip_id == trip_id)
        .all()
    )

    bookings = (
        db.query(Booking)
        .filter(Booking.trip_id == trip_id)
        .order_by(Booking.id.asc())
        .all()
    )

    booking_by_id = {int(b.id): b for b in bookings}
    booking_by_external_id: dict[str, Booking] = {}

    for b in bookings:
        if getattr(b, "external_id", None) is None:
            continue
        key = str(b.external_id).strip()
        if key and key not in booking_by_external_id:
            booking_by_external_id[key] = b

    booking_ids = [int(b.id) for b in bookings]
    qty_map: dict[int, int] = {}

    if booking_ids:
        qty_rows = (
            db.query(
                BookingTicketLine.booking_id,
                func.coalesce(func.sum(BookingTicketLine.qty), 0),
            )
            .filter(BookingTicketLine.booking_id.in_(booking_ids))
            .group_by(BookingTicketLine.booking_id)
            .all()
        )
        qty_map = {
            int(bid): int(total_qty or 0)
            for bid, total_qty in qty_rows
            if bid is not None
        }

    grouped_passengers: dict[str, list[TripPassenger]] = {}
    unmatched_passengers: list[TripPassenger] = []

    for p in raw_passengers:
        ext_key = _trip_passenger_external_id_key(p, booking_by_id=booking_by_id)

        if ext_key and ext_key in booking_by_external_id:
            grouped_passengers.setdefault(ext_key, []).append(p)
        else:
            unmatched_passengers.append(p)

    kept_passengers: list[TripPassenger] = list(unmatched_passengers)
    booking_pending: list[dict] = []
    booking_coverage: list[dict] = []

    for ext_key, booking in booking_by_external_id.items():
        booking_rows = grouped_passengers.get(ext_key, [])
        wanted_count = _booking_passenger_count(db, booking, qty_map=qty_map)

        ranked_rows = sorted(
            booking_rows,
            key=_trip_passenger_merge_rank,
            reverse=True,
        )

        kept_rows = ranked_rows[:wanted_count]
        kept_passengers.extend(kept_rows)

        covered_count = len(kept_rows)
        missing_count = max(0, wanted_count - covered_count)
        duplicate_trimmed_count = max(0, len(booking_rows) - covered_count)

        coverage_item = {
            "booking_id": booking.id,
            "external_id": booking.external_id,
            "customer_name": _booking_customer_name(booking),
            "route": f"{booking.route_from or '—'} → {booking.route_to or '—'}",
            "wanted_count": wanted_count,
            "covered_count": covered_count,
            "missing_count": missing_count,
            "duplicate_trimmed_count": duplicate_trimmed_count,
            "payment_method": booking.payment_method or "—",
            "payment_status": booking.payment_status or "—",
            "booking_status": booking.booking_status or "—",
            "url": f"/admin/bookings/{booking.id}",
        }
        booking_coverage.append(coverage_item)

        if missing_count > 0:
            booking_pending.append(coverage_item)

    missing_passenger_count = sum(int(x["missing_count"]) for x in booking_pending)
    kept_passenger_count = len(kept_passengers)
    display_total = kept_passenger_count + missing_passenger_count

    return {
        "trip": trip,
        "passengers": kept_passengers,
        "booking_pending": booking_pending,
        "booking_coverage": booking_coverage,
        "raw_passenger_count": len(raw_passengers),
        "kept_passenger_count": kept_passenger_count,
        "missing_passenger_count": missing_passenger_count,
        "display_total": display_total,
    }



def _build_driver_trip_live_payload(db: Session, trip_id: int) -> dict:
    projection = build_driver_trip_projection(db, trip_id)
    trip = projection.get("trip")

    if not trip:
        raise HTTPException(404, "Trip not found")

    kept_passengers = sorted(
        list(projection.get("passengers") or []),
        key=_trip_passenger_sort_key,
    )

    portal_overlay = _build_trip_portal_overlay(db, trip_id, kept_passengers)
    boarding_state_map = _get_driver_boarding_state_map(db, trip_id)

    out: list[dict] = []
    for p in kept_passengers:
        item = _passenger_to_api_dict(p, trip)

        ov = portal_overlay.get(int(p.id), {})
        seat_override = (ov.get("seatNo") or "").strip()
        if seat_override:
            item["seatNo"] = seat_override

        item["paymentApproved"] = bool(ov.get("paymentApproved"))
        item["paymentBadgeLabel"] = "PAYMENT APPROVED" if item["paymentApproved"] else ""

        state = boarding_state_map.get(int(p.id), {})
        item["boardingStatus"] = state.get("boarding_status") or ("checked_in" if item.get("checkedIn") else "pending")
        item["refusedReason"] = state.get("refused_reason")
        item["oebbChecked"] = bool(state.get("oebb_checked")) or bool(item.get("oebb"))
        item["cashCollectedAmount"] = state.get("cash_collected_amount")
        item["cashCollectedCurrency"] = state.get("cash_collected_currency")

        out.append(item)

    decorate_passenger_dicts_with_bad_clients(db, out)

    return {
        "tripId": trip.id,
        "routeFrom": trip.route_from,
        "routeTo": trip.route_to,
        "tripDate": trip.date_time.isoformat() if trip.date_time else None,
        "passengers": out,
        "displayTotal": int(projection.get("display_total") or 0),
        "rawPassengerCount": int(projection.get("raw_passenger_count") or 0),
        "keptPassengerCount": int(projection.get("kept_passenger_count") or 0),
        "missingPassengerCount": int(projection.get("missing_passenger_count") or 0),
        "bookingPending": list(projection.get("booking_pending") or []),
        "bookingCoverage": list(projection.get("booking_coverage") or []),
    }


def _ensure_driver_manifest_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS driver_trip_manifests (
            trip_id INTEGER PRIMARY KEY,
            manifest_json TEXT NOT NULL,
            published_at TIMESTAMP NOT NULL,
            published_by VARCHAR(50)
        )
    """))
    db.flush()


def _build_admin_trip_passengers_payload(db: Session, trip_id: int) -> list[dict]:
    """
    Това е snapshot-ът, който admin публикува към driver.
    Източникът е admin trip_detail списъкът.
    """
    passengers = crud.list_passengers(db, trip_id)
    passengers = sorted(
        passengers,
        key=lambda p: (
            _safe_int_passenger_no(
                _effective_text(
                    getattr(p, "manual_passenger_no", None),
                    getattr(p, "passenger_no", None),
                )
            ),
            p.id,
        ),
    )

    portal_overlay = _build_trip_portal_overlay(db, trip_id, passengers)

    out: list[dict] = []
    for p in passengers:
        item = _passenger_to_api_dict(p)

        ov = portal_overlay.get(p.id, {})

        seat_override = (ov.get("seatNo") or "").strip()
        if seat_override:
            item["seatNo"] = seat_override

        item["paymentApproved"] = bool(ov.get("paymentApproved"))
        item["paymentBadgeLabel"] = "PAYMENT APPROVED" if item["paymentApproved"] else ""

        out.append(item)

    decorate_passenger_dicts_with_bad_clients(db, out)
    return out


def _build_driver_manifest_payload(db: Session, trip_id: int) -> dict:
    """
    Snapshot payload за publish към driver manifests table.

    Базира се на live driver projection, за да няма разлика между
    driver view и публикувания manifest.
    """
    payload = _build_driver_trip_live_payload(db, trip_id)
    payload["publishedAt"] = datetime.utcnow().isoformat()
    payload["publishedBy"] = "admin"
    return payload

def _save_driver_manifest(
    db: Session,
    trip_id: int,
    payload: dict,
    published_by: str = "admin",
) -> None:
    _ensure_driver_manifest_table(db)

    db.execute(
        text("DELETE FROM driver_trip_manifests WHERE trip_id = :trip_id"),
        {"trip_id": trip_id},
    )

    db.execute(
        text("""
            INSERT INTO driver_trip_manifests (
                trip_id,
                manifest_json,
                published_at,
                published_by
            )
            VALUES (
                :trip_id,
                :manifest_json,
                :published_at,
                :published_by
            )
        """),
        {
            "trip_id": trip_id,
            "manifest_json": json.dumps(payload, ensure_ascii=False),
            "published_at": datetime.utcnow(),
            "published_by": published_by,
        },
    )
    db.flush()


def _load_driver_manifest(db: Session, trip_id: int) -> dict | None:
    _ensure_driver_manifest_table(db)

    row = db.execute(
        text("""
            SELECT manifest_json, published_at, published_by
            FROM driver_trip_manifests
            WHERE trip_id = :trip_id
        """),
        {"trip_id": trip_id},
    ).mappings().first()

    if not row:
        return None

    raw = row.get("manifest_json") or "{}"

    try:
        data = json.loads(raw)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    passengers = data.get("passengers")
    if not isinstance(passengers, list):
        passengers = []

    data["passengers"] = passengers
    data["displayTotal"] = int(data.get("displayTotal") or len(passengers))
    data["rawPassengerCount"] = int(data.get("rawPassengerCount") or len(passengers))
    data["keptPassengerCount"] = int(data.get("keptPassengerCount") or len(passengers))
    data["missingPassengerCount"] = int(data.get("missingPassengerCount") or 0)

    if not isinstance(data.get("bookingPending"), list):
        data["bookingPending"] = []

    if not isinstance(data.get("bookingCoverage"), list):
        data["bookingCoverage"] = []

    if not data.get("publishedAt") and row.get("published_at"):
        try:
            data["publishedAt"] = row["published_at"].isoformat()
        except Exception:
            data["publishedAt"] = None

    if not data.get("publishedBy"):
        data["publishedBy"] = row.get("published_by")

    return data


def _overlay_live_driver_operational_fields(
    db: Session,
    manifest_passengers: list[dict],
) -> list[dict]:
    """
    Driver чете публикувания snapshot, но operational полетата
    идват live от TripPassenger.
    """
    ids = []
    for item in manifest_passengers:
        try:
            pid = int(item.get("id"))
            ids.append(pid)
        except Exception:
            continue

    if not ids:
        return manifest_passengers

    rows = (
        db.query(TripPassenger)
        .filter(TripPassenger.id.in_(ids))
        .all()
    )
    live_by_id = {int(p.id): p for p in rows}

    out: list[dict] = []
    for item in manifest_passengers:
        cloned = dict(item)

        try:
            pid = int(cloned.get("id"))
        except Exception:
            out.append(cloned)
            continue

        p = live_by_id.get(pid)
        if p:
            cloned["checkedIn"] = bool(getattr(p, "checked_in", False))
            cloned["paid"] = bool(getattr(p, "paid", False))
            cloned["amount"] = float(p.amount) if getattr(p, "amount", None) is not None else None
            cloned["currency"] = getattr(p, "currency", "EUR")
            cloned["oebb"] = bool(getattr(p, "oebb", False))

        out.append(cloned)

    return out

# =======================
# Helper portal session
# =======================
def _ensure_portal_or_redirect(request: Request):
    booking_id = request.session.get("portal_booking_id")
    if not booking_id:
        next_url = request.url.path
        if request.url.query:
            next_url += f"?{request.url.query}"
        return RedirectResponse(
            url=f"/portal/login?next={quote(next_url, safe='/?=&')}",
            status_code=303,
        )
    return None


@app.get("/portal/ticket", response_class=HTMLResponse)
def portal_ticket_page(request: Request, db: Session = Depends(get_db)):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    if not _can_portal_view_ticket(booking):
        return RedirectResponse(url="/portal?cash_err=ticket", status_code=303)

    service_label = _booking_service_label(booking)
    selected_seat = _booking_selected_seat(booking)
    selected_seats = _booking_selected_seats(booking)
    qr_available = _ticket_qr_available(booking)

    stop_points = _booking_stop_points(booking)
    first_departure_time = _extract_first_departure_time(getattr(booking, "time_range_raw", None))
    departure_time_label = first_departure_time.strftime("%H:%M") if first_departure_time else None

    return templates.TemplateResponse(
        request,
        "portal/ticket.html",
        {
            "booking": booking,
            "selected_seat": selected_seat,
            "selected_seats": selected_seats,
            "service_label": service_label,
            "qr_available": qr_available,
            "stop_points": stop_points,
            "departure_time_label": departure_time_label,
        },
    )


@app.get("/portal/ticket/qr")
def portal_ticket_qr(request: Request, db: Session = Depends(get_db)):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    if not _can_portal_view_ticket(booking):
        return RedirectResponse(url="/portal?cash_err=ticket", status_code=303)

    selected_seat = _booking_selected_seat(booking)
    if not selected_seat or not _ticket_qr_available(booking):
        return RedirectResponse(url="/portal/ticket", status_code=303)

    trip = None
    if getattr(booking, "trip_id", None):
        trip = db.query(Trip).filter(Trip.id == booking.trip_id).first()

    passenger = None
    passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking.id)
        .order_by(TripPassenger.id.asc())
        .all()
    )

    if passengers:
        seat_norm = str(selected_seat or "").strip()

        for p in passengers:
            p_seat = (
                getattr(p, "seat_no", None)
                or getattr(p, "manual_seat_no", None)
                or getattr(p, "effective_seat_no", None)
            )
            if str(p_seat or "").strip() == seat_norm:
                passenger = p
                break

        if passenger is None:
            passenger = passengers[0]

    payload = _portal_ticket_payload(
        booking=booking,
        selected_seat=selected_seat,
        passenger=passenger,
        trip=trip,
    )

    qr_data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    svg_bytes = _build_qr_svg_bytes(qr_data, size=260)

    return Response(
        content=svg_bytes,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )

@app.get("/portal/ticket/qr/download")
def portal_ticket_qr_download(request: Request, db: Session = Depends(get_db)):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    if not _can_portal_view_ticket(booking):
        return RedirectResponse(url="/portal?cash_err=ticket", status_code=303)

    selected_seat = _booking_selected_seat(booking)
    if not selected_seat or not _ticket_qr_available(booking):
        return RedirectResponse(url="/portal/ticket", status_code=303)

    trip = None
    if getattr(booking, "trip_id", None):
        trip = db.query(Trip).filter(Trip.id == booking.trip_id).first()

    passenger = None
    passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking.id)
        .order_by(TripPassenger.id.asc())
        .all()
    )

    if passengers:
        seat_norm = str(selected_seat or "").strip()

        for p in passengers:
            p_seat = (
                getattr(p, "seat_no", None)
                or getattr(p, "manual_seat_no", None)
                or getattr(p, "effective_seat_no", None)
            )
            if str(p_seat or "").strip() == seat_norm:
                passenger = p
                break

        if passenger is None:
            passenger = passengers[0]

    payload = _portal_ticket_payload(
        booking=booking,
        selected_seat=selected_seat,
        passenger=passenger,
        trip=trip,
    )

    qr_data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    svg_bytes = _build_qr_svg_bytes(qr_data, size=260)

    filename = f"ticket-qr-{booking.external_id}.svg"
    return Response(
        content=svg_bytes,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )

@app.get("/portal/ticket/pdf")
def portal_ticket_pdf(request: Request, db: Session = Depends(get_db)):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    if not _can_portal_view_ticket(booking):
        return RedirectResponse(url="/portal?cash_err=ticket", status_code=303)

    regular_font, bold_font = _ensure_pdf_unicode_fonts()

    service_label = _booking_service_label(booking)
    selected_seat = _booking_selected_seat(booking)
    qr_available = _ticket_qr_available(booking)

    trip = None
    if getattr(booking, "trip_id", None):
        trip = db.query(Trip).filter(Trip.id == booking.trip_id).first()

    passenger = None
    passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking.id)
        .order_by(TripPassenger.id.asc())
        .all()
    )

    if passengers and selected_seat:
        seat_norm = str(selected_seat or "").strip()

        for p in passengers:
            p_seat = (
                getattr(p, "manual_seat_no", None)
                or getattr(p, "seat_no", None)
                or getattr(p, "effective_seat_no", None)
            )
            if str(p_seat or "").strip() == seat_norm:
                passenger = p
                break

        if passenger is None:
            passenger = passengers[0]

    stop_points = _booking_stop_points(booking)
    departure_stop = stop_points.get("departure", {}) or {}
    arrival_stop = stop_points.get("arrival", {}) or {}

    first_departure_time = _extract_first_departure_time(getattr(booking, "time_range_raw", None))
    departure_time_label = first_departure_time.strftime("%H:%M") if first_departure_time else "-"

    # ASCII-safe label separators for PDF rendering
    service_label_pdf = (service_label or "-").replace("•", "-").replace("→", "->")
    departure_point_pdf = str(departure_stop.get("label") or "-").replace("•", "-").replace("→", "->")
    departure_address_pdf = str(departure_stop.get("address") or "-").replace("•", "-").replace("→", "->")
    arrival_point_pdf = str(arrival_stop.get("label") or "-").replace("•", "-").replace("→", "->")
    arrival_address_pdf = str(arrival_stop.get("address") or "-").replace("•", "-").replace("→", "->")

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    left = 20 * mm
    right = page_w - 20 * mm
    top = page_h - 20 * mm
    width = right - left

    card_x = left
    card_y = 35 * mm
    card_w = width
    card_h = page_h - 55 * mm

    pdf.setLineWidth(1)
    pdf.roundRect(card_x, card_y, card_w, card_h, 10, stroke=1, fill=0)

    pdf.setFont(bold_font, 20)
    pdf.drawString(card_x + 12 * mm, top, "Boarding Ticket")

    pdf.setFont(regular_font, 10)
    pdf.drawString(card_x + 12 * mm, top - 7 * mm, f"Unique ID: {booking.external_id}")

    pdf.line(card_x, top - 12 * mm, card_x + card_w, top - 12 * mm)

    qr_box_size = 58 * mm
    qr_box_x = card_x + card_w - 78 * mm
    qr_box_y = card_y + card_h - 92 * mm

    text_x = card_x + 12 * mm
    text_right = qr_box_x - 10 * mm
    text_width = max(60 * mm, text_right - text_x)
    y = top - 24 * mm

    def wrap_text(value: str, font_name: str, font_size: int, max_width: float) -> list[str]:
        value = str(value or "-").strip() or "-"
        words = value.split()
        if not words:
            return ["-"]

        lines: list[str] = []
        current = words[0]

        for word in words[1:]:
            candidate = f"{current} {word}"
            if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word

        lines.append(current)
        return lines

    def row(label: str, value: str):
        nonlocal y

        label_text = str(label or "-")
        value_text = str(value or "-")

        pdf.setFont(regular_font, 9)
        pdf.drawString(text_x, y, label_text)

        value_lines = wrap_text(value_text, bold_font, 11, text_width)

        value_y = y - 5 * mm
        pdf.setFont(bold_font, 11)
        for line in value_lines:
            pdf.drawString(text_x, value_y, line)
            value_y -= 4.6 * mm

        y = value_y - 3 * mm

    passenger_name = f"{booking.first_name or ''} {booking.last_name or ''}".strip() or "-"
    passenger_route = f"{booking.route_from or '-'} -> {booking.route_to or '-'}"
    seat_label = selected_seat or "Assigned later by dispatch"
    payment_status = booking.payment_status or "-"
    booking_status = booking.booking_status or "-"
    booking_ref = f"#{booking.id}"

    row("Passenger", passenger_name)
    row("Service", service_label_pdf)
    row("Passenger route", passenger_route)
    row("Time DEPARTURE", departure_time_label)
    row("Departure point", departure_point_pdf)
    row("Departure address", departure_address_pdf)
    row("Arrival point", arrival_point_pdf)
    row("Arrival address", arrival_address_pdf)
    row("Seat", seat_label)
    row("Payment status", payment_status)
    row("Booking status", booking_status)
    row("Booking reference", booking_ref)

    pdf.roundRect(
        qr_box_x - 6 * mm,
        qr_box_y - 6 * mm,
        qr_box_size + 12 * mm,
        qr_box_size + 18 * mm,
        8,
        stroke=1,
        fill=0,
    )
    pdf.setFont(bold_font, 12)
    pdf.drawCentredString(
        qr_box_x + qr_box_size / 2,
        qr_box_y + qr_box_size + 6 * mm,
        "Boarding QR",
    )

    if qr_available and selected_seat:
        payload = _portal_ticket_payload(
            booking=booking,
            selected_seat=selected_seat,
            passenger=passenger,
            trip=trip,
        )
        qr_data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        qr = QrCodeWidget(qr_data)
        bounds = qr.getBounds()
        bw = bounds[2] - bounds[0]
        bh = bounds[3] - bounds[1]

        drawing = Drawing(
            qr_box_size,
            qr_box_size,
            transform=[qr_box_size / bw, 0, 0, qr_box_size / bh, 0, 0],
        )
        drawing.add(qr)
        renderPDF.draw(drawing, pdf, qr_box_x, qr_box_y)

        pdf.setFont(regular_font, 9)
        pdf.drawCentredString(
            qr_box_x + qr_box_size / 2,
            qr_box_y - 7 * mm,
            "Show during boarding",
        )
    else:
        pdf.setFont(regular_font, 10)
        pdf.drawString(qr_box_x, qr_box_y + 22 * mm, "QR will become available")
        pdf.drawString(qr_box_x, qr_box_y + 16 * mm, "after a final seat is assigned.")

    pdf.setFont(regular_font, 8)
    pdf.drawString(card_x + 12 * mm, card_y + 8 * mm, "Generated from passenger portal")

    pdf.showPage()
    pdf.save()

    pdf_bytes = buf.getvalue()
    buf.close()

    filename = f"ticket-{booking.external_id}.pdf"
    headers = {
        "Content-Disposition": f'attachment; filename=\"{filename}\"'
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)




@app.get("/drivers/scan", response_class=HTMLResponse)
def drivers_scan_get(
    request: Request,
    trip_id: int | None = None,
    err: str | None = None,
):
    _ensure_driver(request)

    result = None

    if err:
        err_map = {
            "invalid_qr": "Invalid QR payload",
            "notfound": "Booking or passenger not found",
            "cash_amount_missing": "Missing cash amount",
            "cash_amount_invalid": "Invalid cash amount",
            "bad_action": "Invalid scan action",
        }
        result = {
            "ok": False,
            "message": err_map.get(err, "Scan action failed"),
            "booking": None,
            "passenger": None,
            "parsed_payload": None,
            "boarding_state": None,
        }

    return templates.TemplateResponse(
        request,
        "drivers_scan.html",
        {
            "result": result,
            "payload_text": "",
            "trip_id": trip_id,
        },
    )


@app.post("/drivers/scan", response_class=HTMLResponse)
def drivers_scan_submit(
    request: Request,
    qr_payload: str = Form(""),
    trip_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    _ensure_driver(request)

    payload_text = (qr_payload or "").strip()
    payload = _parse_ticket_payload(payload_text)

    result = {
        "ok": False,
        "message": "",
        "booking": None,
        "passenger": None,
        "parsed_payload": None,
        "boarding_state": None,
    }

    if not payload:
        result["message"] = "Invalid QR payload"
        return templates.TemplateResponse(
            request,
            "drivers_scan.html",
            {
                "result": result,
                "payload_text": payload_text,
                "trip_id": trip_id or request.query_params.get("trip_id"),
            },
        )

    booking, passenger = _resolve_trip_passenger_by_ticket_payload(db, payload)

    if not booking:
        result["message"] = "Booking not found"
        result["parsed_payload"] = payload

    elif not passenger:
        result["message"] = "Passenger not found for this QR"
        result["booking"] = booking
        result["parsed_payload"] = payload

    else:
        boarding_state = _get_driver_boarding_state_row(db, passenger.id)
        result = {
            "ok": True,
            "message": "QR parsed successfully",
            "booking": booking,
            "passenger": passenger,
            "parsed_payload": payload,
            "boarding_state": boarding_state,
        }

    return templates.TemplateResponse(
        request,
        "drivers_scan.html",
        {
            "result": result,
            "payload_text": payload_text,
            "trip_id": trip_id or request.query_params.get("trip_id"),
        },
    )


@app.post("/drivers/scan/action")
def drivers_scan_action(
    request: Request,
    qr_payload: str = Form(""),
    action: str = Form(""),
    cash_amount: str = Form(""),
    cash_currency: str = Form("EUR"),
    refuse_reason: str = Form(""),
    refused_reason: str = Form(""),
    db: Session = Depends(get_db),
):
    _ensure_driver(request)

    payload = _parse_ticket_payload((qr_payload or "").strip())
    if not payload:
        return RedirectResponse(url="/drivers/scan?err=invalid_qr", status_code=303)

    booking, passenger = _resolve_trip_passenger_by_ticket_payload(db, payload)
    if not booking or not passenger:
        return RedirectResponse(url="/drivers/scan?err=notfound", status_code=303)

    current_state = _get_driver_boarding_state_row(db, passenger.id) or {}

    boarding_status = current_state.get("boarding_status") or (
        "checked_in" if bool(getattr(passenger, "checked_in", False)) else "pending"
    )
    refused_reason_value = current_state.get("refused_reason")
    oebb_checked = bool(current_state.get("oebb_checked")) or bool(getattr(passenger, "oebb", False))
    cash_collected_amount = current_state.get("cash_collected_amount")
    cash_collected_currency = (
        current_state.get("cash_collected_currency")
        or getattr(passenger, "currency", None)
        or "EUR"
    )

    action = (action or "").strip().lower()

    # support both template variants and old variants
    if action in {"check_in", "checkin"}:
        passenger.checked_in = True
        boarding_status = "checked_in"
        refused_reason_value = None

    elif action in {"collect_cash", "cash"}:
        raw_amount = (cash_amount or "").strip()
        if not raw_amount:
            return RedirectResponse(
                url=f"/drivers/scan?err=cash_amount_missing&trip_id={passenger.trip_id}",
                status_code=303,
            )

        try:
            parsed_amount = float(raw_amount.replace(",", "."))
        except Exception:
            return RedirectResponse(
                url=f"/drivers/scan?err=cash_amount_invalid&trip_id={passenger.trip_id}",
                status_code=303,
            )

        passenger.paid = True
        passenger.amount = parsed_amount
        passenger.currency = ((cash_currency or "EUR").upper().strip() or "EUR")

        cash_collected_amount = parsed_amount
        cash_collected_currency = passenger.currency

    elif action in {"check_oebb", "oebb"}:
        passenger.oebb = True
        oebb_checked = True

    elif action == "refuse":
        passenger.checked_in = False
        boarding_status = "refused"
        refused_reason_value = (
            (refused_reason or "").strip()
            or (refuse_reason or "").strip()
            or "driver_refused"
        )

    else:
        return RedirectResponse(url="/drivers/scan?err=bad_action", status_code=303)

    _upsert_driver_boarding_state(
        db=db,
        passenger_id=passenger.id,
        trip_id=passenger.trip_id,
        booking_id=getattr(passenger, "booking_id", None),
        boarding_status=boarding_status,
        refused_reason=refused_reason_value,
        last_qr_payload=json.dumps(payload, ensure_ascii=False),
        oebb_checked=oebb_checked,
        cash_collected_amount=cash_collected_amount,
        cash_collected_currency=cash_collected_currency,
        updated_by="driver",
    )

    db.commit()

    return RedirectResponse(
        url=f"/drivers/trips/{passenger.trip_id}?scan_ok={action}",
        status_code=303,
    )


@app.post("/admin/bookings/{booking_id}/assign-seat")
def admin_booking_assign_seat(
    booking_id: int,
    request: Request,
    seat_no: str = Form(""),
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(404, "Booking not found")

    if not _can_dispatch_assign_cash_seat(db, booking):
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?seat_admin_err=window",
            status_code=303,
        )

    seat_no = (seat_no or "").strip()
    if not seat_no:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?seat_admin_err=missing",
            status_code=303,
        )

    allowed = set(_service_default_seat_map(booking))
    if seat_no not in allowed:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?seat_admin_err=invalid",
            status_code=303,
        )

    passenger_count = _booking_passenger_count(db, booking)
    taken_seats = _service_taken_seats(db, booking, exclude_booking_id=booking.id)

    chosen_seats = _pick_free_service_seats(
        booking=booking,
        taken_seats=taken_seats,
        count=passenger_count,
        preferred_first=seat_no,
    )

    if len(chosen_seats) < passenger_count:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?seat_admin_err=full",
            status_code=303,
        )

    _apply_booking_seat_assignment(
        db=db,
        booking=booking,
        seat_nos=chosen_seats,
        selection_mode="dispatcher",
    )
    _set_booking_trip_passengers_admin_seat_lock(db, booking.id, True)

    db.commit()

    return RedirectResponse(
        url=f"/admin/bookings/{booking_id}?seat_admin_ok=1",
        status_code=303,
    )

@app.post("/admin/bookings/{booking_id}/assign-seat-auto")
def admin_booking_assign_seat_auto(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(404, "Booking not found")

    if not _can_dispatch_assign_cash_seat(db, booking):
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?seat_admin_err=window",
            status_code=303,
        )

    passenger_count = _booking_passenger_count(db, booking)
    taken_seats = _service_taken_seats(db, booking, exclude_booking_id=booking.id)

    chosen_seats = _pick_free_service_seats(
        booking=booking,
        taken_seats=taken_seats,
        count=passenger_count,
        preferred_first=None,
    )

    if len(chosen_seats) < passenger_count:
        return RedirectResponse(
            url=f"/admin/bookings/{booking_id}?seat_admin_err=full",
            status_code=303,
        )

    _apply_booking_seat_assignment(
        db=db,
        booking=booking,
        seat_nos=chosen_seats,
        selection_mode="dispatcher_auto",
    )
    _set_booking_trip_passengers_admin_seat_lock(db, booking.id, True)

    db.commit()

    return RedirectResponse(
        url=f"/admin/bookings/{booking_id}?seat_admin_ok=1",
        status_code=303,
    )


@app.get("/admin/bookings/test-import", response_class=HTMLResponse)
def admin_booking_test_import_page(request: Request):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    return templates.TemplateResponse(
        request,
        "admin/booking_test_import.html",
        {
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
        },
    )


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


@app.get("/admin/bookings/list", response_class=HTMLResponse)
def admin_bookings_list_page(
    request: Request,
    q: str = "",
    booking_status: str = "",
    payment_status: str = "",
    only_unlinked: str = "",
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    query = db.query(Booking).order_by(Booking.created_at.desc(), Booking.id.desc())

    q = (q or "").strip()
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                cast(Booking.external_id, String).ilike(pattern),
                Booking.first_name.ilike(pattern),
                Booking.last_name.ilike(pattern),
                Booking.email.ilike(pattern),
                Booking.phone.ilike(pattern),
                Booking.route_from.ilike(pattern),
                Booking.route_to.ilike(pattern),
                Booking.bus_name.ilike(pattern),
            )
        )

    booking_status = (booking_status or "").strip()
    if booking_status:
        query = query.filter(Booking.booking_status == booking_status)

    payment_status = (payment_status or "").strip()
    if payment_status:
        query = query.filter(Booking.payment_status == payment_status)

    if only_unlinked:
        query = query.filter(Booking.trip_id.is_(None))

    bookings = query.limit(300).all()

    booking_ids = [b.id for b in bookings]
    seat_map: dict[int, list[str]] = {}
    pax_count_map: dict[int, int] = {}

    if booking_ids:
        seat_rows = (
            db.query(BookingSeat.booking_id, BookingSeat.seat_no)
            .filter(BookingSeat.booking_id.in_(booking_ids))
            .order_by(BookingSeat.booking_id.asc(), BookingSeat.seat_no.asc())
            .all()
        )
        for bid, seat_no in seat_rows:
            seat_map.setdefault(int(bid), []).append(seat_no)

        pax_rows = (
            db.query(TripPassenger.booking_id, func.count(TripPassenger.id))
            .filter(TripPassenger.booking_id.in_(booking_ids))
            .group_by(TripPassenger.booking_id)
            .all()
        )
        pax_count_map = {int(bid): int(cnt) for bid, cnt in pax_rows if bid is not None}

    for b in bookings:
        b._seat_list = seat_map.get(int(b.id), [])
        b._seat_list_str = ", ".join(b._seat_list) if b._seat_list else "—"
        b._linked_pax_count = pax_count_map.get(int(b.id), 0)

    return templates.TemplateResponse(
        request,
        "admin/bookings_list.html",
        {
            "section": "list",
            "bookings": bookings,
            "filters": {
                "q": q,
                "booking_status": booking_status,
                "payment_status": payment_status,
                "only_unlinked": bool(only_unlinked),
            },
        },
    )


@app.get("/admin/bookings", response_class=HTMLResponse)
def admin_bookings_dashboard_page(request: Request, db: Session = Depends(get_db)):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    total_bookings = int(db.query(func.count(Booking.id)).scalar() or 0)
    total_paid = int(
        db.query(func.count(Booking.id))
        .filter(Booking.payment_status == "paid")
        .scalar()
        or 0
    )
    total_pending_review = int(
        db.query(func.count(Booking.id))
        .filter(Booking.payment_status == "pending_review")
        .scalar()
        or 0
    )

    today_start = _vienna_now_naive().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    total_today_bookings = int(
        db.query(func.count(Booking.id))
        .filter(Booking.created_at.isnot(None))
        .filter(Booking.created_at >= today_start)
        .filter(Booking.created_at < today_end)
        .scalar()
        or 0
    ) 

    total_pending_cancellations = int(
        db.query(func.count(BookingCancellation.id))
        .filter(BookingCancellation.admin_status == "pending")
        .scalar()
        or 0
    )

    recent_bookings = (
        db.query(Booking)
        .order_by(Booking.created_at.desc(), Booking.id.desc())
        .limit(10)
        .all()
    )

    all_bookings = (
        db.query(Booking)
        .order_by(Booking.booking_date.asc(), Booking.id.desc())
        .all()
    )

    booking_ids = [int(b.id) for b in all_bookings if getattr(b, "id", None) is not None]
    trip_passengers_by_booking_id: dict[int, list[TripPassenger]] = {}

    if booking_ids:
        booking_linked_passengers = (
            db.query(TripPassenger)
            .filter(TripPassenger.booking_id.in_(booking_ids))
            .all()
        )

        for p in booking_linked_passengers:
            bid = getattr(p, "booking_id", None)
            if bid is None:
                continue
            trip_passengers_by_booking_id.setdefault(int(bid), []).append(p)

        for bid in list(trip_passengers_by_booking_id.keys()):
            trip_passengers_by_booking_id[bid] = sorted(
                trip_passengers_by_booking_id[bid],
                key=_trip_passenger_sort_key,
            )

    proof_count_map: dict[int, int] = {}
    final_seats_map: dict[int, list[str]] = {}
    qty_sum_map: dict[int, int] = {}
    linked_pax_count_map: dict[int, int] = {}
    booking_seat_count_map: dict[int, int] = {}

    if booking_ids:
        proof_rows = (
            db.query(PaymentProof.booking_id, func.count(PaymentProof.id))
            .filter(PaymentProof.booking_id.in_(booking_ids))
            .group_by(PaymentProof.booking_id)
            .all()
        )
        proof_count_map = {int(bid): int(cnt) for bid, cnt in proof_rows if bid is not None}

        final_seat_rows = (
            db.query(BookingSeat.booking_id, BookingSeat.seat_no)
            .filter(
                BookingSeat.booking_id.in_(booking_ids),
                BookingSeat.is_final == True,
                BookingSeat.seat_no.isnot(None),
            )
            .order_by(BookingSeat.booking_id.asc(), BookingSeat.id.asc())
            .all()
        )
        for bid, seat_no in final_seat_rows:
            if bid is None or not seat_no:
                continue
            final_seats_map.setdefault(int(bid), []).append(str(seat_no).strip())

        qty_rows = (
            db.query(
                BookingTicketLine.booking_id,
                func.coalesce(func.sum(BookingTicketLine.qty), 0),
            )
            .filter(BookingTicketLine.booking_id.in_(booking_ids))
            .group_by(BookingTicketLine.booking_id)
            .all()
        )
        qty_sum_map = {
            int(bid): int(total_qty or 0)
            for bid, total_qty in qty_rows
            if bid is not None
        }

        linked_pax_rows = (
            db.query(TripPassenger.booking_id, func.count(TripPassenger.id))
            .filter(
                TripPassenger.booking_id.in_(booking_ids),
                TripPassenger.booking_id.isnot(None),
            )
            .group_by(TripPassenger.booking_id)
            .all()
        )
        linked_pax_count_map = {
            int(bid): int(cnt or 0)
            for bid, cnt in linked_pax_rows
            if bid is not None
        }

        booking_seat_rows = (
            db.query(BookingSeat.booking_id, func.count(BookingSeat.id))
            .filter(BookingSeat.booking_id.in_(booking_ids))
            .group_by(BookingSeat.booking_id)
            .all()
        )
        booking_seat_count_map = {
            int(bid): int(cnt or 0)
            for bid, cnt in booking_seat_rows
            if bid is not None
        }

    for booking_id, seat_list in list(final_seats_map.items()):
        unique = [s for s in dict.fromkeys(seat_list) if s]
        unique.sort(key=_seat_sort_key)
        final_seats_map[booking_id] = unique

    booking_trip_ids = {
        int(getattr(b, "trip_id", 0) or 0)
        for b in all_bookings
        if getattr(b, "trip_id", None)
    }

    passenger_trip_ids = {
        int(tid)
        for (tid,) in db.query(TripPassenger.trip_id)
        .filter(TripPassenger.trip_id.isnot(None))
        .distinct()
        .all()
        if tid is not None
    }

    all_relevant_trip_ids = sorted(booking_trip_ids | passenger_trip_ids)

    trip_by_id: dict[int, Trip] = {}
    if all_relevant_trip_ids:
        trips = db.query(Trip).filter(Trip.id.in_(all_relevant_trip_ids)).all()
        trip_by_id = {int(t.id): t for t in trips}

    all_trip_passengers: list[TripPassenger] = []
    if all_relevant_trip_ids:
        all_trip_passengers = (
            db.query(TripPassenger)
            .filter(TripPassenger.trip_id.in_(all_relevant_trip_ids))
            .all()
        )

    trip_passengers_by_trip_id: dict[int, list[TripPassenger]] = {}
    for p in all_trip_passengers:
        trip_id = getattr(p, "trip_id", None)
        if trip_id is None:
            continue
        trip_passengers_by_trip_id.setdefault(int(trip_id), []).append(p)

    for trip_id in list(trip_passengers_by_trip_id.keys()):
        trip_passengers_by_trip_id[trip_id] = sorted(
            trip_passengers_by_trip_id[trip_id],
            key=_trip_passenger_sort_key,
        )

    now_vienna = _vienna_now_naive()

    bank_paypal_missing_proof_le_72 = []
    bank_paypal_missing_proof_gt_72 = []
    cash_not_confirmed_le_72 = []
    cash_not_confirmed_gt_72 = []
    dispatcher_seat_assignment_needed = []

    day_direction_map: dict[str, dict[str, dict]] = {}

    def _dir_bucket(date_key: str, direction_key: str, direction_label: str) -> dict:
        day_bucket = day_direction_map.setdefault(date_key, {})
        if direction_key not in day_bucket:
            day_bucket[direction_key] = {
                "key": direction_key,
                "label": direction_label,
                "present": False,
                "items": [],
                "trip_ids": set(),
                "bank_paypal_missing_proof_le72": [],
                "bank_paypal_missing_proof_gt72": [],
                "cash_not_confirmed_le72": [],
                "cash_not_confirmed_gt72": [],
                "dispatcher_seat_assignment_needed": [],
                "taken_seats": set(),
            }
        return day_bucket[direction_key]

    def _dashboard_item(
        booking: Booking,
        dep_dt: datetime | None,
        booking_date_obj: date,
        hours_left: float | None,
    ) -> dict:
        passenger_name = f"{booking.first_name or ''} {booking.last_name or ''}".strip() or "—"
        route = f"{booking.route_from or booking.bus_from or '—'} → {booking.route_to or booking.bus_to or '—'}"
        departure_str = dep_dt.strftime("%d.%m.%Y %H:%M") if dep_dt else booking_date_obj.strftime("%d.%m.%Y")
        return {
            "id": booking.id,
            "external_id": booking.external_id,
            "passenger_name": passenger_name,
            "route": route,
            "departure_str": departure_str,
            "hours_left": hours_left,
            "hours_left_str": f"{hours_left:.1f} h" if hours_left is not None else "—",
            "payment_status": booking.payment_status or "—",
            "booking_status": booking.booking_status or "—",
            "url": f"/admin/bookings/{booking.id}",
        }

    def _fast_booking_passenger_count(booking: Booking) -> int:
        booking_id = int(getattr(booking, "id", 0) or 0)
        if not booking_id:
            return 1

        total_qty = int(qty_sum_map.get(booking_id, 0) or 0)
        if total_qty > 0:
            return total_qty

        pax_count = int(linked_pax_count_map.get(booking_id, 0) or 0)
        if pax_count > 0:
            return pax_count

        seat_count = int(booking_seat_count_map.get(booking_id, 0) or 0)
        if seat_count > 0:
            return seat_count

        final_seat_count = len(final_seats_map.get(booking_id, []) or [])
        if final_seat_count > 0:
            return final_seat_count

        for attr in ("passenger_count", "pax_count", "seats_count", "qty"):
            value = getattr(booking, attr, None)
            try:
                if value is not None and int(value) > 0:
                    return int(value)
            except Exception:
                pass

        return 1

    for trip in trip_by_id.values():
        trip_date_obj = _dashboard_trip_base_date(trip)
        if not trip_date_obj:
            continue

        direction_meta = _dashboard_direction_meta_for_trip(trip)
        date_key = trip_date_obj.isoformat()
        bucket = _dir_bucket(date_key, direction_meta["key"], direction_meta["label"])
        bucket["present"] = True
        bucket["trip_ids"].add(int(trip.id))

    for booking in all_bookings:
        booking_date_obj = _dashboard_booking_base_date(booking, trip_by_id=trip_by_id)
        if not booking_date_obj:
            continue

        dep_dt = _booking_departure_dt_for_dispatch(db, booking)
        hours_left = None
        if dep_dt is not None:
            hours_left = (dep_dt - now_vienna).total_seconds() / 3600.0

        direction_meta = _dashboard_direction_meta_for_booking(booking, trip_by_id=trip_by_id)
        date_key = booking_date_obj.isoformat()
        direction_key = direction_meta["key"]
        bucket = _dir_bucket(date_key, direction_key, direction_meta["label"])
        bucket["present"] = True
        bucket["items"].append(booking)

        booking_trip_id = getattr(booking, "trip_id", None)
        if booking_trip_id:
            bucket["trip_ids"].add(int(booking_trip_id))

        method = _norm_payment_method(getattr(booking, "payment_method", None))
        proof_count = proof_count_map.get(int(booking.id), 0)
        final_seats = list(final_seats_map.get(int(booking.id), []))
        has_final_seat = bool(final_seats)

        setattr(booking, "_dashboard_final_seats", final_seats)
        setattr(booking, "_dashboard_passenger_count", _fast_booking_passenger_count(booking))

        for seat_no in final_seats:
            if seat_no:
                bucket["taken_seats"].add(str(seat_no).strip())

        item = _dashboard_item(booking, dep_dt, booking_date_obj, hours_left)

        if hours_left is None or hours_left < 0:
            continue

        if method in {"bank", "paypal"} and proof_count == 0 and booking.payment_status != "paid":
            if hours_left <= 72:
                bank_paypal_missing_proof_le_72.append(item)
                bucket["bank_paypal_missing_proof_le72"].append(item)
            else:
                bank_paypal_missing_proof_gt_72.append(item)
                bucket["bank_paypal_missing_proof_gt72"].append(item)

        if method == "cash" and booking.booking_status not in {"confirmed", "cancelled"}:
            if hours_left <= 72:
                cash_not_confirmed_le_72.append(item)
                bucket["cash_not_confirmed_le72"].append(item)
            else:
                cash_not_confirmed_gt_72.append(item)
                bucket["cash_not_confirmed_gt72"].append(item)

        if (
            method == "cash"
            and booking.booking_status == "confirmed"
            and not has_final_seat
            and _ensure_booking_has_service(db, booking)
            and 10 <= hours_left <= 24
        ):
            dispatcher_seat_assignment_needed.append(item)
            bucket["dispatcher_seat_assignment_needed"].append(item)

    def _hours_sort_value(item: dict):
        hours_left = item.get("hours_left")
        if hours_left is None:
            return 10**9
        return float(hours_left)

    bank_paypal_missing_proof_le_72.sort(key=_hours_sort_value)
    bank_paypal_missing_proof_gt_72.sort(key=_hours_sort_value)
    cash_not_confirmed_le_72.sort(key=_hours_sort_value)
    cash_not_confirmed_gt_72.sort(key=_hours_sort_value)
    dispatcher_seat_assignment_needed.sort(key=_hours_sort_value)

    dashboard_calendar_data = {}
    for date_key in sorted(day_direction_map.keys()):
        dirs = day_direction_map[date_key]
        direction_payloads: list[dict] = []

        for direction_key, bucket in sorted(dirs.items(), key=lambda kv: str(kv[1].get("label") or "").lower()):
            trip_passengers: list[TripPassenger] = []
            seen_passenger_ids: set[int] = set()
            taken_seats_union = set(bucket["taken_seats"])

            for trip_id in sorted(bucket.get("trip_ids", set())):
                for p in trip_passengers_by_trip_id.get(int(trip_id), []):
                    pid = int(getattr(p, "id", 0) or 0)
                    if pid and pid in seen_passenger_ids:
                        continue
                    if pid:
                        seen_passenger_ids.add(pid)
                    trip_passengers.append(p)
                    seat_no = _effective_trip_passenger_seat(p)
                    if seat_no:
                        taken_seats_union.add(seat_no)

            # Добавяме и всички TripPassenger rows, които са вързани към booking_id,
            # дори ако trip_id липсва или не е попаднал в trip_passengers_by_trip_id.
            for booking in bucket.get("items", []) or []:
                bid = int(getattr(booking, "id", 0) or 0)
                if not bid:
                    continue

                for p in trip_passengers_by_booking_id.get(bid, []):
                    pid = int(getattr(p, "id", 0) or 0)
                    if pid and pid in seen_passenger_ids:
                        continue

                    if pid:
                        seen_passenger_ids.add(pid)

                    # Само за display payload. Не е задължително да commit-ваме тук.
                    if not getattr(p, "trip_id", None) and getattr(booking, "trip_id", None):
                        p.trip_id = booking.trip_id

                    trip_passengers.append(p)

                    seat_no = _effective_trip_passenger_seat(p)
                    if seat_no:
                        taken_seats_union.add(seat_no)

            trip_passengers = sorted(trip_passengers, key=_trip_passenger_sort_key)

            payload = _build_dashboard_direction_payload(
                label=bucket["label"],
                items=bucket["items"],
                trip_passengers=trip_passengers,
                bank_paypal_missing_proof_le72=bucket["bank_paypal_missing_proof_le72"],
                cash_not_confirmed_le72=bucket["cash_not_confirmed_le72"],
                dispatcher_seat_assignment_needed=bucket["dispatcher_seat_assignment_needed"],
                bank_paypal_missing_proof_gt72=bucket["bank_paypal_missing_proof_gt72"],
                cash_not_confirmed_gt72=bucket["cash_not_confirmed_gt72"],
                extra_taken_seats=taken_seats_union,
                total_confirmed=None,
            )
            payload["key"] = direction_key
            payload["booking_count"] = len(bucket["items"])
            direction_payloads.append(payload)

        direction_payloads.sort(key=_dashboard_direction_sort_key)
        legacy_red = direction_payloads[0] if len(direction_payloads) > 0 else _empty_dashboard_direction_payload("—", "AT->UA")
        legacy_blue = direction_payloads[1] if len(direction_payloads) > 1 else _empty_dashboard_direction_payload("—", "UA->AT")

        dashboard_calendar_data[date_key] = {
            "present": bool(direction_payloads),
            "issue_count": sum(int(item.get("issue_count") or 0) for item in direction_payloads),
            "direction_count": len(direction_payloads),
            "booking_count": sum(int(item.get("booking_count") or 0) for item in direction_payloads),
            "directions": direction_payloads,
            "red": legacy_red,
            "blue": legacy_blue,
            "other_directions": direction_payloads[2:],
        }

    return templates.TemplateResponse(
        request,
        "admin/bookings_dashboard.html",
        {
            "section": "dashboard",
            "stats": {
                "total_bookings": total_bookings,
                "total_paid": total_paid,
                "total_pending_review": total_pending_review,
                "total_today_bookings": total_today_bookings,
            },
            "recent_bookings": recent_bookings,
            "critical": {
                "bank_paypal_missing_proof_le_72": bank_paypal_missing_proof_le_72,
                "bank_paypal_missing_proof_gt_72": bank_paypal_missing_proof_gt_72,
                "cash_not_confirmed_le_72": cash_not_confirmed_le_72,
                "cash_not_confirmed_gt_72": cash_not_confirmed_gt_72,
                "dispatcher_seat_assignment_needed": dispatcher_seat_assignment_needed,
                "pending_cancellations_count": total_pending_cancellations,
            },
            "seat_layout": SEAT_LAYOUT,
            "dashboard_calendar_data": dashboard_calendar_data,
        },
    )


@app.get("/admin/bookings/{booking_id}", response_class=HTMLResponse)
def admin_booking_detail_page(
    request: Request,
    booking_id: int,
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(404, "Booking not found")

    incoming_email = None
    if booking.incoming_email_id:
        incoming_email = (
            db.query(IncomingEmail)
            .filter(IncomingEmail.id == booking.incoming_email_id)
            .first()
        )

    seats = (
        db.query(BookingSeat)
        .filter(BookingSeat.booking_id == booking.id)
        .order_by(BookingSeat.seat_no.asc())
        .all()
    )

    ticket_lines = (
        db.query(BookingTicketLine)
        .filter(BookingTicketLine.booking_id == booking.id)
        .order_by(BookingTicketLine.id.asc())
        .all()
    )

    payment_proofs = (
        db.query(PaymentProof)
        .filter(PaymentProof.booking_id == booking.id)
        .order_by(PaymentProof.uploaded_at.desc(), PaymentProof.id.desc())
        .all()
    )

    linked_trip_passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking.id)
        .order_by(TripPassenger.id.asc())
        .all()
    )

    trip = None
    if booking.trip_id:
        trip = db.query(Trip).filter(Trip.id == booking.trip_id).first()

    payment_method_norm = _norm_payment_method(booking.payment_method)
    selected_seat = _booking_selected_seat(booking)
    selected_seats = _booking_selected_seats(booking)

    dispatch_hours_left = _dispatch_hours_until_departure(db, booking)
    dispatch_can_assign_seat = _can_dispatch_assign_cash_seat(db, booking)
    dispatch_taken_seats_raw = _service_taken_seats(db, booking, exclude_booking_id=booking.id) if _ensure_booking_has_service(booking) else set()
    dispatch_taken_seats = sorted(
        [str(x).strip() for x in dispatch_taken_seats_raw if str(x).strip()],
        key=_seat_sort_key,
    )
    dispatch_all_seats = _service_default_seat_map(booking) if _ensure_booking_has_service(booking) else []
    dispatch_departure_dt = _booking_departure_dt_for_dispatch(db, booking)

    editable_customer_name = f"{booking.first_name or ''} {booking.last_name or ''}".strip()
    editable_departure_date = _booking_departure_date_input_value(booking)
    editable_departure_time = _booking_departure_time_input_value(booking, dispatch_departure_dt)
    editable_total = _booking_total_input_value(getattr(booking, "total", None))

    return templates.TemplateResponse(request, "admin/booking_detail.html", {
        "section": "detail",
        "booking": booking,
        "incoming_email": incoming_email,
        "seats": seats,
        "selected_seats": selected_seats,
        "ticket_lines": ticket_lines,
        "payment_proofs": payment_proofs,
        "trip": trip,
        "linked_trip_passengers": linked_trip_passengers,

        "payment_method_norm": payment_method_norm,
        "selected_seat": selected_seat,
        "dispatch_hours_left": dispatch_hours_left,
        "dispatch_can_assign_seat": dispatch_can_assign_seat,
        "dispatch_taken_seats": dispatch_taken_seats,
        "dispatch_all_seats": dispatch_all_seats,
        "dispatch_departure_dt": dispatch_departure_dt,
        "seat_layout": SEAT_LAYOUT,
        "seat_admin_ok": request.query_params.get("seat_admin_ok", ""),
        "seat_admin_err": request.query_params.get("seat_admin_err", ""),

        "edit_ok": request.query_params.get("edit_ok", ""),
        "edit_err": request.query_params.get("edit_err", ""),
        "editable_customer_name": editable_customer_name,
        "editable_departure_date": editable_departure_date,
        "editable_departure_time": editable_departure_time,
        "editable_total": editable_total,
    })
 

@app.post("/admin/payment-proofs/{proof_id}/approve")
def admin_approve_payment_proof(
    proof_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    proof = db.query(PaymentProof).filter(PaymentProof.id == proof_id).first()
    if not proof:
        raise HTTPException(404, "Payment proof not found")

    booking = db.query(Booking).filter(Booking.id == proof.booking_id).first()
    if not booking:
        raise HTTPException(404, "Booking not found")

    proof.review_status = "approved"
    proof.review_note = None
    proof.reviewed_at = datetime.utcnow()
    proof.reviewed_by = "admin"

    booking.payment_status = "paid"

    if not booking.booking_status or booking.booking_status in {"new", "pending_payment"}:
        booking.booking_status = "confirmed"

    try:
        rematch_booking_to_trip(db, booking.id)
        db.flush()
        db.refresh(booking)

        if booking.trip_id:
            sync_booking_to_trip_passengers_by_id(
                db,
                booking.id,
                strict_replace_extra=False,
            )
            db.flush()
    except Exception:
        pass

    db.commit()

    return RedirectResponse(
        url=f"/admin/bookings/{booking.id}",
        status_code=303,
    )

@app.post("/admin/payment-proofs/{proof_id}/reject")
def admin_reject_payment_proof(
    proof_id: int,
    request: Request,
    review_note: str = Form(""),
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    proof = db.query(PaymentProof).filter(PaymentProof.id == proof_id).first()
    if not proof:
        raise HTTPException(404, "Payment proof not found")

    booking = db.query(Booking).filter(Booking.id == proof.booking_id).first()
    if not booking:
        raise HTTPException(404, "Booking not found")

    proof.review_status = "rejected"
    proof.review_note = (review_note or "").strip() or None
    proof.reviewed_at = datetime.utcnow()
    proof.reviewed_by = "admin"

    booking.payment_status = "rejected"

    db.commit()

    return RedirectResponse(
        url=f"/admin/bookings/{booking.id}",
        status_code=303,
    )


@app.post("/admin/bookings/{booking_id}/rematch")
def admin_booking_rematch(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(404, "Booking not found")

    match_result = rematch_booking_to_trip(db, booking_id)

    if match_result.matched and booking.trip_id:
        sync_booking_to_trip_passengers_by_id(db, booking_id, strict_replace_extra=False)

    db.commit()

    return RedirectResponse(
        url=f"/admin/bookings/{booking_id}",
        status_code=303,
    )


@app.post("/admin/bookings/{booking_id}/resync")
def admin_booking_resync(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(404, "Booking not found")

    if not booking.trip_id:
        raise HTTPException(400, "Booking is not linked to a trip")

    sync_booking_to_trip_passengers_by_id(
        db,
        booking_id,
        strict_replace_extra=False,
    )
    db.commit()

    return RedirectResponse(
        url=f"/admin/bookings/{booking_id}",
        status_code=303,
    )



# =======================
# Passenger portal
# =======================
@app.get("/portal/login", response_class=HTMLResponse)
def portal_login_page(request: Request):
    next_url = request.query_params.get("next", "/portal")
    if not next_url.startswith("/"):
        next_url = "/portal"

    if request.session.get("portal_booking_id"):
        return RedirectResponse(url="/portal", status_code=303)

    err = request.query_params.get("err", "")

    return templates.TemplateResponse(request, "portal/login.html", {
        "next_url": next_url,
        "error": err,
    })



@app.post("/portal/login")
def portal_login_submit(
    request: Request,
    unique_id: str = Form(""),
    email: str = Form(""),
    next: str = Form("/portal"),
    db: Session = Depends(get_db),
):
    next_url = (next or "/portal").strip()
    if not next_url.startswith("/"):
        next_url = "/portal"

    unique_id = (unique_id or "").strip()
    email_norm = (email or "").strip().lower()

    if not unique_id or not email_norm:
        return RedirectResponse(
            url=f"/portal/login?next={quote(next_url)}&err=missing",
            status_code=303,
        )

    if not unique_id.isdigit():
        return RedirectResponse(
            url=f"/portal/login?next={quote(next_url)}&err=badid",
            status_code=303,
        )

    unique_id_int = int(unique_id)

    booking = (
        db.query(Booking)
        .filter(Booking.external_id == unique_id_int)
        .first()
    )

    if not booking:
        return RedirectResponse(
            url=f"/portal/login?next={quote(next_url)}&err=notfound",
            status_code=303,
        )

    booking_email = (getattr(booking, "email", None) or "").strip().lower()
    if not booking_email or booking_email != email_norm:
        return RedirectResponse(
            url=f"/portal/login?next={quote(next_url)}&err=invalid",
            status_code=303,
        )

    request.session["portal_booking_id"] = booking.id
    return RedirectResponse(url=next_url, status_code=303)

@app.post("/portal/logout")
def portal_logout(request: Request):
    request.session.pop("portal_booking_id", None)
    return RedirectResponse(url="/portal/login", status_code=303)



@app.get("/portal", response_class=HTMLResponse)
def portal_dashboard(request: Request, db: Session = Depends(get_db)):
    r = _ensure_portal_or_redirect(request)
    if r:
        return r

    booking_id = request.session.get("portal_booking_id")
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        request.session.pop("portal_booking_id", None)
        return RedirectResponse(url="/portal/login?err=notfound", status_code=303)

    seats = (
        db.query(BookingSeat)
        .filter(BookingSeat.booking_id == booking.id)
        .order_by(BookingSeat.id.asc())
        .all()
    )

    selected_seats = _booking_selected_seats(booking)
    selected_seat = selected_seats[0] if selected_seats else None
    passenger_count = _booking_passenger_count(db, booking)

    ticket_lines = (
        db.query(BookingTicketLine)
        .filter(BookingTicketLine.booking_id == booking.id)
        .order_by(BookingTicketLine.id.asc())
        .all()
    )

    payment_proofs = (
        db.query(PaymentProof)
        .filter(PaymentProof.booking_id == booking.id)
        .order_by(PaymentProof.uploaded_at.desc(), PaymentProof.id.desc())
        .all()
    )

    trip = None
    trip_id = _resolve_booking_trip_id(db, booking)
    if trip_id:
        trip = db.query(Trip).filter(Trip.id == trip_id).first()

    payment_method_norm = _norm_payment_method(booking.payment_method)
    can_upload_payment_proof = _can_upload_payment_proof(booking)
    can_select_seat = _can_portal_select_seat(booking)
    can_change_seat = _can_portal_change_seat(booking)
    is_cash_booking = _cash_notice_active(booking)
    hours_until_departure = _hours_until_departure(booking)
    cash_confirmed = _cash_booking_confirmed(booking)
    can_view_ticket = _can_portal_view_ticket(booking)
    ticket_qr_available = _ticket_qr_available(booking)

    departure_time_obj = _extract_first_departure_time(getattr(booking, "time_range_raw", None))
    departure_time_display = departure_time_obj.strftime("%H:%M") if departure_time_obj else "—"

    stop_points = _booking_stop_points(booking)
   
    cancel_policy = _portal_cancellation_policy(booking, db)

    db.commit()

    return templates.TemplateResponse(
        request,
        "portal/dashboard.html",
        {
            "booking": booking,
            "seats": seats,
            "selected_seat": selected_seat,
            "selected_seats": selected_seats,
            "passenger_count": passenger_count,
            "ticket_lines": ticket_lines,
            "payment_proofs": payment_proofs,
            "trip": trip,
            "upload_ok": request.query_params.get("upload_ok", ""),
            "upload_err": request.query_params.get("upload_err", ""),
            "seat_ok": request.query_params.get("seat_ok", ""),
            "seat_err": request.query_params.get("seat_err", ""),
            "payment_ok": request.query_params.get("payment_ok", ""),
            "payment_err": request.query_params.get("payment_err", ""),
            "cash_ok": request.query_params.get("cash_ok", ""),
            "cash_err": request.query_params.get("cash_err", ""),
            "payment_method_norm": payment_method_norm,
            "can_upload_payment_proof": can_upload_payment_proof,
            "can_select_seat": can_select_seat,
            "can_change_seat": can_change_seat,
            "can_view_ticket": can_view_ticket,
            "ticket_qr_available": ticket_qr_available,
            "is_cash_booking": is_cash_booking,
            "cash_confirmed": cash_confirmed,
            "hours_until_departure": hours_until_departure,
            "departure_time_display": departure_time_display,
            "stop_points": stop_points,
            "cancel_policy": cancel_policy,
            "cancel_ok": request.query_params.get("cancel_ok"),
            "cancel_err": request.query_params.get("cancel_err"),
        },
    )

@app.post("/portal/payment-proof")
async def portal_upload_payment_proof(
    request: Request,
    note: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    r = _ensure_portal_or_redirect(request)
    if r:
        return r

    booking_id = request.session.get("portal_booking_id")
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        request.session.pop("portal_booking_id", None)
        return RedirectResponse(url="/portal/login?err=notfound", status_code=303)

    if _booking_is_cancelled_or_pending_cancellation(booking):
        return RedirectResponse(url="/portal?upload_err=cancelled", status_code=303)

    if not _can_upload_payment_proof(booking):
        return RedirectResponse(url="/portal?upload_err=payment_method", status_code=303)

    content_type = (file.content_type or "").lower().strip()
    if content_type not in ALLOWED_PAYMENT_PROOF_TYPES:
        return RedirectResponse(url="/portal?upload_err=type", status_code=303)

    data = await file.read()
    if not data:
        return RedirectResponse(url="/portal?upload_err=empty", status_code=303)

    if len(data) > 10 * 1024 * 1024:
        return RedirectResponse(url="/portal?upload_err=size", status_code=303)

    ext = ALLOWED_PAYMENT_PROOF_TYPES[content_type]
    stored_filename = f"{booking.id}_{uuid.uuid4().hex}{ext}"
    target_path = UPLOADS_DIR / stored_filename

    with open(target_path, "wb") as f:
        f.write(data)

    rel_path = f"/static/uploads/payment_proofs/{stored_filename}"

    proof = PaymentProof(
        booking_id=booking.id,
        original_filename=(file.filename or "").strip() or None,
        stored_filename=stored_filename,
        file_path=rel_path,
        content_type=content_type,
        file_size=len(data),
        note=(note or "").strip() or None,
    )
    db.add(proof)

    if booking.payment_status == "unpaid":
        booking.payment_status = "pending_review"

    db.commit()

    return RedirectResponse(url="/portal?upload_ok=1", status_code=303)


@app.post("/portal/payment-method")
def portal_change_payment_method(
    request: Request,
    payment_method: str = Form(""),
    db: Session = Depends(get_db),
):
    r = _ensure_portal_or_redirect(request)
    if r:
        return r

    booking_id = request.session.get("portal_booking_id")
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        request.session.pop("portal_booking_id", None)
        return RedirectResponse(url="/portal/login?err=notfound", status_code=303)

    if _booking_is_cancelled_or_pending_cancellation(booking):
        return RedirectResponse(url="/portal?payment_err=cancelled", status_code=303)

    new_method = _norm_payment_method(payment_method)
    if new_method not in {"bank", "paypal"}:
        return RedirectResponse(url="/portal?payment_err=method", status_code=303)

    old_method = _norm_payment_method(booking.payment_method)
    booking.payment_method = new_method

    if old_method == "cash":
        if booking.payment_status in {None, "", "unpaid", "rejected"}:
            booking.payment_status = "unpaid"

    db.commit()

    return RedirectResponse(url="/portal?payment_ok=method_changed", status_code=303)

@app.post("/portal/cash-confirm")
def portal_cash_confirm(
    request: Request,
    accept_terms: str | None = Form(None),
    db: Session = Depends(get_db),
):
    r = _ensure_portal_or_redirect(request)
    if r:
        return r

    booking_id = request.session.get("portal_booking_id")
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        request.session.pop("portal_booking_id", None)
        return RedirectResponse(url="/portal/login?err=notfound", status_code=303)

    if _booking_is_cancelled_or_pending_cancellation(booking):
        return RedirectResponse(url="/portal?cash_err=cancelled", status_code=303)

    if not _cash_notice_active(booking):
        return RedirectResponse(url="/portal?cash_err=method", status_code=303)

    if booking.booking_status == "cancelled":
        return RedirectResponse(url="/portal?cash_err=cancelled", status_code=303)

    if accept_terms != "1":
        return RedirectResponse(url="/portal?cash_err=terms", status_code=303)

    if booking.booking_status != "confirmed":
        booking.booking_status = "confirmed"

        stamp = _vienna_now_naive().strftime("%d.%m.%Y %H:%M")
        note_line = f"[PORTAL CASH CONFIRM] Terms accepted by customer at {stamp}"

        old_notes = (booking.notes or "").strip()
        if note_line not in old_notes:
            booking.notes = f"{old_notes}\n{note_line}".strip()

    db.commit()

    return RedirectResponse(url="/portal?cash_ok=confirmed", status_code=303)


@app.get("/portal/seats", response_class=HTMLResponse)
def portal_seats_page(request: Request, db: Session = Depends(get_db)):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    if _booking_is_cancelled_or_pending_cancellation(booking):
        return RedirectResponse(url="/portal?seat_err=cancelled", status_code=303)

    if _norm_payment_method(booking.payment_method) not in {"bank", "paypal"}:
        return RedirectResponse(url="/portal?seat_err=payment_method", status_code=303)

    if booking.payment_status != "paid":
        return RedirectResponse(url="/portal?seat_err=payment", status_code=303)

    if not _ensure_booking_has_service(booking):
        return RedirectResponse(url="/portal?seat_err=service", status_code=303)

    if _booking_has_admin_locked_seat(db, booking):
        return RedirectResponse(url="/portal?seat_err=change_locked", status_code=303)

    selected_seats = _booking_selected_seats(booking)
    selected_seat = selected_seats[0] if selected_seats else None
    passenger_count = _booking_passenger_count(db, booking)

    if selected_seats and not _can_portal_change_seat(booking):
        return RedirectResponse(url="/portal?seat_err=change_locked", status_code=303)

    taken_seats_raw = _service_taken_seats(db, booking, exclude_booking_id=booking.id)
    taken_seats = sorted(
        [str(x).strip() for x in taken_seats_raw if str(x).strip()],
        key=_seat_sort_key,
    )
    all_seats = _service_default_seat_map(booking)

    return templates.TemplateResponse(
        request,
        "portal/seats.html",
        {
            "booking": booking,
            "selected_seat": selected_seat,
            "selected_seats": selected_seats,
            "passenger_count": passenger_count,
            "seat_layout": _service_seat_layout(booking),
            "taken_seats": taken_seats,
            "all_seats": all_seats,
            "seat_err": request.query_params.get("seat_err", ""),
            "seat_ok": request.query_params.get("seat_ok", ""),
        },
    )


@app.get("/portal/seats/state")
def portal_seats_state(request: Request, db: Session = Depends(get_db)):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        raise HTTPException(status_code=401, detail="Portal login required")

    if _booking_is_cancelled_or_pending_cancellation(booking):
        raise HTTPException(status_code=403, detail="Booking is cancelled or pending cancellation")

    if _norm_payment_method(booking.payment_method) not in {"bank", "paypal"}:
        raise HTTPException(status_code=403, detail="Seat selection is not available for this payment method")

    if booking.payment_status != "paid":
        raise HTTPException(status_code=403, detail="Payment is not approved")

    if not _ensure_booking_has_service(booking):
        raise HTTPException(status_code=403, detail="Booking has no service/trip")

    taken_seats_raw = _service_taken_seats(db, booking, exclude_booking_id=booking.id)
    taken_seats = sorted(
        [str(x).strip() for x in taken_seats_raw if str(x).strip()],
        key=_seat_sort_key,
    )

    return {
        "ok": True,
        "taken_seats": taken_seats,
        "selected_seats": _booking_selected_seats(booking),
        "passenger_count": _booking_passenger_count(db, booking),
    }


@app.post("/portal/seats/assign")
async def portal_assign_seats(request: Request, db: Session = Depends(get_db)):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    if _booking_is_cancelled_or_pending_cancellation(booking):
        return RedirectResponse(url="/portal?seat_err=cancelled", status_code=303)

    if _norm_payment_method(booking.payment_method) not in {"bank", "paypal"}:
        return RedirectResponse(url="/portal?seat_err=payment_method", status_code=303)

    if booking.payment_status != "paid":
        return RedirectResponse(url="/portal?seat_err=payment", status_code=303)

    if not _ensure_booking_has_service(booking):
        return RedirectResponse(url="/portal?seat_err=service", status_code=303)

    if _booking_has_admin_locked_seat(db, booking):
        return RedirectResponse(url="/portal?seat_err=change_locked", status_code=303)

    selected_seats = _booking_selected_seats(booking)
    passenger_count = _booking_passenger_count(db, booking)

    if selected_seats and not _can_portal_change_seat(booking):
        return RedirectResponse(url="/portal?seat_err=change_locked", status_code=303)

    form = await request.form()
    raw_seat_nos = form.getlist("seat_nos")

    seat_nos: list[str] = []
    seen: set[str] = set()
    for raw in raw_seat_nos:
        seat_no = str(raw or "").strip()
        if not seat_no or seat_no in seen:
            continue
        seen.add(seat_no)
        seat_nos.append(seat_no)

    if len(seat_nos) != passenger_count:
        return RedirectResponse(url="/portal/seats?seat_err=missing", status_code=303)

    allowed = set(_service_default_seat_map(booking))
    if any(seat_no not in allowed for seat_no in seat_nos):
        return RedirectResponse(url="/portal/seats?seat_err=invalid", status_code=303)

    taken_seats = _service_taken_seats(db, booking, exclude_booking_id=booking.id)
    if any(seat_no in taken_seats for seat_no in seat_nos):
        return RedirectResponse(url="/portal/seats?seat_err=taken", status_code=303)

    _apply_booking_seat_assignment(
        db=db,
        booking=booking,
        seat_nos=seat_nos,
        selection_mode="manual",
    )

    db.commit()

    return RedirectResponse(url="/portal/seats?seat_ok=assigned", status_code=303)


@app.post("/portal/seats/select")
def portal_select_seat(
    request: Request,
    seat_no: str = Form(""),
    db: Session = Depends(get_db),
):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    if _booking_is_cancelled_or_pending_cancellation(booking):
        return RedirectResponse(url="/portal?seat_err=cancelled", status_code=303)

    if _norm_payment_method(booking.payment_method) not in {"bank", "paypal"}:
        return RedirectResponse(url="/portal?seat_err=payment_method", status_code=303)

    if booking.payment_status != "paid":
        return RedirectResponse(url="/portal?seat_err=payment", status_code=303)

    if not _ensure_booking_has_service(booking):
        return RedirectResponse(url="/portal?seat_err=service", status_code=303)

    # ADMIN LOCK GUARD:
    # ако админ вече е заключил място(а), пасажерът няма право да ги променя
    trip_passengers = (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking.id)
        .order_by(TripPassenger.id.asc())
        .all()
    )

    if any(getattr(p, "seat_locked_by_admin", False) for p in trip_passengers):
        return RedirectResponse(url="/portal?seat_err=change_locked", status_code=303)

    selected_seats = _booking_selected_seats(booking)
    passenger_count = _booking_passenger_count(db, booking)

    if selected_seats and not _can_portal_change_seat(booking):
        return RedirectResponse(url="/portal?seat_err=change_locked", status_code=303)

    seat_no = (seat_no or "").strip()
    if not seat_no:
        return RedirectResponse(url="/portal/seats?seat_err=missing", status_code=303)

    allowed = set(_service_default_seat_map(booking))
    if seat_no not in allowed:
        return RedirectResponse(url="/portal/seats?seat_err=invalid", status_code=303)

    taken_seats = _service_taken_seats(db, booking, exclude_booking_id=booking.id)
    if seat_no in taken_seats:
        return RedirectResponse(url="/portal/seats?seat_err=taken", status_code=303)

    if seat_no in selected_seats:
        return RedirectResponse(url="/portal?seat_ok=selected", status_code=303)

    final_rows = (
        db.query(BookingSeat)
        .filter(
            BookingSeat.booking_id == booking.id,
            BookingSeat.is_final == True,
        )
        .order_by(BookingSeat.id.asc())
        .all()
    )

    if len(final_rows) < passenger_count:
        _create_booking_seat_row(
            db=db,
            booking=booking,
            seat_no=seat_no,
            is_final=True,
            selection_mode="manual",
        )
    else:
        # ако вече са достигнати всички места, заменяме последното
        row = final_rows[-1]
        row.trip_id = getattr(booking, "trip_id", None)
        row.seat_no = seat_no
        row.is_final = True
        row.selection_mode = "manual"

    updated_selected_seats = _booking_selected_seats(booking)
    if seat_no not in updated_selected_seats:
        updated_selected_seats.append(seat_no)

    _sync_booking_seats_to_trip_passengers(db, booking.id, updated_selected_seats)

    db.commit()

    return RedirectResponse(url="/portal?seat_ok=selected", status_code=303)


@app.post("/portal/seats/auto-assign")
def portal_auto_assign_seat(
    request: Request,
    db: Session = Depends(get_db),
):
    booking, redirect_resp = _portal_booking_or_redirect(request, db)
    if redirect_resp:
        return redirect_resp

    if _booking_is_cancelled_or_pending_cancellation(booking):
        return RedirectResponse(url="/portal?seat_err=cancelled", status_code=303)

    if _norm_payment_method(booking.payment_method) not in {"bank", "paypal"}:
        return RedirectResponse(url="/portal?seat_err=payment_method", status_code=303)

    if booking.payment_status != "paid":
        return RedirectResponse(url="/portal?seat_err=payment", status_code=303)

    if not _ensure_booking_has_service(booking):
        return RedirectResponse(url="/portal?seat_err=service", status_code=303)

    if _booking_has_admin_locked_seat(db, booking):
        return RedirectResponse(url="/portal?seat_err=change_locked", status_code=303)

    selected_seats = _booking_selected_seats(booking)
    passenger_count = _booking_passenger_count(db, booking)

    if selected_seats and not _can_portal_change_seat(booking):
        return RedirectResponse(url="/portal?seat_err=change_locked", status_code=303)

    taken_seats = _service_taken_seats(db, booking, exclude_booking_id=booking.id)

    already_selected = set(selected_seats)
    need_count = max(0, passenger_count - len(selected_seats))

    if need_count <= 0:
        _sync_booking_seats_to_trip_passengers(db, booking.id, selected_seats)
        db.commit()
        return RedirectResponse(url="/portal?seat_ok=auto", status_code=303)

    free_seats: list[str] = []
    for seat_no in _service_default_seat_map(booking):
        if seat_no in taken_seats:
            continue
        if seat_no in already_selected:
            continue
        free_seats.append(seat_no)
        if len(free_seats) >= need_count:
            break

    if len(free_seats) < need_count:
        return RedirectResponse(url="/portal/seats?seat_err=full", status_code=303)

    for seat_no in free_seats:
        _create_booking_seat_row(
            db=db,
            booking=booking,
            seat_no=seat_no,
            is_final=True,
            selection_mode="auto",
        )

    updated_selected_seats = _booking_selected_seats(booking)
    for seat_no in free_seats:
        if seat_no not in updated_selected_seats:
            updated_selected_seats.append(seat_no)

    _sync_booking_seats_to_trip_passengers(db, booking.id, updated_selected_seats)

    db.commit()

    return RedirectResponse(url="/portal?seat_ok=auto", status_code=303)


@app.post("/set-language")
def set_language(
    request: Request,
    lang: str = Form(DEFAULT_LANG),
    next: str = Form("/"),
):
    _set_lang(request, lang)

    next_url = (next or "/").strip()
    if not next_url.startswith("/"):
        next_url = "/"

    return RedirectResponse(url=next_url, status_code=303)

# =======================
# Admin login
# =======================

@app.get("/admin", response_class=HTMLResponse)
def admin_home_page(request: Request):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    return templates.TemplateResponse(
        request,
        "admin/home.html",
        {},
    )


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    next_url = request.query_params.get("next", "/admin")
    if not next_url.startswith("/"):
        next_url = "/admin"

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
def admin_login(request: Request, password: str = Form(""), next: str = Form("/admin")):
    if not ADMIN_PASSWORD:
        raise HTTPException(500, "Missing ADMIN_PASSWORD env var")
    if password.strip() != ADMIN_PASSWORD:
        raise HTTPException(401, "Bad password")

    request.session["is_admin"] = True

    if not next or not next.startswith("/"):
        next = "/admin"

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


@app.get("/admin/trips", response_class=HTMLResponse)
def admin_trips_page(request: Request, db: Session = Depends(get_db)):
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

    return templates.TemplateResponse(
        request,
        "trips.html",
        {
            "trips": trips,
        },
    )


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

    trips_data = []

    for t in trips:
        live_payload = _build_driver_trip_live_payload(db, t.id)
        manifest = _load_driver_manifest(db, t.id)

        t.total_passengers = int(live_payload.get("displayTotal") or 0)
        t.driver_kept_passenger_count = int(live_payload.get("keptPassengerCount") or 0)
        t.driver_missing_passenger_count = int(live_payload.get("missingPassengerCount") or 0)
        t.driver_manifest_published = bool(manifest and manifest.get("publishedAt"))
        t.driver_manifest_published_at = manifest.get("publishedAt") if manifest else None

        route_from = (t.route_from or "").strip()
        route_to = (t.route_to or "").strip()

        dir_code = _direction_code_from_values(route_from, route_to) or "OTHER"

        if dir_code == "IK":
            label = "Innsbruck → Kyiv"
        elif dir_code == "KI":
            label = "Kyiv → Innsbruck"
        else:
            label = f"{route_from or '?'} → {route_to or '?'}"

        if t.date_time:
            trips_data.append({
                "id": int(t.id),
                "date": t.date_time.strftime("%Y-%m-%d"),
                "time": t.date_time.strftime("%H:%M"),
                "from": route_from,
                "to": route_to,
                "dir": dir_code,
                "label": label,
                "total": int(t.total_passengers or 0),
                "kept": int(t.driver_kept_passenger_count or 0),
                "missing": int(t.driver_missing_passenger_count or 0),
                "published": bool(t.driver_manifest_published),
                "publishedAt": t.driver_manifest_published_at,
            })

    return templates.TemplateResponse(
        request,
        "drivers_trips.html",
        {
            "trips": trips,
            "trips_data": trips_data,
        },
    )

@app.get("/drivers/trips/{trip_id}", response_class=HTMLResponse)
def driver_trip_detail(request: Request, trip_id: int, db: Session = Depends(get_db)):
    _ensure_driver(request)

    trip = crud.get_trip(db, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    if not trip.is_finalized:
        raise HTTPException(403, "Trip is not released (no Freigabe)")

    live_payload = _build_driver_trip_live_payload(db, trip_id)
    manifest = _load_driver_manifest(db, trip_id)

    return templates.TemplateResponse(
        request,
        "driver_trip_detail.html",
        {
            "trip": trip,
            "driver_projection": live_payload,
            "driver_booking_pending": live_payload.get("bookingPending", []),
            "driver_booking_coverage": live_payload.get("bookingCoverage", []),
            "driver_raw_passenger_count": int(live_payload.get("rawPassengerCount") or 0),
            "driver_kept_passenger_count": int(live_payload.get("keptPassengerCount") or 0),
            "driver_missing_passenger_count": int(live_payload.get("missingPassengerCount") or 0),
            "driver_display_total": int(live_payload.get("displayTotal") or 0),
            "driver_manifest_published": bool(manifest and manifest.get("publishedAt")),
            "driver_manifest_published_at": manifest.get("publishedAt") if manifest else None,
        },
    )

@app.get("/trips", response_class=HTMLResponse)
def trips_page(request: Request):
    r = _ensure_admin_or_redirect(request)
    if r:
        return r

    return RedirectResponse(url="/admin/trips", status_code=303)


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
            _safe_int_passenger_no(
                _effective_text(getattr(p, "manual_passenger_no", None), p.passenger_no)
            ),
            p.id,
        ),
    )

    portal_overlay = _build_trip_portal_overlay(db, trip_id, passengers)

    out = []
    for p in passengers:
        item = _passenger_to_api_dict(p)

        ov = portal_overlay.get(p.id, {})

        seat_override = (ov.get("seatNo") or "").strip()
        if seat_override:
            item["seatNo"] = seat_override

        item["paymentApproved"] = bool(ov.get("paymentApproved"))
        item["paymentBadgeLabel"] = "PAYMENT APPROVED" if item["paymentApproved"] else ""
        
        out.append(item)

    decorate_passenger_dicts_with_bad_clients(db, out)
    return JSONResponse(out)


@app.post("/api/trips/{trip_id}/publish-driver-manifest")
def api_publish_driver_manifest(
    trip_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _ensure_admin(request)

    trip = crud.get_trip(db, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")

    payload = _build_driver_manifest_payload(db, trip_id)
    _save_driver_manifest(db, trip_id, payload, published_by="admin")
    db.commit()

    saved_manifest = _load_driver_manifest(db, trip_id)
    if not saved_manifest:
        raise HTTPException(500, "Manifest save verification failed")

    return {
        "ok": True,
        "tripId": trip_id,
        "published": True,
        "displayTotal": int(saved_manifest.get("displayTotal") or 0),
        "publishedAt": saved_manifest.get("publishedAt"),
        "publishedBy": saved_manifest.get("publishedBy"),
        "passengerCount": len(saved_manifest.get("passengers") or []),
    }

@app.get("/api/trips/{trip_id}/driver-manifest-debug")
def api_driver_manifest_debug(trip_id: int, request: Request, db: Session = Depends(get_db)):
    _ensure_admin_or_driver(request)

    trip = crud.get_trip(db, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")

    manifest = _load_driver_manifest(db, trip_id)
    live_payload = _build_driver_trip_live_payload(db, trip_id)

    return {
        "tripId": trip_id,
        "manifest": manifest,
        "live": {
            "displayTotal": int(live_payload.get("displayTotal") or 0),
            "rawPassengerCount": int(live_payload.get("rawPassengerCount") or 0),
            "keptPassengerCount": int(live_payload.get("keptPassengerCount") or 0),
            "missingPassengerCount": int(live_payload.get("missingPassengerCount") or 0),
            "passengerCount": len(live_payload.get("passengers") or []),
        },
    }

@app.get("/api/trips/{trip_id}/driver-passengers")
def api_driver_list_passengers(trip_id: int, request: Request, db: Session = Depends(get_db)):
    is_admin = bool(request.session.get("is_admin"))
    is_driver = bool(request.session.get("is_driver"))

    if not is_admin and not is_driver:
        raise HTTPException(401, "Not authorized")

    trip = crud.get_trip(db, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")

    if is_driver and not is_admin and not trip.is_finalized:
        raise HTTPException(403, "Trip not released")

    payload = _build_driver_trip_live_payload(db, trip_id)
    return JSONResponse(payload.get("passengers", []))


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

    passenger_rows = [p for p, _trip in rows]
    overlay_by_trip: dict[int, dict[int, dict]] = {}

    trip_groups: dict[int, list[TripPassenger]] = {}
    for p in passenger_rows:
        if p.trip_id:
            trip_groups.setdefault(int(p.trip_id), []).append(p)

    for trip_id, trip_passengers in trip_groups.items():
        overlay_by_trip[trip_id] = _build_trip_portal_overlay(db, trip_id, trip_passengers)

    items = []
    for p, trip in rows:
        item = _passenger_to_api_dict(p, trip)

        ov = overlay_by_trip.get(int(trip.id), {}).get(p.id, {})

        seat_override = (ov.get("seatNo") or "").strip()
        if seat_override:
            item["seatNo"] = seat_override

        item["paymentApproved"] = bool(ov.get("paymentApproved"))
        item["paymentBadgeLabel"] = "PAYMENT APPROVED" if item["paymentApproved"] else ""

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

    p = db.query(TripPassenger).filter(TripPassenger.id == passenger_id).first()
    if not p:
        raise HTTPException(404, "Passenger not found")

    trip = db.query(Trip).filter(Trip.id == p.trip_id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")

    if is_driver and not is_admin and not trip.is_finalized:
        raise HTTPException(403, "Trip not released")

    if is_driver and not is_admin:
        allowed = {"checkedIn", "paid", "amount", "currency"}
        bad_keys = set(payload.keys()) - allowed
        if bad_keys:
            raise HTTPException(403, f"Driver cannot modify: {sorted(bad_keys)}")

    if "checkedIn" in payload:
        p.checked_in = bool(payload.get("checkedIn"))

    if "paid" in payload:
        p.paid = bool(payload.get("paid"))

    if "amount" in payload:
        raw_amount = payload.get("amount")
        if raw_amount in (None, ""):
            p.amount = None
        else:
            try:
                p.amount = float(raw_amount)
            except Exception:
                raise HTTPException(400, "Invalid amount")

    if "currency" in payload:
        p.currency = str(payload.get("currency") or "EUR").upper().strip()

    if is_admin and "oebb" in payload:
        p.oebb = bool(payload.get("oebb"))

    db.commit()
    db.refresh(p)

    return {
        "ok": True,
        "item": {
            "id": p.id,
            "checkedIn": bool(p.checked_in),
            "paid": bool(p.paid),
            "amount": float(p.amount) if p.amount is not None else None,
            "currency": getattr(p, "currency", "EUR"),
            "oebb": bool(getattr(p, "oebb", False)),
        },
    }

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

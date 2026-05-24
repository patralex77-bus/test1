from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import Booking, Trip


@dataclass
class BookingMatchResult:
    matched: bool
    booking_id: int | None = None
    trip_id: int | None = None
    reason: str | None = None
    detail: str | None = None
    candidates_count: int = 0


def _norm_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def _norm_city(s: str | None) -> str | None:
    if not s:
        return None

    x = str(s).strip().lower()
    x = re.sub(r"\s+", " ", x)

    mapping = {
        "київ": "kyiv",
        "киев": "kyiv",
        "kyiv": "kyiv",
        "kiev": "kyiv",

        "відень": "vienna",
        "вiдень": "vienna",
        "вена": "vienna",
        "wien": "vienna",
        "vienna": "vienna",

        "інсбрук": "innsbruck",
        "инсбрук": "innsbruck",
        "innsbruck": "innsbruck",

        "львів": "lviv",
        "львов": "lviv",
        "lviv": "lviv",

        "рівне": "rivne",
        "ровно": "rivne",
        "rivne": "rivne",

        "житомир": "zhytomyr",
        "zhitomir": "zhytomyr",
        "zhytomir": "zhytomyr",
        "zhytomyr": "zhytomyr",

        "зальцбург": "salzburg",
        "salzburg": "salzburg",

        "велс": "wels",
        "wels": "wels",

        "линц": "linz",
        "лінц": "linz",
        "linz": "linz",

        "st. poelten": "st. poelten",
        "st poelten": "st. poelten",
        "sankt poelten": "st. poelten",
        "st.pölten": "st. poelten",
        "st. pölten": "st. poelten",

        "villach": "villach",
        "виллах": "villach",

        "клагенфурт": "klagenfurt",
        "klagenfurt": "klagenfurt",

        "graz": "graz",
        "грац": "graz",

        "брюк-ан-дер-мур": "bruck an der mur",
        "bruck an der mur": "bruck an der mur",

        "львiв": "lviv",
        "рiвне": "rivne",
    }

    return mapping.get(x, x)


def _booking_date_only(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _booking_day_bounds(booking: Booking) -> tuple[datetime, datetime] | None:
    d = _booking_date_only(getattr(booking, "booking_date", None))
    if not d:
        return None
    return datetime.combine(d, time.min), datetime.combine(d, time.max)


def _same_route(booking: Booking, trip: Trip) -> bool:
    """
    Fallback match по passenger route_from / route_to.
    Това НЕ е primary logic, но е полезно като secondary fallback.
    """
    bf = _norm_city(getattr(booking, "route_from", None))
    bt = _norm_city(getattr(booking, "route_to", None))
    tf = _norm_city(getattr(trip, "route_from", None))
    tt = _norm_city(getattr(trip, "route_to", None))

    return bool(bf and bt and tf and tt and bf == tf and bt == tt)


def _same_bus_direction(booking: Booking, trip: Trip) -> bool:
    """
    Primary logic:
    booking.bus_from / booking.bus_to трябва да match-нат trip.route_from / trip.route_to
    """
    bf = _norm_city(getattr(booking, "bus_from", None))
    bt = _norm_city(getattr(booking, "bus_to", None))
    tf = _norm_city(getattr(trip, "route_from", None))
    tt = _norm_city(getattr(trip, "route_to", None))

    return bool(bf and bt and tf and tt and bf == tf and bt == tt)


def _same_day_candidates(db: Session, booking: Booking) -> list[Trip]:
    bounds = _booking_day_bounds(booking)
    if not bounds:
        return []

    start_dt, end_dt = bounds

    return (
        db.query(Trip)
        .filter(
            Trip.date_time.isnot(None),
            Trip.date_time >= start_dt,
            Trip.date_time <= end_dt,
        )
        .order_by(Trip.date_time.asc(), Trip.id.asc())
        .all()
    )


def _pick_unique(items: Iterable[Trip]) -> Trip | None:
    items = list(items)
    if len(items) == 1:
        return items[0]
    return None


def _find_trip_for_booking(db: Session, booking: Booking) -> tuple[Trip | None, str, int]:
    """
    Matching strategy:

    1. same day + bus_from/bus_to  (PRIMARY)
    2. same day + passenger route  (FALLBACK)
    3. if only one trip exists that day -> use it as last conservative fallback

    Returns:
      (trip_or_none, detail, candidates_count)
    """
    day_candidates = _same_day_candidates(db, booking)
    if not day_candidates:
        return None, "no trip candidates found for booking day", 0

    # 1) primary: same day + bus direction
    bus_candidates = [t for t in day_candidates if _same_bus_direction(booking, t)]
    trip = _pick_unique(bus_candidates)
    if trip:
        return trip, "matched by same day and bus direction", 1
    if len(bus_candidates) > 1:
        return None, "multiple trip candidates found for same day and bus direction", len(bus_candidates)

    # 2) fallback: same day + passenger route
    route_candidates = [t for t in day_candidates if _same_route(booking, t)]
    trip = _pick_unique(route_candidates)
    if trip:
        return trip, "matched by same day and passenger route", 1
    if len(route_candidates) > 1:
        return None, "multiple trip candidates found for same day and passenger route", len(route_candidates)

    # 3) last fallback: if exactly one trip exists that day
    trip = _pick_unique(day_candidates)
    if trip:
        return trip, "matched by same day only (single trip on that day)", 1

    return None, "no unique trip match", len(day_candidates)


def match_booking_to_trip(db: Session, booking: Booking) -> BookingMatchResult:
    if not booking:
        return BookingMatchResult(
            matched=False,
            booking_id=None,
            trip_id=None,
            reason="booking is None",
            detail="booking is None",
            candidates_count=0,
        )

    booking_day = _booking_date_only(getattr(booking, "booking_date", None))
    if not booking_day:
        return BookingMatchResult(
            matched=False,
            booking_id=getattr(booking, "id", None),
            trip_id=None,
            reason="booking_date is missing",
            detail="booking_date is missing",
            candidates_count=0,
        )

    trip, detail, candidates_count = _find_trip_for_booking(db, booking)
    if not trip:
        return BookingMatchResult(
            matched=False,
            booking_id=getattr(booking, "id", None),
            trip_id=None,
            reason="no unique trip match",
            detail=detail,
            candidates_count=candidates_count,
        )

    if booking.trip_id != trip.id:
        booking.trip_id = trip.id
        db.flush()

    return BookingMatchResult(
        matched=True,
        booking_id=getattr(booking, "id", None),
        trip_id=trip.id,
        reason="matched",
        detail=detail,
        candidates_count=1,
    )


def rematch_booking_to_trip(db: Session, booking_id: int) -> BookingMatchResult:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        return BookingMatchResult(
            matched=False,
            booking_id=booking_id,
            trip_id=None,
            reason="booking not found",
            detail="Booking not found",
            candidates_count=0,
        )

    result = match_booking_to_trip(db, booking)

    if not result.matched:
        booking.trip_id = None
        db.flush()

    return result
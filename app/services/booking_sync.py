from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import Booking, BookingSeat, BookingTicketLine, TripPassenger


@dataclass
class BookingSyncResult:
    ok: bool
    booking_id: int | None = None
    trip_id: int | None = None
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    skipped_count: int = 0
    detail: str | None = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _full_name(first_name: str | None, last_name: str | None) -> str | None:
    parts = [x.strip() for x in [first_name or "", last_name or ""] if x and x.strip()]
    if not parts:
        return None
    return " ".join(parts)


def _detect_oebb_from_ticket_lines(lines: Iterable[BookingTicketLine]) -> bool:
    for line in lines:
        raw = (line.ticket_type_raw or "").strip().lower()
        code = (line.ticket_type_code or "").strip().lower()
        if "öbb" in raw or "klimaticket" in raw or code == "obb":
            return True
    return False


def _ticket_line_summary(lines: list[BookingTicketLine]) -> tuple[str | None, float | None, str]:
    """
    Връща:
      voucher_or_amount_raw,
      amount_due_total,
      currency

    Правила:
    - ако е dual currency -> EUR е primary operational currency
    - ако е single currency -> ползваме line_total/currency
    - ако има много линии -> сумираме по primary currency
    """
    if not lines:
        return None, None, "EUR"

    if len(lines) == 1:
        line = lines[0]
        label = _clean(line.ticket_type_raw)

        if bool(getattr(line, "is_dual_currency", False)):
            amount_due = float(line.line_total_eur) if line.line_total_eur is not None else None
            currency = "EUR"

            raw_parts = []
            if label:
                raw_parts.append(label)
            if line.line_total_uah is not None:
                raw_parts.append(f"{float(line.line_total_uah):,.2f} UAH")
            if line.line_total_eur is not None:
                raw_parts.append(f"{float(line.line_total_eur):.2f} EUR")
            raw = " / ".join(raw_parts) if raw_parts else label

            return raw, amount_due, currency

        amount_due = float(line.line_total) if line.line_total is not None else None
        currency = _clean(line.currency) or "EUR"

        if label and amount_due is not None:
            return f"{label}: {amount_due:.2f} {currency}", amount_due, currency
        if label:
            return label, amount_due, currency

        return None, amount_due, currency

    # multiple lines
    parts: list[str] = []
    total = 0.0
    has_total = False
    currency = "EUR"

    for line in lines:
        label = _clean(line.ticket_type_raw) or "ticket"
        qty = int(line.qty or 0)

        if bool(getattr(line, "is_dual_currency", False)):
            line_total = float(line.line_total_eur) if line.line_total_eur is not None else None
            line_currency = "EUR"

            dual_text = []
            if line.line_total_uah is not None:
                dual_text.append(f"{float(line.line_total_uah):,.2f} UAH")
            if line.line_total_eur is not None:
                dual_text.append(f"{float(line.line_total_eur):.2f} EUR")

            if dual_text:
                parts.append(f"{label} x{qty} = {' / '.join(dual_text)}")
            else:
                parts.append(f"{label} x{qty}")
        else:
            line_total = float(line.line_total) if line.line_total is not None else None
            line_currency = _clean(line.currency) or "EUR"

            if line_total is not None:
                parts.append(f"{label} x{qty} = {line_total:.2f} {line_currency}")
            else:
                parts.append(f"{label} x{qty}")

        # за operational total: ако има смесени валути, EUR остава primary
        if line_total is not None:
            has_total = True
            total += line_total
            currency = line_currency or currency

    raw = "; ".join(parts) if parts else None
    return raw, (total if has_total else None), currency


def _sorted_booking_seats(booking: Booking) -> list[BookingSeat]:
    def seat_key(seat: BookingSeat):
        s = (seat.seat_no or "").strip()
        try:
            return (0, int(s))
        except Exception:
            return (1, s.lower())

    return sorted(list(booking.seats or []), key=seat_key)


def _sorted_trip_passengers_for_booking(db: Session, booking_id: int) -> list[TripPassenger]:
    return (
        db.query(TripPassenger)
        .filter(TripPassenger.booking_id == booking_id)
        .order_by(TripPassenger.id.asc())
        .all()
    )


def _apply_common_fields_from_booking(
    passenger: TripPassenger,
    booking: Booking,
    seat_no: str | None,
    passenger_no: str | None,
    voucher_raw: str | None,
    amount_due: float | None,
    currency: str,
    oebb: bool,
) -> bool:
    """
    Попълва само safe operational полета.
    НЕ пипа:
      - paid
      - amount
      - checked_in
      - manual_* полетата
    """
    changed = False

    new_full_name = _full_name(booking.first_name, booking.last_name)

    values = {
        "trip_id": booking.trip_id,
        "booking_id": booking.id,
        "source_uid": str(booking.external_id) if booking.external_id is not None else None,
        "passenger_no": passenger_no,
        "from_city": booking.route_from,
        "to_city": booking.route_to,
        "full_name": new_full_name,
        "seat_no": seat_no,
        "phone": booking.phone,
        "voucher_or_amount_raw": voucher_raw,
        "amount_due": amount_due,
        "currency": currency or "EUR",
        "oebb": bool(oebb),
    }

    for field_name, new_value in values.items():
        old_value = getattr(passenger, field_name)
        if old_value != new_value:
            setattr(passenger, field_name, new_value)
            changed = True

    return changed


def sync_booking_to_trip_passengers(
    db: Session,
    booking: Booking,
    *,
    strict_replace_extra: bool = False,
) -> BookingSyncResult:
    """
    Booking -> TripPassenger sync

    Правила:
    - трябва да има booking.trip_id
    - 1 seat = 1 TripPassenger
    - ако няма seats -> 1 passenger row без seat
    - dual currency -> EUR става operational currency в TripPassenger
    """
    if not booking:
        return BookingSyncResult(
            ok=False,
            detail="booking is None",
        )

    if not booking.trip_id:
        return BookingSyncResult(
            ok=False,
            booking_id=booking.id,
            detail="booking.trip_id is missing",
        )

    seats = _sorted_booking_seats(booking)
    linked_passengers = _sorted_trip_passengers_for_booking(db, booking.id)

    ticket_lines = list(booking.ticket_lines or [])
    voucher_raw, amount_due_total, currency = _ticket_line_summary(ticket_lines)
    oebb = _detect_oebb_from_ticket_lines(ticket_lines)

    target_rows: list[dict] = []

    if seats:
        seat_count = len(seats)

        per_seat_amount = None
        if amount_due_total is not None and seat_count > 0:
            per_seat_amount = round(amount_due_total / seat_count, 2)

        for idx, seat in enumerate(seats, start=1):
            target_rows.append({
                "seat_no": _clean(seat.seat_no),
                "passenger_no": str(idx),
                "voucher_raw": voucher_raw,
                "amount_due": per_seat_amount,
                "currency": currency,
                "oebb": oebb,
            })
    else:
        target_rows.append({
            "seat_no": None,
            "passenger_no": "1",
            "voucher_raw": voucher_raw,
            "amount_due": amount_due_total,
            "currency": currency,
            "oebb": oebb,
        })

    created_count = 0
    updated_count = 0
    unchanged_count = 0
    skipped_count = 0

    for idx, row in enumerate(target_rows):
        if idx < len(linked_passengers):
            passenger = linked_passengers[idx]
            changed = _apply_common_fields_from_booking(
                passenger=passenger,
                booking=booking,
                seat_no=row["seat_no"],
                passenger_no=row["passenger_no"],
                voucher_raw=row["voucher_raw"],
                amount_due=row["amount_due"],
                currency=row["currency"],
                oebb=row["oebb"],
            )
            if changed:
                passenger.updated_by = "booking-sync"
                updated_count += 1
            else:
                unchanged_count += 1
            continue

        passenger = TripPassenger(
            trip_id=booking.trip_id,
            booking_id=booking.id,
            source_uid=str(booking.external_id) if booking.external_id is not None else None,
            passenger_no=row["passenger_no"],
            from_city=booking.route_from,
            to_city=booking.route_to,
            full_name=_full_name(booking.first_name, booking.last_name),
            seat_no=row["seat_no"],
            phone=booking.phone,
            voucher_or_amount_raw=row["voucher_raw"],
            amount_due=row["amount_due"],
            currency=row["currency"],
            oebb=bool(row["oebb"]),
            checked_in=False,
            paid=False,
            amount=None,
            updated_by="booking-sync",
        )
        db.add(passenger)
        created_count += 1

    extra = linked_passengers[len(target_rows):]
    if extra:
        if strict_replace_extra:
            for passenger in extra:
                db.delete(passenger)
                skipped_count += 1
        else:
            skipped_count += len(extra)

    db.flush()

    return BookingSyncResult(
        ok=True,
        booking_id=booking.id,
        trip_id=booking.trip_id,
        created_count=created_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        skipped_count=skipped_count,
        detail="sync completed",
    )


def sync_booking_to_trip_passengers_by_id(
    db: Session,
    booking_id: int,
    *,
    strict_replace_extra: bool = False,
) -> BookingSyncResult:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        return BookingSyncResult(
            ok=False,
            booking_id=booking_id,
            detail="booking not found",
        )

    return sync_booking_to_trip_passengers(
        db,
        booking,
        strict_replace_extra=strict_replace_extra,
    )
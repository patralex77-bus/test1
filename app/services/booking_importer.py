from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    Booking,
    BookingSeat,
    BookingTicketLine,
    IncomingEmail,
)
from app.services.booking_matcher import match_booking_to_trip
from app.services.booking_parser import (
    ParsedBooking,
    parse_booking_email,
)
from app.services.booking_sync import sync_booking_to_trip_passengers


@dataclass
class ImportEmailPayload:
    message_id: str
    sender: str | None = None
    subject: str | None = None
    received_at: Any | None = None
    body_text: str | None = None
    body_html: str | None = None


@dataclass
class ImportResult:
    ok: bool
    status: str
    incoming_email_id: int | None = None
    booking_id: int | None = None
    external_id: int | None = None

    parse_errors: list[str] | None = None
    warnings: list[str] | None = None
    detail: str | None = None

    matched_trip_id: int | None = None
    match_reason: str | None = None

    sync_ok: bool | None = None
    sync_detail: str | None = None
    sync_created_count: int = 0
    sync_updated_count: int = 0
    sync_unchanged_count: int = 0
    sync_skipped_count: int = 0


def _upsert_incoming_email(db: Session, payload: ImportEmailPayload) -> IncomingEmail:
    """
    1) Ако message_id вече съществува -> update-ва суровите полета.
    2) Ако не съществува -> създава нов IncomingEmail.
    """
    existing = (
        db.query(IncomingEmail)
        .filter(IncomingEmail.message_id == payload.message_id)
        .first()
    )

    if existing:
        existing.sender = payload.sender
        existing.subject = payload.subject
        existing.received_at = payload.received_at
        existing.body_text = payload.body_text
        existing.body_html = payload.body_html
        return existing

    obj = IncomingEmail(
        message_id=payload.message_id,
        sender=payload.sender,
        subject=payload.subject,
        received_at=payload.received_at,
        body_text=payload.body_text,
        body_html=payload.body_html,
        fetch_status="new",
        parse_status="new",
    )
    db.add(obj)
    db.flush()
    return obj


def _find_booking_by_external_id(db: Session, external_id: int | None) -> Booking | None:
    if external_id is None:
        return None

    return (
        db.query(Booking)
        .filter(Booking.external_id == external_id)
        .first()
    )


def _apply_booking_fields(
    booking: Booking,
    parsed: ParsedBooking,
    incoming_email_id: int | None,
) -> None:
    """
    Пълни/обновява booking основните полета от ParsedBooking.
    """
    booking.incoming_email_id = incoming_email_id

    if parsed.external_id is not None:
        booking.external_id = parsed.external_id

    booking.booking_date = parsed.booking_date
    booking.time_range_raw = parsed.time_range_raw
    booking.time_from = parsed.time_from
    booking.time_to = parsed.time_to

    # BUS = trip-level
    booking.bus_name = parsed.bus_name
    booking.bus_route_raw = parsed.bus_route_raw
    booking.bus_from = parsed.bus_from
    booking.bus_to = parsed.bus_to

    # ROUTE = passenger-level
    booking.route_raw = parsed.route_raw
    booking.route_from = parsed.route_from
    booking.route_to = parsed.route_to

    booking.first_name = parsed.first_name
    booking.last_name = parsed.last_name
    booking.email = parsed.email
    booking.phone = parsed.phone
    booking.notes = parsed.notes

    booking.seats_raw = parsed.seats_raw
    booking.total = float(parsed.total) if parsed.total is not None else None
    booking.currency = parsed.currency or "EUR"
    booking.payment_method = parsed.payment_method

    booking.source = "email"
    booking.raw_text = parsed.raw_text

    if not booking.booking_status:
        booking.booking_status = "new"
    if not booking.payment_status:
        booking.payment_status = "unpaid"


def _replace_booking_seats(db: Session, booking: Booking, parsed: ParsedBooking) -> None:
    """
    Изтрива старите booking seats и записва новите.
    ВАЖНО: imported seat от email НЕ е final seat.
    """
    (
        db.query(BookingSeat)
        .filter(BookingSeat.booking_id == booking.id)
        .delete(synchronize_session=False)
    )

    for seat_no in parsed.seats:
        db.add(
            BookingSeat(
                booking_id=booking.id,
                trip_id=booking.trip_id,
                seat_no=str(seat_no).strip(),
                is_final=False,
                selection_mode="imported",
            )
        )


def _replace_booking_ticket_lines(db: Session, booking: Booking, parsed: ParsedBooking) -> None:
    """
    Изтрива старите ticket lines и записва новите.
    """
    (
        db.query(BookingTicketLine)
        .filter(BookingTicketLine.booking_id == booking.id)
        .delete(synchronize_session=False)
    )

    for line in parsed.ticket_lines:
        db.add(
            BookingTicketLine(
                booking_id=booking.id,
                ticket_type_raw=line.ticket_type_raw,
                ticket_type_code=line.ticket_type_code,
                qty=int(line.qty or 0),
                unit_price=float(line.unit_price) if line.unit_price is not None else None,
                line_total=float(line.line_total) if line.line_total is not None else None,
                currency=line.currency or "EUR",
                is_dual_currency=bool(line.is_dual_currency),
                unit_price_uah=float(line.unit_price_uah) if line.unit_price_uah is not None else None,
                unit_price_eur=float(line.unit_price_eur) if line.unit_price_eur is not None else None,
                line_total_uah=float(line.line_total_uah) if line.line_total_uah is not None else None,
                line_total_eur=float(line.line_total_eur) if line.line_total_eur is not None else None,
            )
        )


def import_booking_email(
    db: Session,
    payload: ImportEmailPayload,
    *,
    allow_update_existing: bool = True,
    fail_on_parse_errors: bool = False,
    run_matcher: bool = True,
    run_sync: bool = True,
    strict_sync_replace_extra: bool = False,
) -> ImportResult:
    """
    Основен entry point.

    flow:
      1. upsert incoming_email
      2. parse body_text
      3. create/update booking by external_id
      4. apply booking fields
      5. match booking -> trip
      6. replace seats
      7. replace ticket lines
      8. sync booking -> trip_passengers
      9. commit
    """
    try:
        raw_text = (payload.body_text or "").strip()

        if not payload.message_id:
            return ImportResult(
                ok=False,
                status="error",
                detail="Missing message_id",
            )

        if not raw_text:
            incoming = _upsert_incoming_email(db, payload)
            incoming.parse_status = "error"
            incoming.parse_error = "Empty body_text"
            incoming.fetch_status = "done"
            db.commit()

            return ImportResult(
                ok=False,
                status="error",
                incoming_email_id=incoming.id,
                detail="Empty body_text",
            )

        incoming = _upsert_incoming_email(db, payload)
        parsed = parse_booking_email(raw_text)

        if parsed.errors and fail_on_parse_errors:
            incoming.parse_status = "error"
            incoming.parse_error = " | ".join(parsed.errors)
            incoming.fetch_status = "done"
            db.commit()

            return ImportResult(
                ok=False,
                status="parse_error",
                incoming_email_id=incoming.id,
                external_id=parsed.external_id,
                parse_errors=parsed.errors,
                warnings=parsed.warnings,
                detail="Parse errors prevented import",
            )

        if parsed.external_id is None:
            incoming.parse_status = "error"
            incoming.parse_error = "Missing external_id"
            incoming.fetch_status = "done"
            db.commit()

            return ImportResult(
                ok=False,
                status="parse_error",
                incoming_email_id=incoming.id,
                parse_errors=parsed.errors,
                warnings=parsed.warnings,
                detail="Missing external_id",
            )

        booking = _find_booking_by_external_id(db, parsed.external_id)

        if booking and not allow_update_existing:
            incoming.parse_status = "duplicate"
            incoming.parse_error = None
            incoming.fetch_status = "done"
            db.commit()

            return ImportResult(
                ok=False,
                status="duplicate",
                incoming_email_id=incoming.id,
                booking_id=booking.id,
                external_id=booking.external_id,
                parse_errors=parsed.errors,
                warnings=parsed.warnings,
                detail="Booking already exists",
            )

        created = False

        if not booking:
            booking = Booking(
                external_id=parsed.external_id,
            )
            db.add(booking)
            db.flush()
            created = True

        _apply_booking_fields(booking, parsed, incoming.id)
        db.flush()

        matched_trip_id = None
        match_reason = None

        if run_matcher:
            match_result = match_booking_to_trip(db, booking)
            matched_trip_id = match_result.trip_id
            match_reason = match_result.detail or match_result.reason
            db.flush()

        _replace_booking_seats(db, booking, parsed)
        _replace_booking_ticket_lines(db, booking, parsed)
        db.flush()

        sync_ok = None
        sync_detail = None
        sync_created_count = 0
        sync_updated_count = 0
        sync_unchanged_count = 0
        sync_skipped_count = 0

        if run_sync and booking.trip_id:
            sync_result = sync_booking_to_trip_passengers(
                db,
                booking,
                strict_replace_extra=strict_sync_replace_extra,
            )
            sync_ok = sync_result.ok
            sync_detail = sync_result.detail
            sync_created_count = sync_result.created_count
            sync_updated_count = sync_result.updated_count
            sync_unchanged_count = sync_result.unchanged_count
            sync_skipped_count = sync_result.skipped_count
            db.flush()

        if parsed.errors:
            incoming.parse_status = "error"
            incoming.parse_error = " | ".join(parsed.errors)
        else:
            incoming.parse_status = "parsed"
            incoming.parse_error = None

        incoming.fetch_status = "done"

        db.commit()
        db.refresh(incoming)
        db.refresh(booking)

        return ImportResult(
            ok=True,
            status="created" if created else "updated",
            incoming_email_id=incoming.id,
            booking_id=booking.id,
            external_id=booking.external_id,
            parse_errors=parsed.errors,
            warnings=parsed.warnings,
            detail="Import completed",
            matched_trip_id=matched_trip_id,
            match_reason=match_reason,
            sync_ok=sync_ok,
            sync_detail=sync_detail,
            sync_created_count=sync_created_count,
            sync_updated_count=sync_updated_count,
            sync_unchanged_count=sync_unchanged_count,
            sync_skipped_count=sync_skipped_count,
        )

    except Exception as e:
        db.rollback()
        return ImportResult(
            ok=False,
            status="error",
            detail=f"Unhandled import exception: {e}",
        )
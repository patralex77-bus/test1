from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Booking
from app.services.booking_importer import ImportEmailPayload, import_booking_email
from app.services.mail_sender import send_booking_confirmation_email


def _read_field(raw: Any, key: str, default=None):
    if raw is None:
        return default

    if isinstance(raw, dict):
        return raw.get(key, default)

    return getattr(raw, key, default)


def _normalize_import_result(raw: Any) -> dict[str, Any]:
    """
    Нормализира резултата до стабилен dict за:
    - admin test import page
    - mailbox poller

    Поддържа:
    - dict
    - ImportResult object / dataclass / pydantic-like object
    """

    base = {
        "ok": False,
        "status": "error",
        "detail": None,
        "incoming_email_id": None,
        "booking_id": None,
        "external_id": None,
        "matched_trip_id": None,
        "match_reason": None,
        "sync_ok": False,
        "sync_detail": None,
        "sync_created_count": 0,
        "sync_updated_count": 0,
        "sync_unchanged_count": 0,
        "sync_skipped_count": 0,
        "parse_errors": [],
        "warnings": [],
    }

    if raw is None:
        base["detail"] = "import_booking_email returned None"
        return base

    # Поддръжка за dict / object
    base["ok"] = bool(_read_field(raw, "ok", False))
    base["status"] = _read_field(raw, "status", base["status"])
    base["detail"] = _read_field(raw, "detail", base["detail"])
    base["incoming_email_id"] = _read_field(raw, "incoming_email_id", None)
    base["booking_id"] = _read_field(raw, "booking_id", None)
    base["external_id"] = _read_field(raw, "external_id", None)
    base["matched_trip_id"] = _read_field(raw, "matched_trip_id", None)
    base["match_reason"] = _read_field(raw, "match_reason", None)
    base["sync_ok"] = bool(_read_field(raw, "sync_ok", False))
    base["sync_detail"] = _read_field(raw, "sync_detail", None)
    base["sync_created_count"] = int(_read_field(raw, "sync_created_count", 0) or 0)
    base["sync_updated_count"] = int(_read_field(raw, "sync_updated_count", 0) or 0)
    base["sync_unchanged_count"] = int(_read_field(raw, "sync_unchanged_count", 0) or 0)
    base["sync_skipped_count"] = int(_read_field(raw, "sync_skipped_count", 0) or 0)
    base["parse_errors"] = list(_read_field(raw, "parse_errors", []) or [])
    base["warnings"] = list(_read_field(raw, "warnings", []) or [])

    # fallback: ако няма explicit status, но ok=True
    if base["ok"] and (not base["status"] or base["status"] == "error"):
        base["status"] = "ok"

    return base


def _load_booking_for_result(db: Session, result: dict[str, Any]) -> Booking | None:
    booking_id = result.get("booking_id")
    if booking_id:
        try:
            return db.query(Booking).filter(Booking.id == int(booking_id)).first()
        except Exception:
            return None

    external_id = (result.get("external_id") or "").strip()
    if external_id:
        try:
            return db.query(Booking).filter(Booking.external_id == external_id).first()
        except Exception:
            return None

    return None


def run_booking_import(
    db: Session,
    *,
    message_id: str,
    received_at: datetime | None,
    sender: str | None,
    subject: str | None,
    body_text: str,
    allow_update_existing: bool = False,
    fail_on_parse_errors: bool = False,
    run_matcher: bool = True,
    run_sync: bool = True,
    strict_sync_replace_extra: bool = False,
    source: str = "manual_test",
    send_confirmation: bool = False,
    portal_base_url: str | None = None,
) -> dict[str, Any]:
    """
    Единна входна точка за:
    - /admin/bookings/test-import
    - IMAP poller
    """

    result: dict[str, Any] = {
        "ok": False,
        "status": "error",
        "detail": None,
        "incoming_email_id": None,
        "booking_id": None,
        "external_id": None,
        "matched_trip_id": None,
        "match_reason": None,
        "sync_ok": False,
        "sync_detail": None,
        "sync_created_count": 0,
        "sync_updated_count": 0,
        "sync_unchanged_count": 0,
        "sync_skipped_count": 0,
        "parse_errors": [],
        "warnings": [],
    }

    message_id = (message_id or "").strip()
    body_text = body_text or ""

    if not message_id:
        result["detail"] = "message_id is required"
        return result

    if not body_text.strip():
        result["detail"] = "body_text is required"
        return result

    payload = ImportEmailPayload(
        message_id=message_id,
        sender=(sender or "").strip() or None,
        subject=(subject or "").strip() or None,
        received_at=received_at,
        body_text=body_text,
        body_html=None,
    )

    try:
        raw = import_booking_email(
            db,
            payload,
            allow_update_existing=allow_update_existing,
            fail_on_parse_errors=fail_on_parse_errors,
            run_matcher=run_matcher,
            run_sync=run_sync,
            strict_sync_replace_extra=strict_sync_replace_extra,
        )

        result = _normalize_import_result(raw)

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass

        result["ok"] = False
        result["status"] = "error"
        result["detail"] = str(e)
        return result

    if not result.get("ok"):
        return result

    if send_confirmation:
        booking = _load_booking_for_result(db, result)
        if booking:
            try:
                send_booking_confirmation_email(
                    booking=booking,
                    portal_base_url=portal_base_url,
                )
            except Exception as e:
                warnings = list(result.get("warnings") or [])
                warnings.append(f"confirmation_email_failed: {e}")
                result["warnings"] = warnings

    return result
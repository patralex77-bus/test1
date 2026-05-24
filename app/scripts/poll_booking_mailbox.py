from __future__ import annotations

import email
import imaplib
import os
import re
import sys
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.parser import BytesParser
from email.policy import default
from pathlib import Path

from dotenv import load_dotenv


# Позволява директно пускане:
# python app/scripts/poll_booking_mailbox.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Зареждаме .env от root на проекта
load_dotenv(PROJECT_ROOT / ".env")


from app.db import SessionLocal  # noqa: E402
from app.services.booking_import_runner import run_booking_import  # noqa: E402


IMAP_HOST = os.getenv("IMAP_HOST", "").strip()
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USERNAME = os.getenv("IMAP_USERNAME", "").strip()
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "").strip()
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX").strip()

PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "").strip()

# Как да търсим нови писма:
# UNSEEN = само непрочетени
# ALL = всичко
IMAP_SEARCH_CRITERIA = os.getenv("IMAP_SEARCH_CRITERIA", "UNSEEN").strip() or "UNSEEN"

# Поведение след import
MARK_SEEN_ON_SUCCESS = os.getenv("IMAP_MARK_SEEN_ON_SUCCESS", "1").strip() == "1"
MARK_FLAGGED_ON_ERROR = os.getenv("IMAP_MARK_FLAGGED_ON_ERROR", "1").strip() == "1"

# Ако искаш допълнителен mail filter
ONLY_FROM_CONTAINS = os.getenv("IMAP_ONLY_FROM_CONTAINS", "").strip().lower()
ONLY_SUBJECT_CONTAINS = os.getenv("IMAP_ONLY_SUBJECT_CONTAINS", "").strip().lower()


def _decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return (value or "").strip()


def _extract_sender(msg: Message) -> str:
    return _decode_mime_header(msg.get("From"))


def _extract_subject(msg: Message) -> str:
    return _decode_mime_header(msg.get("Subject"))


def _extract_message_id(msg: Message, fallback_uid: str) -> str:
    raw = (msg.get("Message-ID") or "").strip()
    raw = raw.strip("<>").strip()
    return raw or f"imap-uid-{fallback_uid}"


def _extract_received_at(msg: Message) -> datetime | None:
    raw_date = msg.get("Date")
    if not raw_date:
        return None

    try:
        dt = email.utils.parsedate_to_datetime(raw_date)
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _strip_html(html_text: str) -> str:
    if not html_text:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\r", "", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _decode_part_bytes(part: Message) -> str:
    try:
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()
    except Exception:
        return ""


def _extract_text_body(msg: Message) -> str:
    """
    Предпочита text/plain.
    Ако няма, fallback към text/html -> strip html.
    """
    if msg.is_multipart():
        plain_parts: list[str] = []
        html_parts: list[str] = []

        for part in msg.walk():
            content_type = (part.get_content_type() or "").lower()
            content_disposition = (part.get("Content-Disposition") or "").lower()

            if "attachment" in content_disposition:
                continue

            text = _decode_part_bytes(part)
            if not text:
                continue

            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)

        if plain_parts:
            return "\n\n".join([p for p in plain_parts if p]).strip()

        if html_parts:
            html_merged = "\n\n".join([p for p in html_parts if p]).strip()
            return _strip_html(html_merged)

        return ""

    content_type = (msg.get_content_type() or "").lower()
    text = _decode_part_bytes(msg)

    if content_type == "text/html":
        return _strip_html(text)

    return text


def _mail_matches_filters(sender: str, subject: str) -> bool:
    sender_l = (sender or "").lower()
    subject_l = (subject or "").lower()

    if ONLY_FROM_CONTAINS and ONLY_FROM_CONTAINS not in sender_l:
        return False

    if ONLY_SUBJECT_CONTAINS and ONLY_SUBJECT_CONTAINS not in subject_l:
        return False

    return True


def _imap_connect() -> imaplib.IMAP4_SSL:
    if not IMAP_HOST:
        raise RuntimeError("IMAP_HOST is not configured")
    if not IMAP_USERNAME:
        raise RuntimeError("IMAP_USERNAME is not configured")
    if not IMAP_PASSWORD:
        raise RuntimeError("IMAP_PASSWORD is not configured")

    client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    client.login(IMAP_USERNAME, IMAP_PASSWORD)
    return client


def _imap_select_folder(client: imaplib.IMAP4_SSL) -> None:
    typ, _ = client.select(IMAP_FOLDER)
    if typ != "OK":
        raise RuntimeError(f"Cannot select IMAP folder: {IMAP_FOLDER}")


def _imap_search_uids(client: imaplib.IMAP4_SSL) -> list[bytes]:
    typ, data = client.uid("SEARCH", None, IMAP_SEARCH_CRITERIA)
    if typ != "OK":
        raise RuntimeError(f"IMAP SEARCH failed with criteria: {IMAP_SEARCH_CRITERIA}")

    raw = data[0] if data else b""
    if not raw:
        return []

    return [x for x in raw.split() if x]


def _imap_fetch_rfc822(client: imaplib.IMAP4_SSL, uid: bytes) -> bytes | None:
    typ, msg_data = client.uid("FETCH", uid, "(RFC822)")
    if typ != "OK" or not msg_data:
        return None

    for item in msg_data:
        if isinstance(item, tuple) and len(item) >= 2 and item[1]:
            return item[1]

    return None


def _imap_mark_seen(client: imaplib.IMAP4_SSL, uid: bytes) -> None:
    client.uid("STORE", uid, "+FLAGS", r"(\Seen)")


def _imap_mark_flagged(client: imaplib.IMAP4_SSL, uid: bytes) -> None:
    client.uid("STORE", uid, "+FLAGS", r"(\Flagged)")


def _process_one_message(db, uid: bytes, raw_bytes: bytes) -> dict:
    uid_text = uid.decode(errors="ignore")
    msg = BytesParser(policy=default).parsebytes(raw_bytes)

    sender = _extract_sender(msg)
    subject = _extract_subject(msg)

    if not _mail_matches_filters(sender, subject):
        return {
            "ok": True,
            "skipped": True,
            "detail": "Skipped by configured sender/subject filters",
            "message_id": f"imap-uid-{uid_text}",
            "uid": uid_text,
        }

    message_id = _extract_message_id(msg, uid_text)
    received_at = _extract_received_at(msg)
    body_text = _extract_text_body(msg)

    result = run_booking_import(
        db=db,
        message_id=message_id,
        received_at=received_at,
        sender=sender or None,
        subject=subject or None,
        body_text=body_text,
        allow_update_existing=True,
        fail_on_parse_errors=False,
        run_matcher=True,
        run_sync=True,
        strict_sync_replace_extra=False,
        source="imap_fetch",
        send_confirmation=True,
        portal_base_url=PORTAL_BASE_URL or None,
    )

    result["message_id"] = message_id
    result["uid"] = uid_text
    return result


def poll_booking_mailbox() -> None:
    client: imaplib.IMAP4_SSL | None = None
    db = SessionLocal()

    try:
        client = _imap_connect()
        _imap_select_folder(client)

        uids = _imap_search_uids(client)
        if not uids:
            print("No new mails.")
            return

        print(f"Found {len(uids)} mail(s) in {IMAP_FOLDER}.")

        for uid in uids:
            uid_text = uid.decode(errors="ignore")

            try:
                raw_bytes = _imap_fetch_rfc822(client, uid)
                if not raw_bytes:
                    print(f"[UID {uid_text}] fetch failed or empty message")
                    if MARK_FLAGGED_ON_ERROR:
                        _imap_mark_flagged(client, uid)
                    continue

                result = _process_one_message(db, uid, raw_bytes)

                if result.get("skipped"):
                    print(f"[UID {uid_text}] skipped: {result.get('detail')}")
                    if MARK_SEEN_ON_SUCCESS:
                        _imap_mark_seen(client, uid)
                    continue

                if result.get("ok"):
                    print(
                        f"[UID {uid_text}] OK | "
                        f"booking_id={result.get('booking_id')} | "
                        f"external_id={result.get('external_id')} | "
                        f"detail={result.get('detail')}"
                    )
                    if MARK_SEEN_ON_SUCCESS:
                        _imap_mark_seen(client, uid)
                else:
                    print(
                        f"[UID {uid_text}] ERROR | "
                        f"message_id={result.get('message_id')} | "
                        f"detail={result.get('detail')}"
                    )
                    if MARK_FLAGGED_ON_ERROR:
                        _imap_mark_flagged(client, uid)

            except Exception as e:
                print(f"[UID {uid_text}] EXCEPTION | {e}")
                try:
                    db.rollback()
                except Exception:
                    pass

                if client is not None and MARK_FLAGGED_ON_ERROR:
                    try:
                        _imap_mark_flagged(client, uid)
                    except Exception:
                        pass

    finally:
        try:
            db.close()
        except Exception:
            pass

        if client is not None:
            try:
                client.close()
            except Exception:
                pass
            try:
                client.logout()
            except Exception:
                pass


if __name__ == "__main__":
    poll_booking_mailbox()
from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage

from app.models import Booking


COMPANY_NAME = os.getenv("COMPANY_NAME", "Austria Express")

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()

SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME or "bookingsystem@bus-express.at").strip()
SMTP_REPLY_TO = os.getenv("SMTP_REPLY_TO", SMTP_FROM).strip()

SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "1").strip() == "1"
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "0").strip() == "1"
SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "30"))

PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "").strip().rstrip("/")


def _safe_str(value) -> str:
    return str(value).strip() if value is not None else ""


def _html(value) -> str:
    return html.escape(_safe_str(value))


def _customer_name(booking: Booking) -> str:
    full_name = f"{_safe_str(getattr(booking, 'first_name', ''))} {_safe_str(getattr(booking, 'last_name', ''))}".strip()
    return full_name or "Passenger"


def _route_text(booking: Booking) -> str:
    route_from = _safe_str(getattr(booking, "route_from", "")) or "—"
    route_to = _safe_str(getattr(booking, "route_to", "")) or "—"
    return f"{route_from} → {route_to}"


def _booking_date_text(booking: Booking) -> str:
    booking_date = getattr(booking, "booking_date", None)
    if not booking_date:
        return "—"

    try:
        return booking_date.strftime("%d.%m.%Y")
    except Exception:
        return _safe_str(booking_date) or "—"


def _payment_method_text(booking: Booking) -> str:
    raw = _safe_str(getattr(booking, "payment_method", ""))
    if not raw:
        return "—"

    norm = raw.lower()
    mapping = {
        "bank": "Bank transfer",
        "paypal": "PayPal",
        "cash": "Cash",
    }
    return mapping.get(norm, raw)


def _payment_status_text(booking: Booking) -> str:
    return _safe_str(getattr(booking, "payment_status", "")) or "—"


def _booking_status_text(booking: Booking) -> str:
    return _safe_str(getattr(booking, "booking_status", "")) or "—"


def _external_id_text(booking: Booking) -> str:
    ext = _safe_str(getattr(booking, "external_id", ""))
    if ext:
        return ext
    booking_id = getattr(booking, "id", None)
    return str(booking_id) if booking_id is not None else "—"


def _total_text(booking: Booking) -> str:
    total = getattr(booking, "total", None)
    currency = _safe_str(getattr(booking, "currency", ""))

    if total is None:
        return "—"

    try:
        return f"{float(total):.2f} {currency}".strip()
    except Exception:
        return f"{total} {currency}".strip()


def _portal_link(portal_base_url: str | None = None) -> str | None:
    base = (portal_base_url or PORTAL_BASE_URL or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/portal"


def _build_confirmation_subject(booking: Booking) -> str:
    return f"{COMPANY_NAME} — booking request received ({_external_id_text(booking)})"


def _build_confirmation_text(booking: Booking, portal_base_url: str | None = None) -> str:
    customer_name = _customer_name(booking)
    unique_id = _external_id_text(booking)
    route_text = _route_text(booking)
    booking_date = _booking_date_text(booking)
    payment_method = _payment_method_text(booking)
    payment_status = _payment_status_text(booking)
    booking_status = _booking_status_text(booking)
    total_text = _total_text(booking)
    portal_url = _portal_link(portal_base_url=portal_base_url)
    recipient_email = _safe_str(getattr(booking, "email", "")) or "your e-mail"

    lines = [
        f"Hello {customer_name},",
        "",
        f"We received your booking request successfully.",
        "",
        f"Unique ID: {unique_id}",
        f"Route: {route_text}",
        f"Booking date: {booking_date}",
        f"Total: {total_text}",
        f"Payment method: {payment_method}",
        f"Payment status: {payment_status}",
        f"Booking status: {booking_status}",
    ]

    if portal_url:
        lines += [
            "",
            "Passenger cabinet / portal:",
            portal_url,
            "",
            f"Login information:",
            f"- Use your Unique ID: {unique_id}",
            f"- Use your e-mail: {recipient_email}",
        ]

    lines += [
        "",
        "Payment instructions:",
        "Please complete the payment according to your selected payment method.",
        "After payment approval your booking can continue to the next processing step in the passenger cabinet.",
        "",
        "If you selected Bank transfer or PayPal, please upload payment proof in the passenger cabinet after payment if required.",
        "",
        f"Best regards,",
        COMPANY_NAME,
    ]

    return "\n".join(lines)


def _build_confirmation_html(booking: Booking, portal_base_url: str | None = None) -> str:
    customer_name = _html(_customer_name(booking))
    unique_id = _html(_external_id_text(booking))
    route_text = _html(_route_text(booking))
    booking_date = _html(_booking_date_text(booking))
    payment_method = _html(_payment_method_text(booking))
    payment_status = _html(_payment_status_text(booking))
    booking_status = _html(_booking_status_text(booking))
    total_text = _html(_total_text(booking))
    recipient_email = _html(_safe_str(getattr(booking, "email", "")) or "your e-mail")
    portal_url = _portal_link(portal_base_url=portal_base_url)

    portal_block = ""
    if portal_url:
        portal_url_html = html.escape(portal_url, quote=True)
        portal_block = f"""
        <div style="margin-top:16px; border:1px solid #e2e8f0; border-radius:16px; padding:16px; background:#f8fafc;">
          <div style="font-weight:700; margin-bottom:8px;">Passenger cabinet / portal</div>
          <div style="margin-bottom:8px;">
            <a href="{portal_url_html}" style="color:#0f172a; text-decoration:underline;">{portal_url_html}</a>
          </div>
          <div>Use your <b>Unique ID</b>: {unique_id}</div>
          <div>Use your <b>e-mail</b>: {recipient_email}</div>
        </div>
        """

    return f"""\
<!doctype html>
<html>
  <body style="margin:0; padding:24px; background:#f8fafc; font-family:Arial,Helvetica,sans-serif; color:#0f172a;">
    <div style="max-width:680px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:20px; overflow:hidden;">
      <div style="padding:24px 24px 18px 24px; border-bottom:1px solid #e2e8f0;">
        <div style="font-size:12px; font-weight:800; letter-spacing:.14em; color:#334155;">{html.escape(COMPANY_NAME.upper())}</div>
        <div style="margin-top:6px; font-size:26px; line-height:1.1; font-weight:800;">Booking request received</div>
        <div style="margin-top:8px; font-size:14px; color:#64748b;">Unique ID: {unique_id}</div>
      </div>

      <div style="padding:24px;">
        <div style="font-size:15px; margin-bottom:14px;">Hello {customer_name},</div>
        <div style="font-size:15px; line-height:1.6; margin-bottom:18px;">
          We received your booking request successfully.
        </div>

        <div style="border:1px solid #e2e8f0; border-radius:16px; padding:16px; background:#ffffff;">
          <div style="margin-bottom:8px;"><b>Route:</b> {route_text}</div>
          <div style="margin-bottom:8px;"><b>Booking date:</b> {booking_date}</div>
          <div style="margin-bottom:8px;"><b>Total:</b> {total_text}</div>
          <div style="margin-bottom:8px;"><b>Payment method:</b> {payment_method}</div>
          <div style="margin-bottom:8px;"><b>Payment status:</b> {payment_status}</div>
          <div><b>Booking status:</b> {booking_status}</div>
        </div>

        {portal_block}

        <div style="margin-top:18px; border:1px solid #dbeafe; border-radius:16px; padding:16px; background:#f8fbff;">
          <div style="font-weight:700; margin-bottom:8px;">Payment instructions</div>
          <div style="font-size:14px; line-height:1.6;">
            Please complete the payment according to your selected payment method.<br>
            After payment approval your booking can continue to the next processing step in the passenger cabinet.<br><br>
            If you selected Bank transfer or PayPal, please upload payment proof in the passenger cabinet after payment if required.
          </div>
        </div>

        <div style="margin-top:20px; font-size:14px; line-height:1.6;">
          Best regards,<br>
          <b>{html.escape(COMPANY_NAME)}</b>
        </div>
      </div>
    </div>
  </body>
</html>
"""


def send_booking_confirmation_email(
    booking: Booking,
    portal_base_url: str | None = None,
) -> bool:
    recipient = _safe_str(getattr(booking, "email", ""))
    if not recipient:
        return False

    if not SMTP_HOST:
        raise RuntimeError("SMTP_HOST is not configured")
    if not SMTP_PORT:
        raise RuntimeError("SMTP_PORT is not configured")
    if not SMTP_FROM:
        raise RuntimeError("SMTP_FROM is not configured")
    if SMTP_USERNAME and not SMTP_PASSWORD:
        raise RuntimeError("SMTP_PASSWORD is not configured")

    subject = _build_confirmation_subject(booking)
    text_body = _build_confirmation_text(booking, portal_base_url=portal_base_url)
    html_body = _build_confirmation_html(booking, portal_base_url=portal_base_url)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = recipient

    if SMTP_REPLY_TO:
        msg["Reply-To"] = SMTP_REPLY_TO

    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
            smtp.ehlo()
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
            smtp.ehlo()
            if SMTP_USE_TLS:
                smtp.starttls()
                smtp.ehlo()
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)

    return True


def send_booking_cancellation_email(
    *,
    to_email: str,
    passenger_name: str,
    external_id: str,
    refund_percent: int,
    refund_amount,
    currency: str | None,
    departure_at,
) -> None:
    if not to_email:
        return

    departure_text = departure_at.strftime("%d.%m.%Y %H:%M") if departure_at else "—"
    refund_text = f"{refund_percent}%"
    if refund_amount is not None and currency:
        refund_text += f" ({refund_amount} {currency})"

    subject = f"Cancellation request received – Booking {external_id}"

    body = f"""Hello {passenger_name or ''},

Your cancellation request has been received.

Booking Unique ID: {external_id}
Departure: {departure_text}
Calculated cancellation policy: {refund_text}

Your request was forwarded for review in our system.

Best regards,
Austria Express
"""

    send_smtp_email(
        to_email=to_email,
        subject=subject,
        body=body,
    )

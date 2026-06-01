from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage

from app.models import Booking


# ============================================================
# Company configuration
# ============================================================

COMPANY_NAME = os.getenv("COMPANY_NAME", "Austria Express").strip()

COMPANY_LEGAL_NAME = os.getenv(
    "COMPANY_LEGAL_NAME",
    "Bus Express Tm von Austrian Incentive Service / Austrian Incentive Service GmbH",
).strip()

COMPANY_ADDRESS = os.getenv(
    "COMPANY_ADDRESS",
    "Landstrasser Hauptstrasse 2, Büro Top Nr.M2.01.27",
).strip()

COMPANY_CITY = os.getenv(
    "COMPANY_CITY",
    "A-1030 Wien",
).strip()

COMPANY_PHONE = os.getenv(
    "COMPANY_PHONE",
    "+43 676 849 113 200",
).strip()

COMPANY_EMAIL = os.getenv(
    "COMPANY_EMAIL",
    "office@austria-express.eu",
).strip()


# ============================================================
# SMTP configuration
# ============================================================

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()

SMTP_FROM = os.getenv(
    "SMTP_FROM",
    SMTP_USERNAME or "bookingsystem@bus-express.at",
).strip()

SMTP_REPLY_TO = os.getenv(
    "SMTP_REPLY_TO",
    SMTP_FROM,
).strip()

SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "1").strip() == "1"
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "0").strip() == "1"
SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "30"))

PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "").strip().rstrip("/")


# ============================================================
# General helpers
# ============================================================

def _safe_str(value) -> str:
    return str(value).strip() if value is not None else ""


def _html(value) -> str:
    return html.escape(_safe_str(value), quote=True)


def _customer_name(booking: Booking) -> str:
    full_name = (
        f"{_safe_str(getattr(booking, 'first_name', ''))} "
        f"{_safe_str(getattr(booking, 'last_name', ''))}"
    ).strip()

    return full_name


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


def _external_id_text(booking: Booking) -> str:
    external_id = _safe_str(getattr(booking, "external_id", ""))

    if external_id:
        return external_id

    booking_id = getattr(booking, "id", None)

    if booking_id is not None:
        return str(booking_id)

    return "—"


def _total_text(booking: Booking) -> str:
    total = getattr(booking, "total", None)
    currency = _safe_str(getattr(booking, "currency", "")) or "EUR"

    if total is None:
        return "—"

    try:
        return f"{float(total):.2f} {currency}"
    except Exception:
        return f"{total} {currency}".strip()


# ============================================================
# Payment and booking labels
# ============================================================

def _payment_method_text(
    booking: Booking,
    language: str = "en",
) -> str:
    raw = _safe_str(getattr(booking, "payment_method", ""))

    if not raw:
        return "—"

    norm = raw.lower()

    if language == "uk":
        mapping = {
            "bank": "Банківський переказ",
            "bank transfer": "Банківський переказ",
            "paypal": "PayPal",
            "cash": "Готівка",
        }
    else:
        mapping = {
            "bank": "Bank transfer",
            "bank transfer": "Bank transfer",
            "paypal": "PayPal",
            "cash": "Cash",
        }

    return mapping.get(norm, raw)


def _payment_status_text(
    booking: Booking,
    language: str = "en",
) -> str:
    raw = _safe_str(getattr(booking, "payment_status", ""))

    if not raw:
        return "—"

    norm = raw.lower()

    if language == "uk":
        mapping = {
            "unpaid": "Не оплачено",
            "pending_review": "Очікує перевірки",
            "paid": "Оплачено",
            "approved": "Підтверджено",
            "rejected": "Відхилено",
        }
    else:
        mapping = {
            "unpaid": "Unpaid",
            "pending_review": "Pending review",
            "paid": "Paid",
            "approved": "Approved",
            "rejected": "Rejected",
        }

    return mapping.get(norm, raw)


def _booking_status_text(
    booking: Booking,
    language: str = "en",
) -> str:
    raw = _safe_str(getattr(booking, "booking_status", ""))

    if not raw:
        return "—"

    norm = raw.lower()

    if language == "uk":
        mapping = {
            "new": "Нове бронювання",
            "confirmed": "Підтверджено",
            "pending_payment": "Очікує оплати",
            "cancelled": "Скасовано",
            "cancellation_requested": "Подано запит на скасування",
        }
    else:
        mapping = {
            "new": "New booking",
            "confirmed": "Confirmed",
            "pending_payment": "Pending payment",
            "cancelled": "Cancelled",
            "cancellation_requested": "Cancellation requested",
        }

    return mapping.get(norm, raw)


# ============================================================
# Portal URL
# ============================================================

def _portal_link(portal_base_url: str | None = None) -> str | None:
    """
    Връща правилен portal URL.

    Поддържа и двата ENV варианта:
      PORTAL_BASE_URL=https://example.com
      PORTAL_BASE_URL=https://example.com/portal

    Коригира и вече сгрешена стойност:
      https://example.com/portal/portal
    """
    base = (portal_base_url or PORTAL_BASE_URL or "").strip().rstrip("/")

    if not base:
        return None

    while base.lower().endswith("/portal/portal"):
        base = base[:-7].rstrip("/")

    if base.lower().endswith("/portal"):
        return base

    return f"{base}/portal"


# ============================================================
# Company signature
# ============================================================

def _company_signature_text() -> str:
    return "\n".join([
        "Best regards,",
        COMPANY_NAME,
        COMPANY_LEGAL_NAME,
        COMPANY_ADDRESS,
        COMPANY_CITY,
        f"Mob: {COMPANY_PHONE}",
        f"Email: {COMPANY_EMAIL}",
    ])


def _company_signature_html() -> str:
    return f"""
      <div style="margin-top:22px; font-size:13px; line-height:1.65; color:#334155;">
        <div>Best regards,</div>
        <div style="font-weight:700; color:#0f172a;">{_html(COMPANY_NAME)}</div>
        <div>{_html(COMPANY_LEGAL_NAME)}</div>
        <div>{_html(COMPANY_ADDRESS)}</div>
        <div>{_html(COMPANY_CITY)}</div>
        <div>Mob: {_html(COMPANY_PHONE)}</div>
        <div>
          Email:
          <a href="mailto:{_html(COMPANY_EMAIL)}"
             style="color:#0f172a; text-decoration:underline;">
            {_html(COMPANY_EMAIL)}
          </a>
        </div>
      </div>
    """


# ============================================================
# SMTP sending
# ============================================================

def _validate_smtp_configuration() -> None:
    if not SMTP_HOST:
        raise RuntimeError("SMTP_HOST is not configured")

    if not SMTP_PORT:
        raise RuntimeError("SMTP_PORT is not configured")

    if not SMTP_FROM:
        raise RuntimeError("SMTP_FROM is not configured")

    if SMTP_USERNAME and not SMTP_PASSWORD:
        raise RuntimeError("SMTP_PASSWORD is not configured")


def _send_email_message(message: EmailMessage) -> None:
    _validate_smtp_configuration()

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(
            SMTP_HOST,
            SMTP_PORT,
            timeout=SMTP_TIMEOUT,
        ) as smtp:
            smtp.ehlo()

            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)

            smtp.send_message(message)

        return

    with smtplib.SMTP(
        SMTP_HOST,
        SMTP_PORT,
        timeout=SMTP_TIMEOUT,
    ) as smtp:
        smtp.ehlo()

        if SMTP_USE_TLS:
            smtp.starttls()
            smtp.ehlo()

        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)

        smtp.send_message(message)


def send_smtp_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> bool:
    """
    Универсален SMTP helper.

    Използва се и за confirmation email,
    и за cancellation email.
    """
    recipient = _safe_str(to_email)

    if not recipient:
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM
    message["To"] = recipient

    if SMTP_REPLY_TO:
        message["Reply-To"] = SMTP_REPLY_TO

    message.set_content(body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    _send_email_message(message)

    return True


# ============================================================
# Booking confirmation email
# ============================================================

def _build_confirmation_subject(booking: Booking) -> str:
    unique_id = _external_id_text(booking)

    return (
        f"{COMPANY_NAME} — Запит на бронювання отримано / "
        f"Booking request received ({unique_id})"
    )


def _build_confirmation_text(
    booking: Booking,
    portal_base_url: str | None = None,
) -> str:
    customer_name = _customer_name(booking)

    uk_customer_name = customer_name or "пасажире"
    en_customer_name = customer_name or "Passenger"

    unique_id = _external_id_text(booking)
    route_text = _route_text(booking)
    booking_date = _booking_date_text(booking)
    total_text = _total_text(booking)

    payment_method_uk = _payment_method_text(booking, language="uk")
    payment_method_en = _payment_method_text(booking, language="en")

    payment_status_uk = _payment_status_text(booking, language="uk")
    payment_status_en = _payment_status_text(booking, language="en")

    booking_status_uk = _booking_status_text(booking, language="uk")
    booking_status_en = _booking_status_text(booking, language="en")

    portal_url = _portal_link(portal_base_url=portal_base_url)

    recipient_email = (
        _safe_str(getattr(booking, "email", ""))
        or "your e-mail"
    )

    lines = [
        f"Вітаємо, {uk_customer_name}!",
        "",
        "Ми успішно отримали ваш запит на бронювання.",
        "",
        f"Унікальний ID: {unique_id}",
        f"Маршрут: {route_text}",
        f"Дата поїздки: {booking_date}",
        f"Загальна сума: {total_text}",
        f"Спосіб оплати: {payment_method_uk}",
        f"Статус оплати: {payment_status_uk}",
        f"Статус бронювання: {booking_status_uk}",
    ]

    if portal_url:
        lines += [
            "",
            "Особистий кабінет пасажира",
            "",
            (
                "Це ваш персональний портал клієнта. У ньому ви можете "
                "перевірити актуальний статус бронювання та квитка, "
                "переглянути статус оплати, за потреби завантажити "
                "підтвердження оплати та отримати доступ до наступних "
                "доступних кроків для вашого бронювання."
            ),
            "",
            f"Відкрити портал: {portal_url}",
            "",
            "Дані для входу:",
            f"- Унікальний ID: {unique_id}",
            f"- E-mail: {recipient_email}",
        ]

    lines += [
        "",
        "------------------------------------------------------------",
        "",
        f"Hello {en_customer_name},",
        "",
        "We received your booking request successfully.",
        "",
        f"Unique ID: {unique_id}",
        f"Route: {route_text}",
        f"Travel date: {booking_date}",
        f"Total: {total_text}",
        f"Payment method: {payment_method_en}",
        f"Payment status: {payment_status_en}",
        f"Booking status: {booking_status_en}",
    ]

    if portal_url:
        lines += [
            "",
            "Passenger cabinet / portal",
            "",
            (
                "This is your personal customer portal. You can use it "
                "to check the current status of your booking and ticket, "
                "review the payment status, upload proof of payment when "
                "needed, and access the next available steps for your booking."
            ),
            "",
            f"Open portal: {portal_url}",
            "",
            "Login information:",
            f"- Unique ID: {unique_id}",
            f"- E-mail: {recipient_email}",
        ]

    lines += [
        "",
        _company_signature_text(),
    ]

    return "\n".join(lines)


def _booking_details_table_html(
    *,
    route_text: str,
    booking_date: str,
    total_text: str,
    payment_method: str,
    payment_status: str,
    booking_status: str,
    language: str,
) -> str:
    if language == "uk":
        labels = {
            "route": "Маршрут",
            "date": "Дата поїздки",
            "total": "Загальна сума",
            "payment_method": "Спосіб оплати",
            "payment_status": "Статус оплати",
            "booking_status": "Статус бронювання",
        }
    else:
        labels = {
            "route": "Route",
            "date": "Travel date",
            "total": "Total",
            "payment_method": "Payment method",
            "payment_status": "Payment status",
            "booking_status": "Booking status",
        }

    rows = [
        (labels["route"], route_text),
        (labels["date"], booking_date),
        (labels["total"], total_text),
        (labels["payment_method"], payment_method),
        (labels["payment_status"], payment_status),
        (labels["booking_status"], booking_status),
    ]

    rows_html = ""

    for index, (label, value) in enumerate(rows):
        border_style = (
            "border-bottom:1px solid #e2e8f0;"
            if index < len(rows) - 1
            else ""
        )

        rows_html += f"""
          <tr>
            <td style="
              width:42%;
              padding:10px 0;
              vertical-align:top;
              font-size:13px;
              color:#64748b;
              {border_style}
            ">
              {_html(label)}
            </td>

            <td style="
              padding:10px 0;
              vertical-align:top;
              font-size:13px;
              font-weight:700;
              color:#0f172a;
              {border_style}
            ">
              {_html(value)}
            </td>
          </tr>
        """

    return f"""
      <table role="presentation"
             width="100%"
             cellpadding="0"
             cellspacing="0"
             style="border-collapse:collapse;">
        {rows_html}
      </table>
    """


def _portal_block_html(
    *,
    portal_url: str,
    unique_id: str,
    recipient_email: str,
    language: str,
) -> str:
    portal_url_html = _html(portal_url)

    if language == "uk":
        title = "Особистий кабінет пасажира"

        description = (
            "Це ваш персональний портал клієнта. У ньому ви можете "
            "перевірити актуальний статус бронювання та квитка, "
            "переглянути статус оплати, за потреби завантажити "
            "підтвердження оплати та отримати доступ до наступних "
            "доступних кроків для вашого бронювання."
        )

        button_label = "Відкрити кабінет пасажира"
        login_title = "Дані для входу"
        unique_id_label = "Унікальний ID"
        email_label = "E-mail"

    else:
        title = "Passenger cabinet / portal"

        description = (
            "This is your personal customer portal. You can use it "
            "to check the current status of your booking and ticket, "
            "review the payment status, upload proof of payment when "
            "needed, and access the next available steps for your booking."
        )

        button_label = "Open passenger portal"
        login_title = "Login information"
        unique_id_label = "Unique ID"
        email_label = "E-mail"

    return f"""
      <div style="
        margin-top:16px;
        border:1px solid #cbd5e1;
        border-radius:14px;
        padding:16px;
        background:#f8fafc;
      ">
        <div style="
          font-size:15px;
          font-weight:700;
          color:#0f172a;
        ">
          {_html(title)}
        </div>

        <div style="
          margin-top:8px;
          font-size:13px;
          line-height:1.65;
          color:#475569;
        ">
          {_html(description)}
        </div>

        <div style="margin-top:14px;">
          <a href="{portal_url_html}"
             style="
               display:inline-block;
               padding:11px 15px;
               border-radius:10px;
               background:#0f172a;
               color:#ffffff;
               font-size:13px;
               font-weight:700;
               text-decoration:none;
             ">
            {_html(button_label)}
          </a>
        </div>

        <div style="
          margin-top:14px;
          padding-top:12px;
          border-top:1px solid #e2e8f0;
          font-size:13px;
          line-height:1.7;
          color:#334155;
        ">
          <div style="font-weight:700; color:#0f172a;">
            {_html(login_title)}
          </div>

          <div style="margin-top:4px;">
            {_html(unique_id_label)}:
            <strong>{_html(unique_id)}</strong>
          </div>

          <div>
            {_html(email_label)}:
            <strong>{_html(recipient_email)}</strong>
          </div>
        </div>

        <div style="
          margin-top:10px;
          font-size:11px;
          line-height:1.5;
          color:#64748b;
          word-break:break-all;
        ">
          {_html(portal_url)}
        </div>
      </div>
    """


def _build_confirmation_html(
    booking: Booking,
    portal_base_url: str | None = None,
) -> str:
    customer_name = _customer_name(booking)

    uk_customer_name = customer_name or "пасажире"
    en_customer_name = customer_name or "Passenger"

    unique_id = _external_id_text(booking)
    route_text = _route_text(booking)
    booking_date = _booking_date_text(booking)
    total_text = _total_text(booking)

    payment_method_uk = _payment_method_text(booking, language="uk")
    payment_method_en = _payment_method_text(booking, language="en")

    payment_status_uk = _payment_status_text(booking, language="uk")
    payment_status_en = _payment_status_text(booking, language="en")

    booking_status_uk = _booking_status_text(booking, language="uk")
    booking_status_en = _booking_status_text(booking, language="en")

    recipient_email = (
        _safe_str(getattr(booking, "email", ""))
        or "your e-mail"
    )

    portal_url = _portal_link(portal_base_url=portal_base_url)

    portal_block_uk = ""
    portal_block_en = ""

    if portal_url:
        portal_block_uk = _portal_block_html(
            portal_url=portal_url,
            unique_id=unique_id,
            recipient_email=recipient_email,
            language="uk",
        )

        portal_block_en = _portal_block_html(
            portal_url=portal_url,
            unique_id=unique_id,
            recipient_email=recipient_email,
            language="en",
        )

    details_uk = _booking_details_table_html(
        route_text=route_text,
        booking_date=booking_date,
        total_text=total_text,
        payment_method=payment_method_uk,
        payment_status=payment_status_uk,
        booking_status=booking_status_uk,
        language="uk",
    )

    details_en = _booking_details_table_html(
        route_text=route_text,
        booking_date=booking_date,
        total_text=total_text,
        payment_method=payment_method_en,
        payment_status=payment_status_en,
        booking_status=booking_status_en,
        language="en",
    )

    return f"""\
<!doctype html>
<html>
  <body style="
    margin:0;
    padding:18px;
    background:#f1f5f9;
    font-family:Arial,Helvetica,sans-serif;
    color:#0f172a;
  ">
    <div style="
      max-width:680px;
      margin:0 auto;
      background:#ffffff;
      border:1px solid #e2e8f0;
      border-radius:16px;
      overflow:hidden;
    ">
      <div style="
        padding:20px 22px;
        border-bottom:1px solid #e2e8f0;
        background:#ffffff;
      ">
        <div style="
          font-size:12px;
          font-weight:800;
          letter-spacing:.14em;
          color:#334155;
        ">
          {_html(COMPANY_NAME.upper())}
        </div>

        <div style="
          margin-top:7px;
          font-size:22px;
          line-height:1.25;
          font-weight:800;
          color:#0f172a;
        ">
          Запит на бронювання отримано
        </div>

        <div style="
          margin-top:4px;
          font-size:15px;
          line-height:1.4;
          color:#64748b;
        ">
          Booking request received
        </div>

        <div style="
          margin-top:9px;
          font-size:13px;
          color:#475569;
        ">
          Unique ID:
          <strong>{_html(unique_id)}</strong>
        </div>
      </div>

      <div style="padding:22px;">
        <div style="
          font-size:15px;
          line-height:1.65;
          color:#0f172a;
        ">
          Вітаємо, <strong>{_html(uk_customer_name)}</strong>!
        </div>

        <div style="
          margin-top:8px;
          font-size:14px;
          line-height:1.65;
          color:#334155;
        ">
          Ми успішно отримали ваш запит на бронювання.
        </div>

        <div style="
          margin-top:14px;
          border:1px solid #e2e8f0;
          border-radius:14px;
          padding:4px 14px;
          background:#ffffff;
        ">
          {details_uk}
        </div>

        {portal_block_uk}

        <div style="
          margin:24px 0;
          border-top:1px solid #e2e8f0;
        "></div>

        <div style="
          font-size:15px;
          line-height:1.65;
          color:#0f172a;
        ">
          Hello <strong>{_html(en_customer_name)}</strong>,
        </div>

        <div style="
          margin-top:8px;
          font-size:14px;
          line-height:1.65;
          color:#334155;
        ">
          We received your booking request successfully.
        </div>

        <div style="
          margin-top:14px;
          border:1px solid #e2e8f0;
          border-radius:14px;
          padding:4px 14px;
          background:#ffffff;
        ">
          {details_en}
        </div>

        {portal_block_en}

        {_company_signature_html()}
      </div>
    </div>
  </body>
</html>
"""


def send_booking_confirmation_email(
    booking: Booking,
    portal_base_url: str | None = None,
) -> bool:
    """
    Изпраща bilingual booking confirmation:
      1) Ukrainian
      2) English
    """
    recipient = _safe_str(getattr(booking, "email", ""))

    if not recipient:
        return False

    subject = _build_confirmation_subject(booking)

    text_body = _build_confirmation_text(
        booking,
        portal_base_url=portal_base_url,
    )

    html_body = _build_confirmation_html(
        booking,
        portal_base_url=portal_base_url,
    )

    return send_smtp_email(
        to_email=recipient,
        subject=subject,
        body=text_body,
        html_body=html_body,
    )


# ============================================================
# Booking cancellation email
# ============================================================

def _cancellation_subject(external_id: str) -> str:
    return (
        f"{COMPANY_NAME} — Запит на скасування отримано / "
        f"Cancellation request received ({external_id})"
    )


def _cancellation_text(
    *,
    passenger_name: str,
    external_id: str,
    departure_text: str,
    refund_text: str,
) -> str:
    display_name_uk = passenger_name or "пасажире"
    display_name_en = passenger_name or "Passenger"

    return f"""Вітаємо, {display_name_uk}!

Ми отримали ваш запит на скасування бронювання.

Унікальний ID: {external_id}
Відправлення: {departure_text}
Розрахунок відповідно до умов скасування: {refund_text}

Ваш запит передано на перевірку. Після його обробки статус буде оновлено в системі.

------------------------------------------------------------

Hello {display_name_en},

Your cancellation request has been received.

Booking Unique ID: {external_id}
Departure: {departure_text}
Calculated cancellation policy: {refund_text}

Your request has been forwarded for review. The status will be updated in the system after processing.

{_company_signature_text()}
"""


def _cancellation_html(
    *,
    passenger_name: str,
    external_id: str,
    departure_text: str,
    refund_text: str,
) -> str:
    display_name_uk = passenger_name or "пасажире"
    display_name_en = passenger_name or "Passenger"

    return f"""\
<!doctype html>
<html>
  <body style="
    margin:0;
    padding:18px;
    background:#f1f5f9;
    font-family:Arial,Helvetica,sans-serif;
    color:#0f172a;
  ">
    <div style="
      max-width:680px;
      margin:0 auto;
      background:#ffffff;
      border:1px solid #e2e8f0;
      border-radius:16px;
      overflow:hidden;
    ">
      <div style="
        padding:20px 22px;
        border-bottom:1px solid #e2e8f0;
      ">
        <div style="
          font-size:12px;
          font-weight:800;
          letter-spacing:.14em;
          color:#334155;
        ">
          {_html(COMPANY_NAME.upper())}
        </div>

        <div style="
          margin-top:7px;
          font-size:22px;
          font-weight:800;
          color:#0f172a;
        ">
          Запит на скасування отримано
        </div>

        <div style="
          margin-top:4px;
          font-size:15px;
          color:#64748b;
        ">
          Cancellation request received
        </div>
      </div>

      <div style="padding:22px;">
        <div style="
          font-size:14px;
          line-height:1.65;
          color:#334155;
        ">
          Вітаємо, <strong>{_html(display_name_uk)}</strong>!<br><br>
          Ми отримали ваш запит на скасування бронювання.
        </div>

        <div style="
          margin-top:14px;
          border:1px solid #e2e8f0;
          border-radius:14px;
          padding:14px;
          font-size:13px;
          line-height:1.75;
          color:#334155;
        ">
          <div>
            <strong>Унікальний ID:</strong>
            {_html(external_id)}
          </div>

          <div>
            <strong>Відправлення:</strong>
            {_html(departure_text)}
          </div>

          <div>
            <strong>Розрахунок відповідно до умов скасування:</strong>
            {_html(refund_text)}
          </div>
        </div>

        <div style="
          margin-top:12px;
          font-size:14px;
          line-height:1.65;
          color:#334155;
        ">
          Ваш запит передано на перевірку. Після його обробки статус буде оновлено в системі.
        </div>

        <div style="
          margin:24px 0;
          border-top:1px solid #e2e8f0;
        "></div>

        <div style="
          font-size:14px;
          line-height:1.65;
          color:#334155;
        ">
          Hello <strong>{_html(display_name_en)}</strong>,<br><br>
          Your cancellation request has been received.
        </div>

        <div style="
          margin-top:14px;
          border:1px solid #e2e8f0;
          border-radius:14px;
          padding:14px;
          font-size:13px;
          line-height:1.75;
          color:#334155;
        ">
          <div>
            <strong>Booking Unique ID:</strong>
            {_html(external_id)}
          </div>

          <div>
            <strong>Departure:</strong>
            {_html(departure_text)}
          </div>

          <div>
            <strong>Calculated cancellation policy:</strong>
            {_html(refund_text)}
          </div>
        </div>

        <div style="
          margin-top:12px;
          font-size:14px;
          line-height:1.65;
          color:#334155;
        ">
          Your request has been forwarded for review. The status will be updated in the system after processing.
        </div>

        {_company_signature_html()}
      </div>
    </div>
  </body>
</html>
"""


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
    recipient = _safe_str(to_email)

    if not recipient:
        return

    if departure_at:
        try:
            departure_text = departure_at.strftime("%d.%m.%Y %H:%M")
        except Exception:
            departure_text = _safe_str(departure_at) or "—"
    else:
        departure_text = "—"

    refund_text = f"{int(refund_percent or 0)}%"

    if refund_amount is not None and currency:
        refund_text += f" ({refund_amount} {currency})"

    subject = _cancellation_subject(external_id)

    text_body = _cancellation_text(
        passenger_name=passenger_name,
        external_id=external_id,
        departure_text=departure_text,
        refund_text=refund_text,
    )

    html_body = _cancellation_html(
        passenger_name=passenger_name,
        external_id=external_id,
        departure_text=departure_text,
        refund_text=refund_text,
    )

    send_smtp_email(
        to_email=recipient,
        subject=subject,
        body=text_body,
        html_body=html_body,
    )
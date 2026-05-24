from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


TICKET_LINE_SINGLE_RE = re.compile(
    r"^(?P<ticket_type>.+?)\s+(?P<qty>\d+)\s*x\s+(?P<unit>\d[\d,]*(?:[.]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?P<currency>€|EUR|UAH)\s*=\s*(?P<total>\d[\d,]*(?:[.]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:€|EUR|UAH)?$",
    re.IGNORECASE,
)

TICKET_LINE_DUAL_RE = re.compile(
    r"""^(?P<ticket_type>.+?)\s+
        (?P<qty>\d+)\s*x\s+
        (?P<unit_uah>\d[\d,]*(?:\.\d{1,2})?)\s*UAH\s*/\s*
        (?P<unit_eur>\d[\d,]*(?:\.\d{1,2})?)\s*(?:€|EUR)\s*=\s*
        (?P<total_uah>\d[\d,]*(?:\.\d{1,2})?)\s*UAH\s*/\s*
        (?P<total_eur>\d[\d,]*(?:\.\d{1,2})?)\s*(?:€|EUR)
    $""",
    re.IGNORECASE | re.VERBOSE,
)

TOTAL_RE = re.compile(
    r"(?P<amount>\d[\d,]*(?:\.\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?P<currency>€|EUR|UAH)?",
    re.IGNORECASE,
)

_CITY_SPLIT_RE = re.compile(r"\s*[-–—]\s*")
_MULTI_SPACE_RE = re.compile(r"\s+")

KNOWN_FIELD_NAMES = {
    "Unique ID",
    "Booking date",
    "Time",
    "Bus",
    "Route",
    "Seats",
    "Ticket types price",
    "Total",
    "Payment",
    "First Name",
    "Last Name",
    "E-Mail",
    "Phone",
    "Notes",
}


def _clean_text(s: str | None) -> str | None:
    if s is None:
        return None
    s = str(s).strip()
    s = _MULTI_SPACE_RE.sub(" ", s)
    return s or None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _to_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None

    s = value.strip().replace(" ", "")

    # 8,840.00 -> 8840.00
    if "," in s and "." in s:
        s = s.replace(",", "")
    # 100,00 -> 100.00
    elif "," in s and "." not in s:
        s = s.replace(",", ".")

    try:
        return Decimal(s)
    except (InvalidOperation, AttributeError):
        return None


def _normalize_currency(value: str | None) -> str:
    v = (value or "").strip().upper()
    if v in {"€", "EUR"}:
        return "EUR"
    if v == "UAH":
        return "UAH"
    return v or "EUR"


def _normalize_ticket_type(raw: str | None) -> str | None:
    s = (raw or "").strip().lower()

    if s == "дорослий":
        return "adult"

    if s in {"дитина (5-12,99)", "дитина(5-12,99)"}:
        return "child_5_12"

    if s in {"дитина (0-4,99)", "дитина(0-4,99)"}:
        return "child_0_4"

    if s == "öbb vorteilskarte / klimaticket":
        return "obb"

    return "unknown" if s else None


def _parse_datetime_ddmmyyyy(value: str | None) -> datetime | None:
    value = _clean(value)
    if not value:
        return None

    for fmt in ("%d.%m.%Y", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def _parse_time_range(value: str | None) -> tuple[str | None, str | None]:
    value = _clean(value)
    if not value or " - " not in value:
        return None, None

    left, right = value.split(" - ", 1)
    return _clean(left), _clean(right)


def _parse_seats(value: str | None) -> list[str]:
    value = _clean(value)
    if not value:
        return []

    parts = [x.strip() for x in value.split(",")]
    return [p for p in parts if p]


def _split_bus_direction(raw: str | None) -> tuple[str | None, str | None]:
    """
    Bus field examples:
      'Київ - Відень'
      'Інсбрук - Відень - Київ (Літо), 08:00 - 10:30'
      'Villach - Graz - Wien - Lviv - Rivne - Zhytomir - Kyiv'

    Правило:
      - bus_from = първата точка
      - bus_to   = последната точка
    """
    raw = _clean_text(raw)
    if not raw:
        return None, None

    # Махаме trailing време след запетая
    base = raw.split(",")[0].strip()

    # Махаме съдържание в скоби
    base = re.sub(r"\([^)]*\)", "", base).strip()
    base = _clean_text(base) or ""

    parts = [p.strip() for p in _CITY_SPLIT_RE.split(base) if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[-1]

    return None, None


def _split_passenger_route(raw: str | None) -> tuple[str | None, str | None]:
    """
    Passenger route examples:
      'Київ Відень'
      'Wien Lviv'
      'Linz Zhytomir'

    MVP:
      - first token = from
      - last token  = to
    """
    raw = _clean_text(raw)
    if not raw:
        return None, None

    parts = [p.strip() for p in raw.split(" ") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[-1]

    return None, None


def _parse_total(value: str | None) -> tuple[Decimal | None, str]:
    value = _clean(value)
    if not value:
        return None, "EUR"

    m = TOTAL_RE.search(value)
    if not m:
        return None, "EUR"

    amount = _to_decimal(m.group("amount"))
    currency = _normalize_currency(m.group("currency"))
    return amount, currency


@dataclass
class ParsedTicketLine:
    ticket_type_raw: str | None = None
    ticket_type_code: str | None = None
    qty: int | None = None

    # backward-compatible primary values
    unit_price: Decimal | None = None
    line_total: Decimal | None = None
    currency: str = "EUR"

    # dual-currency support
    is_dual_currency: bool = False
    unit_price_uah: Decimal | None = None
    unit_price_eur: Decimal | None = None
    line_total_uah: Decimal | None = None
    line_total_eur: Decimal | None = None


@dataclass
class ParsedBooking:
    external_id: int | None = None

    booking_date: datetime | None = None

    time_range_raw: str | None = None
    time_from: str | None = None
    time_to: str | None = None

    # Bus / trip-level
    bus_name: str | None = None
    bus_route_raw: str | None = None
    bus_from: str | None = None
    bus_to: str | None = None

    # Passenger route-level
    route_raw: str | None = None
    route_from: str | None = None
    route_to: str | None = None

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None

    seats_raw: str | None = None
    seats: list[str] = field(default_factory=list)

    total: Decimal | None = None
    currency: str = "EUR"
    payment_method: str | None = None

    ticket_lines: list[ParsedTicketLine] = field(default_factory=list)

    raw_text: str | None = None
    raw_fields: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _parse_ticket_line_single(value: str) -> ParsedTicketLine | None:
    m = TICKET_LINE_SINGLE_RE.match(value)
    if not m:
        return None

    ticket_type_raw = _clean(m.group("ticket_type"))
    qty_raw = m.group("qty")
    unit_raw = m.group("unit")
    total_raw = m.group("total")
    currency_raw = m.group("currency")

    try:
        qty = int(qty_raw)
    except Exception:
        qty = None

    currency = _normalize_currency(currency_raw)
    unit_price = _to_decimal(unit_raw)
    line_total = _to_decimal(total_raw)

    return ParsedTicketLine(
        ticket_type_raw=ticket_type_raw,
        ticket_type_code=_normalize_ticket_type(ticket_type_raw),
        qty=qty,
        unit_price=unit_price,
        line_total=line_total,
        currency=currency,
        is_dual_currency=False,
        unit_price_uah=unit_price if currency == "UAH" else None,
        unit_price_eur=unit_price if currency == "EUR" else None,
        line_total_uah=line_total if currency == "UAH" else None,
        line_total_eur=line_total if currency == "EUR" else None,
    )


def _parse_ticket_line_dual(value: str) -> ParsedTicketLine | None:
    m = TICKET_LINE_DUAL_RE.match(value)
    if not m:
        return None

    ticket_type_raw = _clean(m.group("ticket_type"))

    try:
        qty = int(m.group("qty"))
    except Exception:
        qty = None

    unit_uah = _to_decimal(m.group("unit_uah"))
    unit_eur = _to_decimal(m.group("unit_eur"))
    total_uah = _to_decimal(m.group("total_uah"))
    total_eur = _to_decimal(m.group("total_eur"))

    return ParsedTicketLine(
        ticket_type_raw=ticket_type_raw,
        ticket_type_code=_normalize_ticket_type(ticket_type_raw),
        qty=qty,
        # backward-compatible primary values = EUR
        unit_price=unit_eur,
        line_total=total_eur,
        currency="EUR",
        is_dual_currency=True,
        unit_price_uah=unit_uah,
        unit_price_eur=unit_eur,
        line_total_uah=total_uah,
        line_total_eur=total_eur,
    )


def _parse_ticket_line(value: str | None) -> ParsedTicketLine | None:
    value = _clean(value)
    if not value:
        return None

    dual = _parse_ticket_line_dual(value)
    if dual:
        return dual

    single = _parse_ticket_line_single(value)
    if single:
        return single

    return None


def _parse_key_value_lines(raw_text: str) -> dict[str, str]:
    """
    Поддържа multiline value след известен key.
    Това е важно за:

    Ticket types price: дитина(0-4,99) 1 x 60.00 € = 60.00 €
    Дорослий 1 x 100.00 € = 100.00 €
    Total: 160.00 €

    => fields["Ticket types price"] ще съдържа и двата ticket rows.
    """
    fields: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            fields[current_key] = "\n".join(current_lines).strip()
        current_key = None
        current_lines = []

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if ":" in line:
            maybe_key, maybe_value = line.split(":", 1)
            maybe_key = maybe_key.strip()
            maybe_value = maybe_value.strip()

            if maybe_key in KNOWN_FIELD_NAMES:
                flush_current()
                current_key = maybe_key
                current_lines = [maybe_value] if maybe_value else []
                continue

        if current_key is not None:
            current_lines.append(line)

    flush_current()
    return fields


def _sum_ticket_qty(ticket_lines: list[ParsedTicketLine]) -> int:
    return sum((x.qty or 0) for x in ticket_lines)


def _sum_ticket_totals(ticket_lines: list[ParsedTicketLine]) -> tuple[Decimal, Decimal]:
    total_uah = Decimal("0")
    total_eur = Decimal("0")

    for tl in ticket_lines:
        if tl.is_dual_currency:
            total_uah += tl.line_total_uah or Decimal("0")
            total_eur += tl.line_total_eur or Decimal("0")
        else:
            if (tl.currency or "EUR").upper() == "UAH":
                total_uah += tl.line_total or Decimal("0")
            else:
                total_eur += tl.line_total or Decimal("0")

    return total_uah, total_eur


def parse_booking_email(raw_text: str) -> ParsedBooking:
    result = ParsedBooking(raw_text=raw_text)

    fields = _parse_key_value_lines(raw_text)
    result.raw_fields = fields

    uid_raw = fields.get("Unique ID")
    if uid_raw:
        try:
            result.external_id = int(uid_raw.strip())
        except Exception:
            result.errors.append(f"Invalid Unique ID: {uid_raw}")

    result.booking_date = _parse_datetime_ddmmyyyy(fields.get("Booking date"))

    result.time_range_raw = _clean(fields.get("Time"))
    result.time_from, result.time_to = _parse_time_range(result.time_range_raw)

    # BUS = trip-level
    bus_raw = _clean(fields.get("Bus"))
    result.bus_name = bus_raw
    result.bus_route_raw = bus_raw
    result.bus_from, result.bus_to = _split_bus_direction(bus_raw)

    # ROUTE = passenger-level
    result.route_raw = _clean(fields.get("Route"))
    result.route_from, result.route_to = _split_passenger_route(result.route_raw)

    result.first_name = _clean(fields.get("First Name"))
    result.last_name = _clean(fields.get("Last Name"))
    result.email = _clean(fields.get("E-Mail"))
    result.phone = _clean(fields.get("Phone"))
    result.notes = _clean(fields.get("Notes"))

    result.seats_raw = _clean(fields.get("Seats"))
    result.seats = _parse_seats(result.seats_raw)

    result.payment_method = _clean(fields.get("Payment"))

    result.total, result.currency = _parse_total(fields.get("Total"))

    ticket_raw = fields.get("Ticket types price")
    if ticket_raw:
        for raw_ticket_line in ticket_raw.splitlines():
            raw_ticket_line = _clean(raw_ticket_line)
            if not raw_ticket_line:
                continue

            ticket_line = _parse_ticket_line(raw_ticket_line)
            if not ticket_line:
                result.errors.append(f"Could not parse ticket line: {raw_ticket_line}")
                continue

            result.ticket_lines.append(ticket_line)

    if result.external_id is None:
        result.errors.append("Missing external_id")

    if not result.last_name:
        result.errors.append("Missing last_name")

    if not result.bus_route_raw:
        result.warnings.append("Missing bus")

    if not result.route_raw:
        result.warnings.append("Missing route")

    if not result.seats:
        result.warnings.append("No seats parsed")

    if result.ticket_lines:
        total_ticket_qty = _sum_ticket_qty(result.ticket_lines)

        if total_ticket_qty != len(result.seats):
            result.errors.append(
                f"Ticket qty ({total_ticket_qty}) does not match seat count ({len(result.seats)})"
            )

        for tl in result.ticket_lines:
            if tl.is_dual_currency:
                if tl.qty is not None and tl.unit_price_uah is not None and tl.line_total_uah is not None:
                    expected_uah = tl.unit_price_uah * tl.qty
                    if expected_uah != tl.line_total_uah:
                        result.errors.append(
                            f"Ticket arithmetic mismatch UAH: {tl.unit_price_uah} x {tl.qty} != {tl.line_total_uah}"
                        )

                if tl.qty is not None and tl.unit_price_eur is not None and tl.line_total_eur is not None:
                    expected_eur = tl.unit_price_eur * tl.qty
                    if expected_eur != tl.line_total_eur:
                        result.errors.append(
                            f"Ticket arithmetic mismatch EUR: {tl.unit_price_eur} x {tl.qty} != {tl.line_total_eur}"
                        )
            else:
                if tl.qty is not None and tl.unit_price is not None and tl.line_total is not None:
                    expected = tl.unit_price * tl.qty
                    if expected != tl.line_total:
                        result.errors.append(
                            f"Ticket arithmetic mismatch: {tl.unit_price} x {tl.qty} != {tl.line_total}"
                        )

        sum_total_uah, sum_total_eur = _sum_ticket_totals(result.ticket_lines)

        if result.total is not None:
            if result.currency == "EUR":
                if result.total != sum_total_eur:
                    result.errors.append(
                        f"Total mismatch EUR: total={result.total}, sum_ticket_lines={sum_total_eur}"
                    )
            elif result.currency == "UAH":
                if result.total != sum_total_uah:
                    result.errors.append(
                        f"Total mismatch UAH: total={result.total}, sum_ticket_lines={sum_total_uah}"
                    )

    return result


def parsed_booking_to_dict(parsed: ParsedBooking) -> dict[str, Any]:
    return {
        "external_id": parsed.external_id,
        "booking_date": parsed.booking_date.isoformat() if parsed.booking_date else None,
        "time_range_raw": parsed.time_range_raw,
        "time_from": parsed.time_from,
        "time_to": parsed.time_to,
        "bus_name": parsed.bus_name,
        "bus_route_raw": parsed.bus_route_raw,
        "bus_from": parsed.bus_from,
        "bus_to": parsed.bus_to,
        "route_raw": parsed.route_raw,
        "route_from": parsed.route_from,
        "route_to": parsed.route_to,
        "first_name": parsed.first_name,
        "last_name": parsed.last_name,
        "email": parsed.email,
        "phone": parsed.phone,
        "notes": parsed.notes,
        "seats_raw": parsed.seats_raw,
        "seats": parsed.seats,
        "total": str(parsed.total) if parsed.total is not None else None,
        "currency": parsed.currency,
        "payment_method": parsed.payment_method,
        "ticket_lines": [
            {
                "ticket_type_raw": x.ticket_type_raw,
                "ticket_type_code": x.ticket_type_code,
                "qty": x.qty,
                "unit_price": str(x.unit_price) if x.unit_price is not None else None,
                "line_total": str(x.line_total) if x.line_total is not None else None,
                "currency": x.currency,
                "is_dual_currency": x.is_dual_currency,
                "unit_price_uah": str(x.unit_price_uah) if x.unit_price_uah is not None else None,
                "unit_price_eur": str(x.unit_price_eur) if x.unit_price_eur is not None else None,
                "line_total_uah": str(x.line_total_uah) if x.line_total_uah is not None else None,
                "line_total_eur": str(x.line_total_eur) if x.line_total_eur is not None else None,
            }
            for x in parsed.ticket_lines
        ],
        "errors": parsed.errors,
        "warnings": parsed.warnings,
        "raw_fields": parsed.raw_fields,
    }
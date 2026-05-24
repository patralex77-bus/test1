from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Trip, TripPassenger


# ---------------- Amount parsing helpers ----------------
# Строго: сума е само ако има валута (EUR/€ или UAH/₴/грн/гривна)
# + ограничаваме до 6 цифри преди десетичната, за да не хващаме телефони/ID-та.
_AMOUNT_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)")


def _parse_amount_and_currency(raw: str):
    """
    Връща (amount: float|None, currency: str|None)

    ✅ ПАРСВА ако има валута:
      EUR: "EUR", "€", "ЕВРО", "ЄВРО"
      UAH: "UAH", "₴", "ГРН", "ГРИВНА"

    ✅ Ако няма валута, но е чисто число (115 / 115.0 / 115.00 / 115,00),
      -> приема се като EUR, САМО ако <= 2000
    """
    s = (raw or "").strip()
    if not s:
        return None, None

    m_plain = re.fullmatch(r"\s*(\d{1,4})(?:[.,](\d{1,2}))?\s*$", s)
    if m_plain:
        whole = m_plain.group(1)
        frac = m_plain.group(2) or "0"
        frac = frac.ljust(2, "0")[:2]

        try:
            amt = Decimal(f"{whole}.{frac}")
        except InvalidOperation:
            amt = None

        if amt is not None and amt > 0 and amt <= Decimal("2000"):
            return float(amt), "EUR"

    up = s.upper()

    is_eur = ("EUR" in up) or ("€" in s) or ("ЕВРО" in up) or ("ЄВРО" in up)
    is_uah = ("UAH" in up) or ("₴" in s) or ("ГРН" in up) or ("ГРИВНА" in up)

    if not (is_eur or is_uah):
        return None, None

    currency = "EUR" if is_eur else "UAH"

    m = _AMOUNT_RE.search(s)
    if not m:
        return None, currency

    num = m.group(1).replace(",", ".")
    try:
        amt = Decimal(num)
    except InvalidOperation:
        return None, currency

    if amt <= 0:
        return None, currency

    if amt > 1_000_000:
        return None, currency

    return float(amt), currency


def _normalize_currency(cur: str | None) -> str:
    c = (cur or "").strip().upper()
    if c in ("€", "EUR"):
        return "EUR"
    if c in ("₴", "UAH", "ГРН", "ГРН.", "ГРИВНА", "HRN"):
        return "UAH"
    return "EUR"


def _clean_text(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def _clean_int_like(v) -> str:
    s = _clean_text(v)
    if not s:
        return ""
    if re.fullmatch(r"\d+[.,]0+", s):
        return re.split(r"[.,]", s, maxsplit=1)[0]
    return s


def _normalize_phone(v) -> str:
    s = _clean_text(v)
    s = re.sub(r"\D+", "", s)
    if s.startswith("00"):
        s = s[2:]
    return s


def _norm_name(v) -> str:
    return _clean_text(v).lower()


def _norm_match_text(v) -> str:
    return re.sub(r"\s+", " ", (v or "").strip()).lower()


def _normalized_source_uid(v) -> str | None:
    s = str(v or "").strip()
    return s or None


def _same_text(a, b) -> bool:
    return _clean_text(a) == _clean_text(b)


def _same_phone(a, b) -> bool:
    return _normalize_phone(a) == _normalize_phone(b)


def _same_amount(a, b) -> bool:
    if a in (None, "") and b in (None, ""):
        return True
    try:
        if a is None or a == "":
            return False
        if b is None or b == "":
            return False
        return round(float(a), 2) == round(float(b), 2)
    except Exception:
        return False


def _set_if_changed(obj, field: str, new_value, cmp_func=None) -> bool:
    old_value = getattr(obj, field)
    same = cmp_func(old_value, new_value) if cmp_func else old_value == new_value
    if same:
        return False
    setattr(obj, field, new_value)
    return True


def _row_amount_due_and_currency(r: dict) -> tuple[float | None, str]:
    raw = (r.get("voucher_or_amount_raw") or "").strip()

    parsed_amt, parsed_cur = _parse_amount_and_currency(raw)

    amount_due = r.get("amount_due")
    amt_final = None
    if amount_due is not None and amount_due != "":
        try:
            amt_final = float(amount_due)
            if amt_final <= 0:
                amt_final = None
        except Exception:
            amt_final = None

    if amt_final is None:
        amt_final = parsed_amt

    cur_in = r.get("currency")
    if parsed_cur:
        cur_final = parsed_cur
    elif cur_in:
        cur_final = _normalize_currency(cur_in)
    else:
        cur_final = "EUR"

    return amt_final, cur_final


def _row_voucher_code(r: dict, raw: str, parsed_amt: float | None):
    voucher_code = r.get("voucher_code")
    if (voucher_code is None or str(voucher_code).strip() == "") and raw:
        if parsed_amt is None:
            voucher_code = raw
    return voucher_code


def _match_score(p: TripPassenger, r: dict) -> int:
    """
    По-висок score = по-сигурен match.

    ВАЖНО:
    - тук сравняваме Excel/base данните на TripPassenger
    - НЕ гледаме manual_* полетата
    - НЕ гледаме portal/admin seat overlay
    """
    score = 0

    p_pno = _clean_text(p.passenger_no)
    r_pno = _clean_text(r.get("passenger_no"))

    if p_pno and r_pno:
        if p_pno == r_pno:
            return 1000
        return -1000

    p_phone = _normalize_phone(p.phone)
    r_phone = _normalize_phone(r.get("phone"))

    if p_phone and r_phone:
        if p_phone == r_phone:
            score += 300
        else:
            score -= 120
    elif p_phone or r_phone:
        score -= 10

    p_name = _norm_match_text(p.full_name)
    r_name = _norm_match_text(r.get("full_name"))

    if p_name and r_name:
        if p_name == r_name:
            score += 120
        elif p_name in r_name or r_name in p_name:
            score += 60
        else:
            score -= 40
    else:
        score -= 5

    p_seat = _norm_match_text(p.seat_no)
    r_seat = _norm_match_text(r.get("seat_no"))

    if p_seat and r_seat:
        if p_seat == r_seat:
            score += 40
        else:
            score -= 15

    p_from = _norm_match_text(p.from_city)
    r_from = _norm_match_text(r.get("from_city"))
    p_to = _norm_match_text(p.to_city)
    r_to = _norm_match_text(r.get("to_city"))

    if p_from and r_from:
        score += 15 if p_from == r_from else -5
    if p_to and r_to:
        score += 15 if p_to == r_to else -5

    p_raw = _norm_match_text(p.voucher_or_amount_raw)
    r_raw = _norm_match_text(r.get("voucher_or_amount_raw"))
    if p_raw and r_raw and p_raw == r_raw:
        score += 20

    return score


def _apply_import_row_to_passenger(p: TripPassenger, r: dict) -> bool:
    """
    Обновява САМО source/base полетата от Excel.

    Пази:
      - checked_in
      - paid
      - amount
      - booking_id
      - manual_*
      - manual_seat_no (seat chosen in portal/admin)

    ВАЖНО:
    - Excel seat се записва само в base field: seat_no
    - final/portal/admin seat overlay се пази извън този importer
    """
    raw = (r.get("voucher_or_amount_raw") or "").strip()
    parsed_amt, _ = _parse_amount_and_currency(raw)
    amt_final, cur_final = _row_amount_due_and_currency(r)
    voucher_code = _row_voucher_code(r, raw, parsed_amt)
    source_uid = _normalized_source_uid(r.get("source_uid"))

    changed = False
    changed |= _set_if_changed(p, "passenger_no", r.get("passenger_no"), _same_text)
    changed |= _set_if_changed(p, "from_city", r.get("from_city"), _same_text)
    changed |= _set_if_changed(p, "to_city", r.get("to_city"), _same_text)
    changed |= _set_if_changed(p, "full_name", r.get("full_name"), _same_text)
    changed |= _set_if_changed(p, "seat_no", r.get("seat_no"), _same_text)
    changed |= _set_if_changed(p, "phone", r.get("phone"), _same_phone)
    changed |= _set_if_changed(p, "voucher_or_amount_raw", raw, _same_text)
    changed |= _set_if_changed(p, "voucher_code", voucher_code, _same_text)
    changed |= _set_if_changed(p, "amount_due", amt_final, _same_amount)
    changed |= _set_if_changed(p, "currency", cur_final, _same_text)
    changed |= _set_if_changed(p, "source_uid", source_uid, _same_text)

    if changed:
        p.updated_at = datetime.utcnow()

    return changed


# ---------------- Trips ----------------

def create_trip(db: Session, route_from=None, route_to=None, date_time=None, note=None):
    t = Trip(route_from=route_from, route_to=route_to, date_time=date_time, note=note)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def list_trips(db: Session):
    return db.query(Trip).order_by(Trip.created_at.desc()).all()


def get_trip(db: Session, trip_id: int):
    return db.query(Trip).filter(Trip.id == trip_id).first()


def find_trip_by_route_date(db: Session, route_from: str, route_to: str, date_only):
    return (
        db.query(Trip)
        .filter(Trip.route_from == route_from)
        .filter(Trip.route_to == route_to)
        .filter(func.date(Trip.date_time) == date_only)
        .first()
    )


# ---------------- Passengers ----------------

def list_passengers(db: Session, trip_id: int):
    return (
        db.query(TripPassenger)
        .filter(TripPassenger.trip_id == trip_id)
        .all()
    )


def delete_trip(db: Session, trip_id: int) -> bool:
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        return False
    db.delete(trip)
    db.commit()
    return True


def import_passengers(db: Session, trip_id: int, rows: list[dict], replace: bool = True):
    """
    replace=True:
      - НЕ трие сляпо всички редове
      - синхронизира sheet-а към trip-а
      - първо match-ва по source_uid
      - ако няма UID match -> fallback към _match_score
      - пази operational и manual полетата на match-натите редове:
          checked_in, paid, amount, manual_*
      - обновява source/base полетата от Excel:
          passenger_no, from_city, to_city, full_name, seat_no, phone,
          voucher_or_amount_raw, voucher_code, amount_due, currency, source_uid
      - изтрива само редовете, които вече ги няма в sheet-а
      - НЕ прави излишни UPDATE-и, ако редът е същият

    ВАЖНО:
      - importer НЕ пипа manual_seat_no
      - importer НЕ пипа booking_id
      - importer НЕ пипа checked_in / paid / amount
      - importer НЕ може да override-не финално място, избрано през portal/admin
    """
    try:
        if not replace:
            objs = []
            for r in rows:
                raw = (r.get("voucher_or_amount_raw") or "").strip()
                parsed_amt, _ = _parse_amount_and_currency(raw)
                amt_final, cur_final = _row_amount_due_and_currency(r)
                voucher_code = _row_voucher_code(r, raw, parsed_amt)

                objs.append(
                    TripPassenger(
                        trip_id=trip_id,
                        passenger_no=r.get("passenger_no"),
                        from_city=r.get("from_city"),
                        to_city=r.get("to_city"),
                        full_name=r.get("full_name"),
                        seat_no=r.get("seat_no"),
                        phone=r.get("phone"),
                        voucher_or_amount_raw=raw,
                        voucher_code=voucher_code,
                        amount_due=amt_final,
                        currency=cur_final,
                        source_uid=_normalized_source_uid(r.get("source_uid")),
                    )
                )

            if objs:
                db.add_all(objs)
                db.commit()

            return len(objs)

        existing = (
            db.query(TripPassenger)
            .filter(TripPassenger.trip_id == trip_id)
            .all()
        )

        remaining_existing = list(existing)

        existing_by_uid: dict[str, list[TripPassenger]] = {}
        for p in existing:
            uid = _normalized_source_uid(getattr(p, "source_uid", None))
            if uid:
                existing_by_uid.setdefault(uid, []).append(p)

        inserted_count = 0
        updated_count = 0
        deleted_count = 0
        unchanged_count = 0

        for r in rows:
            row_uid = _normalized_source_uid(r.get("source_uid"))

            # 1) UID-first match
            if row_uid:
                bucket = existing_by_uid.get(row_uid) or []

                while bucket and bucket[0] not in remaining_existing:
                    bucket.pop(0)

                if bucket:
                    best = bucket.pop(0)
                    changed = _apply_import_row_to_passenger(best, r)

                    if changed:
                        updated_count += 1
                    else:
                        unchanged_count += 1

                    if best in remaining_existing:
                        remaining_existing.remove(best)
                    continue

            # 2) fallback match by score
            best = None
            best_score = 0

            for p in remaining_existing:
                score = _match_score(p, r)
                if score > best_score:
                    best_score = score
                    best = p

            if best is not None and best_score >= 120:
                changed = _apply_import_row_to_passenger(best, r)

                if changed:
                    updated_count += 1
                else:
                    unchanged_count += 1

                remaining_existing.remove(best)
                continue

            # 3) insert new
            raw = (r.get("voucher_or_amount_raw") or "").strip()
            parsed_amt, _ = _parse_amount_and_currency(raw)
            amt_final, cur_final = _row_amount_due_and_currency(r)
            voucher_code = _row_voucher_code(r, raw, parsed_amt)

            obj = TripPassenger(
                trip_id=trip_id,
                passenger_no=r.get("passenger_no"),
                from_city=r.get("from_city"),
                to_city=r.get("to_city"),
                full_name=r.get("full_name"),
                seat_no=r.get("seat_no"),
                phone=r.get("phone"),
                voucher_or_amount_raw=raw,
                voucher_code=voucher_code,
                amount_due=amt_final,
                currency=cur_final,
                source_uid=row_uid,
            )
            db.add(obj)
            inserted_count += 1

        # 4) delete stale rows
        for stale in remaining_existing:
            db.delete(stale)
            deleted_count += 1

        if inserted_count or updated_count or deleted_count:
            db.commit()

        return len(rows)

    except Exception:
        db.rollback()
        raise


def patch_passenger(db: Session, passenger_id: int, checked_in=None, paid=None, amount=None, currency=None, oebb=None):
    """
    Operational patch:
    - за driver/admin действия
    - НЕ пипа source/base fields
    - НЕ пипа manual_* fields
    """
    p = db.query(TripPassenger).filter(TripPassenger.id == passenger_id).first()
    if not p:
        return None

    changed = False

    if checked_in is not None:
        next_val = bool(checked_in)
        if p.checked_in != next_val:
            p.checked_in = next_val
            changed = True

    if paid is not None:
        next_val = bool(paid)
        if p.paid != next_val:
            p.paid = next_val
            changed = True

    if amount is not None:
        if amount == "" or amount is None:
            next_amount = None
        else:
            try:
                next_amount = float(amount)
            except Exception:
                next_amount = None

        if p.amount != next_amount:
            p.amount = next_amount
            changed = True

    if currency is not None:
        next_currency = _normalize_currency(currency)
        if (p.currency or "EUR") != next_currency:
            p.currency = next_currency
            changed = True

    if oebb is not None:
        next_oebb = bool(oebb)
        if bool(p.oebb) != next_oebb:
            p.oebb = next_oebb
            changed = True

    if changed:
        p.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(p)

    return p
from datetime import datetime

from sqlalchemy import Column, Integer, BigInteger, Boolean, DateTime, ForeignKey, Numeric, String, Text, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    date_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    route_from: Mapped[str | None] = mapped_column(String(120), nullable=True)
    route_to: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    passengers: Mapped[list["TripPassenger"]] = relationship(
        "TripPassenger",
        back_populates="trip",
        cascade="all, delete-orphan",
    )

    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="trip",
    )


class TripPassenger(Base):
    __tablename__ = "trip_passengers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    trip: Mapped["Trip"] = relationship("Trip", back_populates="passengers")
    booking: Mapped["Booking | None"] = relationship("Booking", back_populates="trip_passengers")

    passenger_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    to_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seat_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    seat_locked_by_admin = Column(Boolean, nullable=False, default=False)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    source_uid: Mapped[str | None] = mapped_column(Text, nullable=True)

    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    oebb: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    voucher_or_amount_raw: Mapped[str | None] = mapped_column(String(200), nullable=True)
    voucher_code: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_due: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=True)

    checked_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    amount: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

    manual_passenger_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manual_from_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manual_to_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manual_full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    manual_seat_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    manual_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manual_voucher_raw: Mapped[str | None] = mapped_column(String(200), nullable=True)
    manual_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    manual_updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)


class BadClient(Base):
    __tablename__ = "bad_clients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    phone_norm: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    name_norm: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    bad_count: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class IncomingEmail(Base):
    __tablename__ = "incoming_emails"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    sender: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    fetch_status: Mapped[str] = mapped_column(String(50), default="new", nullable=False)
    parse_status: Mapped[str] = mapped_column(String(50), default="new", nullable=False)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="incoming_email",
    )


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)

    incoming_email_id: Mapped[int | None] = mapped_column(
        ForeignKey("incoming_emails.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trip_id: Mapped[int | None] = mapped_column(
        ForeignKey("trips.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    booking_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    time_range_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    time_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    time_to: Mapped[str | None] = mapped_column(String(20), nullable=True)

    bus_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    route_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    route_from: Mapped[str | None] = mapped_column(String(120), nullable=True)
    route_to: Mapped[str | None] = mapped_column(String(120), nullable=True)

    bus_route_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    bus_from: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bus_to: Mapped[str | None] = mapped_column(String(120), nullable=True)

    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    seats_raw: Mapped[str | None] = mapped_column(String(200), nullable=True)
    total: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)

    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(50), default="unpaid", nullable=False)
    booking_status: Mapped[str] = mapped_column(String(50), default="new", nullable=False)

    source: Mapped[str] = mapped_column(String(50), default="email", nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    portal_access_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    checkin_token: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    incoming_email: Mapped["IncomingEmail | None"] = relationship(
        "IncomingEmail",
        back_populates="bookings",
    )
    trip: Mapped["Trip | None"] = relationship(
        "Trip",
        back_populates="bookings",
    )

    seats: Mapped[list["BookingSeat"]] = relationship(
        "BookingSeat",
        back_populates="booking",
        cascade="all, delete-orphan",
    )
    ticket_lines: Mapped[list["BookingTicketLine"]] = relationship(
        "BookingTicketLine",
        back_populates="booking",
        cascade="all, delete-orphan",
    )
    trip_passengers: Mapped[list["TripPassenger"]] = relationship(
        "TripPassenger",
        back_populates="booking",
    )


class BookingSeat(Base):
    __tablename__ = "booking_seats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    trip_id: Mapped[int | None] = mapped_column(
        ForeignKey("trips.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    seat_no: Mapped[str | None] = mapped_column(String(32), nullable=True)

    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    selection_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    booking: Mapped["Booking"] = relationship("Booking", back_populates="seats")
    trip: Mapped["Trip | None"] = relationship("Trip")

class BookingTicketLine(Base):
    __tablename__ = "booking_ticket_lines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    ticket_type_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ticket_type_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    qty: Mapped[int] = mapped_column(nullable=False, default=1)

    # backward-compatible primary fields
    unit_price: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=True)
    line_total: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)

    # new dual-currency support
    is_dual_currency: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    unit_price_uah: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    unit_price_eur: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)

    line_total_uah: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    line_total_eur: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    booking: Mapped["Booking"] = relationship("Booking", back_populates="ticket_lines")

class PaymentProof(Base):
    __tablename__ = "payment_proofs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    review_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    booking: Mapped["Booking"] = relationship("Booking")


class BookingCancellation(Base):
    __tablename__ = "booking_cancellations"

    id = Column(Integer, primary_key=True, index=True)

    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id = Column(BigInteger, nullable=True, index=True)

    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    travel_at = Column(DateTime, nullable=True)

    hours_before_departure = Column(Numeric(10, 2), nullable=True)
    refund_percent = Column(Integer, nullable=False, default=0)
    refund_amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(16), nullable=True)

    reason = Column(Text, nullable=True)

    admin_status = Column(String(32), nullable=False, default="pending")  # pending / approved / rejected / processed
    admin_note = Column(Text, nullable=True)

    passenger_email_sent = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    booking = relationship("Booking")
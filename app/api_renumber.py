from sqlalchemy import String, DateTime, Boolean, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base

class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    date_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    route_from: Mapped[str | None] = mapped_column(String(120), nullable=True)
    route_to: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    passengers: Mapped[list["TripPassenger"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )

class TripPassenger(Base):
    __tablename__ = "trip_passengers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    trip: Mapped["Trip"] = relationship(back_populates="passengers")

    passenger_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    to_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seat_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    voucher_or_amount_raw: Mapped[str | None] = mapped_column(String(200), nullable=True)
    voucher_code: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_due: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    checked_in: Mapped[bool] = mapped_column(Boolean, default=False)
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

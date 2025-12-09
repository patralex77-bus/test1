
from . import db
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class PayrollSettings(db.Model):
    __tablename__ = "payroll_settings"
    id = db.Column(db.Integer, primary_key=True, default=1)
    daily_fixed = db.Column(db.Float, nullable=False, default=80.0)        # Дневна ставка FIX
    hourly_contract = db.Column(db.Float, nullable=False, default=10.0)    # Часова ставка по договор
    hourly_custom = db.Column(db.Float, nullable=False, default=12.0)      # Часова ставка по договореност
    min_hours = db.Column(db.Float, nullable=False, default=0.0)           # Мин. заетост/часове
    max_hours = db.Column(db.Float, nullable=False, default=13.0)          # Макс. заетост/часове (на ден)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get_or_create():
        obj = PayrollSettings.query.get(1)
        if not obj:
            obj = PayrollSettings(id=1)
            db.session.add(obj)
            db.session.commit()
        return obj

    def as_dict(self):
        return {
            "daily_fixed": self.daily_fixed,
            "hourly_rate": self.hourly_contract,   # ← използвай това име, ако вече го очакваш в front-end
            "hourly_contract": self.hourly_contract,
            "hourly_custom": self.hourly_custom,
            "min_hours": self.min_hours,
            "max_hours": self.max_hours,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class Bus(db.Model, TimestampMixin):
    __tablename__ = "buses"
    id = db.Column(db.Integer, primary_key=True)
    reg_no = db.Column(db.String(32), unique=True, nullable=True)
    brand = db.Column(db.String(80), nullable=True)
    bus_class = db.Column(db.String(32), nullable=True)
    seats = db.Column(db.Integer, nullable=True)
    odometer_start = db.Column(db.Integer, nullable=True)
    tech_inspection_date = db.Column(db.Date, nullable=True)

    fixed_costs = db.relationship("BusFixedCost", backref="bus", cascade="all, delete-orphan", lazy=True)
    repairs = db.relationship("BusRepair", backref="bus", cascade="all, delete-orphan", lazy=True)
    mileages = db.relationship("BusMileage", backref="bus", cascade="all, delete-orphan", lazy=True)
    fuels = db.relationship("BusFuel", backref="bus", cascade="all, delete-orphan", lazy=True)

class BusFixedCost(db.Model, TimestampMixin):
    __tablename__ = "bus_fixed_costs"
    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey("buses.id"), nullable=False)
    category = db.Column(db.String(16), nullable=False)
    periodicity = db.Column(db.String(16), nullable=False, default="MONTHLY")  # MONTHLY | YEARLY
    title = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Numeric(12,2), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.String(255), nullable=True)

class BusRepair(db.Model, TimestampMixin):
    __tablename__ = "bus_repairs"
    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey("buses.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    amount = db.Column(db.Numeric(12,2), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    vendor = db.Column(db.String(120), nullable=True)

class BusMileage(db.Model, TimestampMixin):
    __tablename__ = "bus_mileages"
    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey("buses.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    km = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(255), nullable=True)

class BusFuel(db.Model, TimestampMixin):
    __tablename__ = "bus_fuels"
    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey("buses.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    liters = db.Column(db.Numeric(10,3), nullable=False)
    price_per_liter = db.Column(db.Numeric(10,3), nullable=False)
    amount = db.Column(db.Numeric(12,2), nullable=False)
    odometer = db.Column(db.Integer, nullable=True)
    station = db.Column(db.String(120), nullable=True)
    payment_method = db.Column(db.String(40), nullable=True)
    notes = db.Column(db.String(255), nullable=True)


# ---------------------- Drivers / Orders ----------------------
class Driver(db.Model, TimestampMixin):
    __tablename__ = "drivers"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    license_valid_to = db.Column(db.Date, nullable=True)
    card_valid_to = db.Column(db.Date, nullable=True)        # квалификационна карта
    medical_valid_to = db.Column(db.Date, nullable=True)     # мед. преглед
    notes = db.Column(db.String(500), nullable=True)

    orders = db.relationship("Order", backref="driver", cascade="all, delete-orphan", lazy=True)

class Order(db.Model, TimestampMixin):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    client = db.Column(db.String(120), nullable=False)
    route = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    bus_id = db.Column(db.Integer, db.ForeignKey("buses.id"), nullable=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=False)

    day_logs = db.relationship("OrderDayLog", backref="order", cascade="all, delete-orphan", lazy=True)
    access_tokens = db.relationship("DriverAccessToken", backref="order", cascade="all, delete-orphan", lazy=True)

class OrderDayLog(db.Model, TimestampMixin):
    __tablename__ = "order_day_logs"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_km = db.Column(db.Integer, nullable=True)
    end_km = db.Column(db.Integer, nullable=True)
    fuel_liters = db.Column(db.Numeric(10,3), nullable=True)
    fuel_amount = db.Column(db.Numeric(12,2), nullable=True)
    fees_amount = db.Column(db.Numeric(12,2), nullable=True)   # пътни/такси
    work_hours = db.Column(db.Numeric(6,2), nullable=True)     # работни часове
    incidents = db.Column(db.String(500), nullable=True)
    notes = db.Column(db.String(500), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('order_id', 'date', name='uix_order_day'),
    )

class DriverAccessToken(db.Model, TimestampMixin):
    __tablename__ = "driver_access_tokens"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    String,
    Numeric,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class Terminal(Base):
    __tablename__ = "terminals"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    current_session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sessions: Mapped[List["Session"]] = relationship(back_populates="terminal")
    reservations: Mapped[List["Reservation"]] = relationship(back_populates="terminal")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    card_uid: Mapped[str] = mapped_column(String(50), nullable=False)
    requested_services: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    assigned_terminal_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("terminals.id"), nullable=True
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    terminal: Mapped[Optional["Terminal"]] = relationship(back_populates="reservations")
    session: Mapped[Optional["Session"]] = relationship(
        back_populates="reservation",
        foreign_keys="[Session.reservation_id]",
        uselist=False,
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    terminal_id: Mapped[str] = mapped_column(ForeignKey("terminals.id"), nullable=False)
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reservations.id"), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="STARTED")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    terminal: Mapped["Terminal"] = relationship(back_populates="sessions")
    reservation: Mapped["Reservation"] = relationship(
        back_populates="session",
        foreign_keys=[reservation_id],
    )
    readings: Mapped[List["MeterReading"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    invoice: Mapped[Optional["Invoice"]] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class MeterReading(Base):
    __tablename__ = "meter_readings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    meter_type: Mapped[str] = mapped_column(String(15), nullable=False)
    cumulative_value: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["Session"] = relationship(back_populates="readings")


class TariffBracket(Base):
    __tablename__ = "tariff_brackets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    meter_type: Mapped[str] = mapped_column(String(15), nullable=False)
    tier_order: Mapped[int] = mapped_column(nullable=False)
    lower_bound: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    upper_bound: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)
    rate_per_unit: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    fixed_fee: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), unique=True, nullable=False
    )
    total_amount: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["Session"] = relationship(back_populates="invoice")
    lines: Mapped[List["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    meter_type: Mapped[str] = mapped_column(String(15), nullable=False)
    consumption: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    fixed_fee: Mapped[float] = mapped_column(Numeric(10, 3), default=0.0)
    usage_amount: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    tier_breakdown: Mapped[list] = mapped_column(JSON, default=list)

    invoice: Mapped["Invoice"] = relationship(back_populates="lines")


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

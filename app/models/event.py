from __future__ import annotations

from datetime import date as date_type, datetime, time as time_type
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


_Trimmed = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


REQUIRED_FIELDS: tuple[str, ...] = (
    "name",
    "date",
    "time",
    "seat_types",
    "purchase_start",
    "purchase_end",
    "ticket_limit",
    "venue_name",
    "venue_address",
    "capacity",
    "organizer_name",
    "organizer_email",
    "category",
    "language",
)


class EventDraft(BaseModel):
    """Partial event being built during conversation. All fields Optional."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[_Trimmed] = Field(default=None, description="Event name, e.g., 'Kyoto Jazz Night'")
    date: Optional[date_type] = Field(default=None, description="Event date in YYYY-MM-DD")
    time: Optional[time_type] = Field(default=None, description="Event time in HH:MM (24-hour)")
    description: Optional[_Trimmed] = Field(default=None, description="Free-text event description")
    seat_types: Optional[dict[str, int]] = Field(
        default=None,
        description='Map of seat label to price, e.g., {"VIP": 10000, "Regular": 5000}',
    )
    purchase_start: Optional[date_type] = Field(default=None, description="Ticket purchase start date")
    purchase_end: Optional[date_type] = Field(default=None, description="Ticket purchase end date")
    ticket_limit: Optional[int] = Field(default=None, ge=1, description="Max tickets per person")
    venue_name: Optional[_Trimmed] = Field(default=None)
    venue_address: Optional[_Trimmed] = Field(default=None)
    capacity: Optional[int] = Field(default=None, ge=1)
    organizer_name: Optional[_Trimmed] = Field(default=None)
    organizer_email: Optional[EmailStr] = Field(default=None)
    category: Optional[_Trimmed] = Field(default=None, description="e.g., Concert, Conference")
    language: Optional[_Trimmed] = Field(default=None, description="e.g., Japanese, English")
    is_recurring: Optional[bool] = Field(default=None)
    recurrence_frequency: Optional[str] = Field(
        default=None, description="e.g., weekly, monthly; required when is_recurring=True"
    )
    is_online: Optional[bool] = Field(default=None)

    def missing_required(self) -> list[str]:
        return [f for f in REQUIRED_FIELDS if getattr(self, f) in (None, {}, "")]

    def is_complete(self) -> bool:
        return not self.missing_required()


class EventCreate(BaseModel):
    """Strict event model used at save time. All required fields required."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    date: date_type
    time: time_type
    description: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = None
    seat_types: dict[str, int] = Field(min_length=1)
    purchase_start: date_type
    purchase_end: date_type
    ticket_limit: int = Field(ge=1)
    venue_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    venue_address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    capacity: int = Field(ge=1)
    organizer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    organizer_email: EmailStr
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    language: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    is_recurring: bool = False
    recurrence_frequency: Optional[str] = None
    is_online: bool = False

    @model_validator(mode="after")
    def _check_seat_types_prices(self) -> "EventCreate":
        for label, price in self.seat_types.items():
            if not isinstance(price, int) or price < 0:
                raise ValueError(f"seat_types[{label!r}] must be a non-negative integer")
        return self

    @model_validator(mode="after")
    def _check_purchase_window(self) -> "EventCreate":
        if self.purchase_end < self.purchase_start:
            raise ValueError("purchase_end must be on or after purchase_start")
        if self.purchase_end > self.date:
            raise ValueError("purchase_end must be on or before the event date")
        return self

    @model_validator(mode="after")
    def _check_recurrence(self) -> "EventCreate":
        if self.is_recurring and not self.recurrence_frequency:
            raise ValueError("recurrence_frequency is required when is_recurring is True")
        return self

    @model_validator(mode="after")
    def _check_future_event(self) -> "EventCreate":
        if datetime.combine(self.date, self.time) < datetime.now():
            raise ValueError("event date/time must not be in the past")
        return self

    @model_validator(mode="after")
    def _check_ticket_limit_within_capacity(self) -> "EventCreate":
        if self.ticket_limit > self.capacity:
            raise ValueError("ticket_limit must be <= capacity")
        return self


class EventRead(EventCreate):
    """Event with persisted identifiers — what comes back from the repository."""

    id: int
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _check_future_event(self) -> "EventRead":  # type: ignore[override]
        # Historical rows are allowed to be in the past; only creation enforces this.
        return self


class Base(DeclarativeBase):
    pass


class EventDB(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("name", "date", name="events_name_date_unique"),
        CheckConstraint("purchase_end >= purchase_start", name="events_purchase_window"),
        CheckConstraint("purchase_end <= date", name="events_purchase_before_event"),
        CheckConstraint("ticket_limit > 0", name="events_ticket_limit_positive"),
        CheckConstraint("capacity > 0", name="events_capacity_positive"),
        CheckConstraint("ticket_limit <= capacity", name="events_ticket_limit_within_capacity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    time: Mapped[time_type] = mapped_column(Time, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seat_types: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    purchase_start: Mapped[date_type] = mapped_column(Date, nullable=False)
    purchase_end: Mapped[date_type] = mapped_column(Date, nullable=False)
    ticket_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    venue_name: Mapped[str] = mapped_column(String(255), nullable=False)
    venue_address: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    organizer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    organizer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recurrence_frequency: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def to_read(self) -> EventRead:
        return EventRead(
            id=self.id,
            name=self.name,
            date=self.date,
            time=self.time,
            description=self.description,
            seat_types=dict(self.seat_types) if self.seat_types else {},
            purchase_start=self.purchase_start,
            purchase_end=self.purchase_end,
            ticket_limit=self.ticket_limit,
            venue_name=self.venue_name,
            venue_address=self.venue_address,
            capacity=self.capacity,
            organizer_name=self.organizer_name,
            organizer_email=self.organizer_email,
            category=self.category,
            language=self.language,
            is_recurring=self.is_recurring,
            recurrence_frequency=self.recurrence_frequency,
            is_online=self.is_online,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

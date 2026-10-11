"""Database base models and custom types."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    """Return current timestamp in UTC with timezone awareness."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """SQLAlchemy TypeDecorator guaranteeing timezone-aware UTC datetimes.

    SQLite stores datetimes as naive strings or numbers without timezone offsets.
    This decorator:
    1. Normalizes outgoing datetimes to UTC (treating naive datetimes as UTC).
    2. Ensures retrieved datetimes always have tzinfo=timezone.utc.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is not None:
            if not isinstance(value, datetime):
                raise TypeError(f"Expected datetime instance, got {type(value).__name__}")
            if value.tzinfo is None:
                # Treat naive datetime at application boundary as UTC
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)

            # SQLite standard storage driver works best with naive UTC timestamp representation
            if dialect.name == "sqlite":
                return value.replace(tzinfo=None)
            return value
        return None

    def process_result_value(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is not None:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return None


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass

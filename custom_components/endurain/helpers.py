"""Helpers for interpreting Endurain payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import ACTIVITY_TYPES


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an Endurain timestamp into an aware datetime.

    Endurain serializes activity times without a UTC offset, in the
    server's local time zone. Home Assistant's time zone is the best
    available stand-in for it.
    """
    if not isinstance(value, str) or not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return parsed


def activity_type_name(type_id: Any) -> str | None:
    """Return the human readable name of an activity type id."""
    if type_id is None:
        return None
    return ACTIVITY_TYPES.get(type_id, f"Type {type_id}")


def activity_url(base_url: str, activity: dict[str, Any]) -> str:
    """Return the web UI URL of an activity."""
    return f"{base_url}/activity/{activity['id']}"

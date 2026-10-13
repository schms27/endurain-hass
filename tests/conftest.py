"""Fixtures for Endurain integration tests."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.endurain.const import (
    AUTH_TYPE_API_KEY,
    AUTH_TYPE_PASSWORD,
    CONF_AUTH_TYPE,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

URL = "https://endurain.test"
API = f"{URL}/api/v1"
USER_ID = 7
UNIQUE_ID = f"{URL}#{USER_ID}"

PROFILE: dict[str, Any] = {
    "id": USER_ID,
    "name": "Jane Runner",
    "username": "jane",
    "email": "jane@example.com",
    "units": "metric",
    "first_day_of_week": 1,
}


def summary(distance: float, duration: float, count: int) -> dict[str, Any]:
    """Build a summary payload."""
    return {
        "total_distance": distance,
        "total_duration": duration,
        "total_elevation_gain": 120.0,
        "activity_count": count,
        "total_calories": 900,
        "breakdown": [],
        "type_breakdown": [],
    }


ACTIVITY: dict[str, Any] = {
    "id": 42,
    "user_id": USER_ID,
    "name": "Morning run",
    "activity_type": 1,
    "start_time": "2026-10-12T07:30:00",
    "distance": 10234,
    "total_timer_time": 3120.0,
    "elevation_gain": 85,
    "calories": 650,
    "average_hr": 148,
}


def mock_data_endpoints(
    aioclient_mock: AiohttpClientMocker,
    *,
    activity: dict[str, Any] | None = ACTIVITY,
    forbidden: tuple[str, ...] = (),
) -> None:
    """Register every data endpoint the coordinator reads.

    ``forbidden`` lists API paths (relative to /api/v1) that answer 403.
    """

    def register(path: str, payload: Any) -> None:
        if path in forbidden:
            aioclient_mock.get(f"{API}{path}", status=403, json={"detail": "Missing permissions"})
        else:
            aioclient_mock.get(f"{API}{path}", json=payload)

    register("/profile", PROFILE)
    register("/activities_summaries/week", summary(25000, 9000, 3))
    register("/activities_summaries/month", summary(110000, 40000, 12))
    register("/activities_summaries/year", summary(950000, 350000, 101))
    register("/activities_summaries/lifetime", summary(4200000, 1500000, 480))
    register(
        f"/activities/user/{USER_ID}/page_number/1/num_records/1",
        [activity] if activity else [],
    )
    register(
        "/health/steps",
        {"total": 1, "num_records": 1, "page_number": 1, "records": [{"date": "2026-10-12", "steps": 11234}]},
    )
    register(
        "/health/weight",
        {
            "total": 1,
            "num_records": 1,
            "page_number": 1,
            "records": [{"date": "2026-10-12", "weight": 71.4, "bmi": 22.1, "body_fat": 14.2}],
        },
    )
    register(
        "/health/sleep",
        {
            "total": 1,
            "num_records": 1,
            "page_number": 1,
            "records": [
                {
                    "date": "2026-10-12",
                    "total_sleep_seconds": 27000,
                    "sleep_score_overall": 83,
                    "resting_heart_rate": 48,
                }
            ],
        },
    )


def token_payload(refresh_token: str = "refresh-2", access_token: str = "access-1") -> dict[str, Any]:
    """Build a mobile token response."""
    return {
        "session_id": "sid",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 900,
        "refresh_token_expires_in": 604800,
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the custom integration in every test."""


@pytest.fixture
def api_key_entry() -> MockConfigEntry:
    """Config entry using an API key."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Jane Runner",
        unique_id=UNIQUE_ID,
        data={
            CONF_URL: URL,
            CONF_VERIFY_SSL: True,
            CONF_AUTH_TYPE: AUTH_TYPE_API_KEY,
            CONF_API_KEY: "endurain_secret",
        },
    )


@pytest.fixture
def password_entry() -> MockConfigEntry:
    """Config entry using a persisted refresh token."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Jane Runner",
        unique_id=UNIQUE_ID,
        data={
            CONF_URL: URL,
            CONF_VERIFY_SSL: True,
            CONF_AUTH_TYPE: AUTH_TYPE_PASSWORD,
            CONF_USERNAME: "jane",
            CONF_REFRESH_TOKEN: "refresh-1",
        },
    )

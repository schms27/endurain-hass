"""Sensor platform for the Endurain integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfMass,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import SUMMARY_PERIODS
from .coordinator import EndurainConfigEntry, EndurainCoordinator, EndurainData
from .entity import EndurainEntity
from .helpers import activity_type_name, activity_url, parse_timestamp

PARALLEL_UPDATES = 0

type Payload = dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class EndurainSensorEntityDescription(SensorEntityDescription):
    """Describes an Endurain sensor.

    ``section`` names the coordinator section the value comes from (see
    ``EndurainData.forbidden``); ``value_fn`` receives that section's payload,
    which is never None when called.
    """

    section: str
    value_fn: Callable[[Payload], StateType | datetime]
    attributes_fn: Callable[[Payload, str], dict[str, Any]] | None = None


def _section_payload(data: EndurainData, section: str) -> Payload | None:
    kind, _, name = section.partition(":")
    if kind == "summary":
        return data.summaries.get(name)
    if kind == "health":
        return data.health.get(name)
    return data.latest_activity


def _summary_descriptions(period: str) -> tuple[EndurainSensorEntityDescription, ...]:
    section = f"summary:{period}"
    return (
        EndurainSensorEntityDescription(
            key=f"{period}_distance",
            translation_key=f"{period}_distance",
            section=section,
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.TOTAL,
            native_unit_of_measurement=UnitOfLength.METERS,
            suggested_unit_of_measurement=UnitOfLength.KILOMETERS,
            suggested_display_precision=1,
            value_fn=lambda p: p.get("total_distance"),
        ),
        EndurainSensorEntityDescription(
            key=f"{period}_duration",
            translation_key=f"{period}_duration",
            section=section,
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            suggested_unit_of_measurement=UnitOfTime.HOURS,
            suggested_display_precision=1,
            value_fn=lambda p: p.get("total_duration"),
        ),
        EndurainSensorEntityDescription(
            key=f"{period}_activity_count",
            translation_key=f"{period}_activity_count",
            section=section,
            state_class=SensorStateClass.TOTAL,
            value_fn=lambda p: p.get("activity_count"),
        ),
        EndurainSensorEntityDescription(
            key=f"{period}_elevation_gain",
            translation_key=f"{period}_elevation_gain",
            section=section,
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.TOTAL,
            native_unit_of_measurement=UnitOfLength.METERS,
            suggested_display_precision=0,
            entity_registry_enabled_default=False,
            value_fn=lambda p: p.get("total_elevation_gain"),
        ),
        EndurainSensorEntityDescription(
            key=f"{period}_calories",
            translation_key=f"{period}_calories",
            section=section,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL,
            native_unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
            suggested_display_precision=0,
            entity_registry_enabled_default=False,
            value_fn=lambda p: p.get("total_calories"),
        ),
    )


def _latest_activity_attributes(activity: Payload, base_url: str) -> dict[str, Any]:
    return {
        "activity_id": activity.get("id"),
        "activity_type": activity_type_name(activity.get("activity_type")),
        "start_time": parse_timestamp(activity.get("start_time")),
        "distance_m": activity.get("distance"),
        "duration_s": activity.get("total_timer_time"),
        "elevation_gain_m": activity.get("elevation_gain"),
        "calories": activity.get("calories"),
        "average_hr": activity.get("average_hr"),
        "url": activity_url(base_url, activity),
    }


SENSORS: tuple[EndurainSensorEntityDescription, ...] = (
    *(description for period in SUMMARY_PERIODS for description in _summary_descriptions(period)),
    EndurainSensorEntityDescription(
        key="latest_activity",
        translation_key="latest_activity",
        section="latest_activity",
        value_fn=lambda a: a.get("name"),
        attributes_fn=_latest_activity_attributes,
    ),
    EndurainSensorEntityDescription(
        key="latest_activity_start",
        translation_key="latest_activity_start",
        section="latest_activity",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda a: parse_timestamp(a.get("start_time")),
    ),
    EndurainSensorEntityDescription(
        key="latest_activity_distance",
        translation_key="latest_activity_distance",
        section="latest_activity",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        suggested_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=2,
        value_fn=lambda a: a.get("distance"),
    ),
    EndurainSensorEntityDescription(
        key="latest_activity_duration",
        translation_key="latest_activity_duration",
        section="latest_activity",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda a: a.get("total_timer_time"),
    ),
    EndurainSensorEntityDescription(
        key="steps",
        translation_key="steps",
        section="health:steps",
        native_unit_of_measurement="steps",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: r.get("steps"),
        attributes_fn=lambda r, _: {"date": r.get("date")},
    ),
    EndurainSensorEntityDescription(
        key="weight",
        translation_key="weight",
        section="health:weight",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1,
        value_fn=lambda r: r.get("weight"),
        attributes_fn=lambda r, _: {"date": r.get("date")},
    ),
    EndurainSensorEntityDescription(
        key="bmi",
        translation_key="bmi",
        section="health:weight",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda r: r.get("bmi"),
    ),
    EndurainSensorEntityDescription(
        key="body_fat",
        translation_key="body_fat",
        section="health:weight",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda r: r.get("body_fat"),
    ),
    EndurainSensorEntityDescription(
        key="sleep_duration",
        translation_key="sleep_duration",
        section="health:sleep",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        value_fn=lambda r: r.get("total_sleep_seconds"),
        attributes_fn=lambda r, _: {"date": r.get("date")},
    ),
    EndurainSensorEntityDescription(
        key="sleep_score",
        translation_key="sleep_score",
        section="health:sleep",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: r.get("sleep_score_overall"),
    ),
    EndurainSensorEntityDescription(
        key="resting_heart_rate",
        translation_key="resting_heart_rate",
        section="health:sleep",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="bpm",
        value_fn=lambda r: r.get("resting_heart_rate"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EndurainConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Endurain sensors, skipping sections the credential cannot read."""
    coordinator = entry.runtime_data
    async_add_entities(
        EndurainSensor(coordinator, description)
        for description in SENSORS
        if description.section not in coordinator.data.forbidden
    )


class EndurainSensor(EndurainEntity, SensorEntity):
    """A sensor reading one value from the coordinator data."""

    entity_description: EndurainSensorEntityDescription

    def __init__(
        self,
        coordinator: EndurainCoordinator,
        description: EndurainSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def _payload(self) -> Payload | None:
        return _section_payload(self.coordinator.data, self.entity_description.section)

    @property
    def available(self) -> bool:
        """Return False if the section became unreadable since setup."""
        return super().available and self.entity_description.section not in self.coordinator.data.forbidden

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value, or None when there is no data yet."""
        payload = self._payload
        if payload is None:
            return None
        return self.entity_description.value_fn(payload)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes for the sensor."""
        payload = self._payload
        if payload is None or self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(payload, self.coordinator.client.base_url)

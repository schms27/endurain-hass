"""Event platform for the Endurain integration."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EndurainConfigEntry, EndurainCoordinator
from .entity import EndurainEntity
from .helpers import activity_type_name, activity_url

PARALLEL_UPDATES = 0

EVENT_NEW_ACTIVITY = "new_activity"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EndurainConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the new-activity event entity."""
    coordinator = entry.runtime_data
    if "latest_activity" not in coordinator.data.forbidden:
        async_add_entities([EndurainActivityEvent(coordinator)])


class EndurainActivityEvent(EndurainEntity, EventEntity):
    """Fires when a newer activity than the last seen one appears."""

    _attr_translation_key = "activity"
    _attr_event_types = [EVENT_NEW_ACTIVITY]

    def __init__(self, coordinator: EndurainCoordinator) -> None:
        """Initialize the event entity with the activity known at startup."""
        super().__init__(coordinator, "activity_event")
        self._last_activity_id = self._current_activity_id()

    def _current_activity_id(self) -> int | None:
        activity = self.coordinator.data.latest_activity
        return activity["id"] if activity else None

    @callback
    def _handle_coordinator_update(self) -> None:
        activity = self.coordinator.data.latest_activity
        activity_id = self._current_activity_id()
        # Activity ids are increasing, so a lower id means the latest
        # activity was deleted rather than a new one uploaded.
        if (
            activity is not None
            and activity_id is not None
            and (self._last_activity_id is None or activity_id > self._last_activity_id)
        ):
            self._trigger_event(
                EVENT_NEW_ACTIVITY,
                {
                    "activity_id": activity_id,
                    "name": activity.get("name"),
                    "activity_type": activity_type_name(activity.get("activity_type")),
                    "start_time": activity.get("start_time"),
                    "distance_m": activity.get("distance"),
                    "duration_s": activity.get("total_timer_time"),
                    "url": activity_url(self.coordinator.client.base_url, activity),
                },
            )
        self._last_activity_id = activity_id
        super()._handle_coordinator_update()

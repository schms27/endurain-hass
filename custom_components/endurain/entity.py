"""Base entity for the Endurain integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EndurainCoordinator


class EndurainEntity(CoordinatorEntity[EndurainCoordinator]):
    """An entity belonging to one Endurain account."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EndurainCoordinator, key: str) -> None:
        """Initialize the entity and attach it to the account's service device."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        assert entry.unique_id is not None
        profile = coordinator.data.profile
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=profile.get("name") or profile.get("username") or "Endurain",
            manufacturer="Endurain",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.client.base_url,
        )

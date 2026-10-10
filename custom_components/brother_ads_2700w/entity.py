"""Base entity for the Brother ADS-2700W."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_FIRMWARE, CONF_MODEL, DOMAIN
from .coordinator import BrotherAdsCoordinator


class BrotherAdsEntity(CoordinatorEntity[BrotherAdsCoordinator]):
    """Common base for all entities of the scanner."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BrotherAdsCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        serial = entry.unique_id
        model = entry.data.get(CONF_MODEL) or "ADS-2700W"
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="Brother",
            model=model,
            name=f"Brother {model}",
            serial_number=serial,
            sw_version=entry.data.get(CONF_FIRMWARE) or None,
            configuration_url=f"http://{entry.data[CONF_HOST]}",
        )

    @property
    def online(self) -> bool:
        """Whether the scanner answered the last poll."""
        return self.coordinator.data is not None and self.coordinator.data.online

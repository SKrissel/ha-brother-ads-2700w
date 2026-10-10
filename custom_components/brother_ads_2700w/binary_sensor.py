"""Connectivity sensor for the Brother ADS-2700W."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BrotherAdsConfigEntry, BrotherAdsCoordinator
from .entity import BrotherAdsEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrotherAdsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the connectivity sensor."""
    async_add_entities([BrotherAdsOnlineSensor(entry.runtime_data)])


class BrotherAdsOnlineSensor(BrotherAdsEntity, BinarySensorEntity):
    """Whether the scanner is switched on and reachable."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: BrotherAdsCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "online")

    @property
    def is_on(self) -> bool:
        """Return true if the scanner answered the last poll."""
        return self.online

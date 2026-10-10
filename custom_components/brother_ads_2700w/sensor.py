"""Sensors for the Brother ADS-2700W."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import Maintenance
from .coordinator import BrotherAdsConfigEntry, BrotherAdsCoordinator, BrotherAdsData
from .entity import BrotherAdsEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BrotherAdsSensorDescription(SensorEntityDescription):
    """Describes a scanner sensor."""

    value_fn: Callable[[BrotherAdsData], StateType]
    attrs_fn: Callable[[BrotherAdsData], dict[str, Any]] | None = None
    # Live values are only meaningful while the scanner is switched on;
    # everything else keeps (and restores) its last known value.
    live: bool = False


def _m(attr: str) -> Callable[[BrotherAdsData], StateType]:
    def value(data: BrotherAdsData) -> StateType:
        maintenance: Maintenance | None = data.maintenance
        return getattr(maintenance, attr) if maintenance else None

    return value


def _error_attrs(data: BrotherAdsData) -> dict[str, Any]:
    if data.maintenance is None:
        return {}
    return {"errors": [asdict(err) for err in data.maintenance.errors]}


SENSORS: tuple[BrotherAdsSensorDescription, ...] = (
    BrotherAdsSensorDescription(
        key="page_count",
        translation_key="page_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_m("page_count"),
    ),
    BrotherAdsSensorDescription(
        key="roller_remaining",
        translation_key="roller_remaining",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_m("roller_percent"),
    ),
    BrotherAdsSensorDescription(
        key="roller_remaining_pages",
        translation_key="roller_remaining_pages",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_m("roller_remaining"),
    ),
    BrotherAdsSensorDescription(
        key="maintenance_remaining",
        translation_key="maintenance_remaining",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_m("maintenance_percent"),
    ),
    BrotherAdsSensorDescription(
        key="maintenance_remaining_pages",
        translation_key="maintenance_remaining_pages",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_m("maintenance_remaining"),
    ),
    BrotherAdsSensorDescription(
        key="paper_jams",
        translation_key="paper_jams",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_m("paper_jams"),
    ),
    BrotherAdsSensorDescription(
        key="errors",
        translation_key="errors",
        value_fn=lambda data: (
            len(data.maintenance.errors) if data.maintenance else None
        ),
        attrs_fn=_error_attrs,
    ),
    BrotherAdsSensorDescription(
        key="roller_replace_count",
        translation_key="roller_replace_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_m("roller_replace_count"),
    ),
    BrotherAdsSensorDescription(
        key="maintenance_reset_count",
        translation_key="maintenance_reset_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_m("maintenance_reset_count"),
    ),
    BrotherAdsSensorDescription(
        key="clock_offset",
        translation_key="clock_offset",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        live=True,
        value_fn=lambda data: data.clock_offset,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrotherAdsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(BrotherAdsSensor(coordinator, desc) for desc in SENSORS)


class BrotherAdsSensor(BrotherAdsEntity, RestoreSensor):
    """A scanner sensor that keeps its last value while the scanner is off."""

    entity_description: BrotherAdsSensorDescription

    def __init__(
        self,
        coordinator: BrotherAdsCoordinator,
        description: BrotherAdsSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._restored: StateType = None

    async def async_added_to_hass(self) -> None:
        """Restore the last value after a restart while the scanner is off."""
        await super().async_added_to_hass()
        if self.entity_description.live:
            return
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._restored = last.native_value  # type: ignore[assignment]

    @property
    def available(self) -> bool:
        """Live sensors are only available while the scanner is online."""
        if self.entity_description.live:
            return super().available and self.online
        return super().available

    @property
    def native_value(self) -> StateType:
        """Return the current or last known value."""
        data = self.coordinator.data
        value = self.entity_description.value_fn(data) if data else None
        if value is None and not self.entity_description.live:
            return self._restored
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if self.entity_description.attrs_fn is None or self.coordinator.data is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data) or None

"""Time sync button for the Brother ADS-2700W."""

from __future__ import annotations

import asyncio

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import BrotherAdsError, InvalidAuth
from .const import DOMAIN
from .coordinator import BrotherAdsConfigEntry, BrotherAdsCoordinator
from .entity import BrotherAdsEntity

PARALLEL_UPDATES = 1

# The device needs a moment to reach its SNTP server.
REFRESH_DELAY = 3


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrotherAdsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button."""
    async_add_entities([BrotherAdsSyncTimeButton(entry.runtime_data)])


class BrotherAdsSyncTimeButton(BrotherAdsEntity, ButtonEntity):
    """Makes the scanner sync its clock via SNTP."""

    _attr_translation_key = "sync_time"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BrotherAdsCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "sync_time")

    @property
    def available(self) -> bool:
        """Only available while the scanner is switched on."""
        return super().available and self.online

    async def async_press(self) -> None:
        """Sync the clock and refresh the clock offset."""
        try:
            await self.coordinator.async_sync_time()
        except InvalidAuth as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except BrotherAdsError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="sync_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await asyncio.sleep(REFRESH_DELAY)
        await self.coordinator.async_request_refresh()

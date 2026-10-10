"""Data update coordinator for the Brother ADS-2700W."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    BrotherAdsClient,
    BrotherAdsError,
    CannotConnect,
    InvalidResponse,
    Maintenance,
    TimeSettings,
)
from .const import (
    CLOCK_TOLERANCE,
    CONF_AUTO_TIME_SYNC,
    DEFAULT_AUTO_TIME_SYNC,
    DOMAIN,
    SCAN_INTERVAL,
    TIME_SYNC_RETRY,
)

_LOGGER = logging.getLogger(__name__)

type BrotherAdsConfigEntry = ConfigEntry[BrotherAdsCoordinator]


@dataclass(frozen=True)
class BrotherAdsData:
    """State shared with the entities."""

    online: bool
    # Last known values; kept while the scanner is switched off.
    maintenance: Maintenance | None
    # Device clock minus Home Assistant clock in seconds (only while online).
    clock_offset: float | None


class BrotherAdsCoordinator(DataUpdateCoordinator[BrotherAdsData]):
    """Polls the scanner and keeps its clock in sync.

    The scanner is usually switched off. Being unreachable is therefore a
    normal state and not an update failure: the entities keep their last
    values and only the connectivity sensor changes.
    """

    config_entry: BrotherAdsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: BrotherAdsConfigEntry,
        client: BrotherAdsClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self._online = False
        self._last_maintenance: Maintenance | None = None
        self._last_sync_attempt: datetime | None = None

    @property
    def auto_time_sync(self) -> bool:
        """Whether the clock is synced automatically."""
        return self.config_entry.options.get(
            CONF_AUTO_TIME_SYNC, DEFAULT_AUTO_TIME_SYNC
        )

    async def _async_update_data(self) -> BrotherAdsData:
        try:
            status = await self.client.async_get_status()
        except CannotConnect as err:
            if self._online:
                _LOGGER.debug("Scanner went offline: %s", err)
            self._online = False
            return BrotherAdsData(False, self._last_maintenance, None)
        except InvalidResponse as err:
            raise UpdateFailed(str(err)) from err

        if not self._online:
            _LOGGER.debug("Scanner is online")
            # Fresh start of the device: allow an immediate sync attempt.
            self._last_sync_attempt = None
        self._online = True
        self._last_maintenance = status.maintenance

        offset: float | None = None
        if status.device_time is not None:
            offset = (status.device_time - dt_util.utcnow()).total_seconds()

        if (
            self.auto_time_sync
            and offset is not None
            and abs(offset) > CLOCK_TOLERANCE
        ):
            await self._async_auto_sync(offset)

        return BrotherAdsData(True, status.maintenance, offset)

    async def _async_auto_sync(self, offset: float) -> None:
        now = dt_util.utcnow()
        if (
            self._last_sync_attempt is not None
            and now - self._last_sync_attempt < TIME_SYNC_RETRY
        ):
            return
        _LOGGER.debug("Device clock is off by %.0f s, syncing", offset)
        try:
            await self.async_sync_time()
        except BrotherAdsError as err:
            _LOGGER.warning("Automatic time sync failed: %s", err)

    async def async_sync_time(self) -> None:
        """Trigger an SNTP sync on the device."""
        self._last_sync_attempt = dt_util.utcnow()
        await self.client.async_sync_time(self._time_settings())

    @staticmethod
    def _time_settings() -> TimeSettings:
        """Derive the device time zone settings from Home Assistant's zone."""
        tz = dt_util.get_default_time_zone()
        year = dt_util.now().year
        offsets = [
            datetime(year, month, 1, tzinfo=tz).utcoffset() for month in (1, 7)
        ]
        standard = min(o for o in offsets if o is not None)
        return TimeSettings(
            utc_offset_seconds=int(standard.total_seconds()),
            auto_daylight=offsets[0] != offsets[1],
        )

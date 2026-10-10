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
    ScannerState,
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
    # Operating state (only while online).
    state: ScannerState | None = None


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

        # Compare the time the device displays with Home Assistant's local
        # time. This also catches a wrong time zone or daylight saving offset.
        offset: float | None = None
        if status.device_time is not None:
            local_now = dt_util.now().replace(tzinfo=None)
            offset = (status.device_time - local_now).total_seconds()

        if (
            self.auto_time_sync
            and offset is not None
            and abs(offset) > CLOCK_TOLERANCE
        ):
            await self._async_auto_sync(f"clock is off by {offset:.0f} s")

        return BrotherAdsData(True, status.maintenance, offset, status.state)

    async def _async_auto_sync(self, reason: str) -> None:
        now = dt_util.utcnow()
        if (
            self._last_sync_attempt is not None
            and now - self._last_sync_attempt < TIME_SYNC_RETRY
        ):
            return
        _LOGGER.debug("Syncing device clock: %s", reason)
        try:
            await self.async_sync_time()
        except BrotherAdsError as err:
            _LOGGER.warning("Automatic time sync failed: %s", err)

    async def async_sync_time(self) -> None:
        """Trigger an SNTP sync on the device."""
        self._last_sync_attempt = dt_util.utcnow()
        await self.client.async_sync_time(self._time_settings())

    @staticmethod
    def _current_utc_offset() -> int:
        offset = dt_util.now().utcoffset()
        return int(offset.total_seconds()) if offset is not None else 0

    @classmethod
    def _time_settings(cls) -> TimeSettings:
        """Use the offset currently in effect in Home Assistant's time zone.

        The device's own daylight saving switch does not take effect (it
        shows standard time all year), so the current offset including
        daylight saving is written instead. After a daylight saving change
        the displayed time is off by an hour, which triggers a new sync.
        """
        return TimeSettings(
            utc_offset_seconds=cls._current_utc_offset(), auto_daylight=False
        )

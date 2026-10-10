"""The Brother ADS-2700W integration."""

from __future__ import annotations

import aiohttp

from homeassistant.const import CONF_HOST, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import BrotherAdsClient
from .coordinator import BrotherAdsConfigEntry, BrotherAdsCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]


def create_session(
    hass: HomeAssistant, auto_cleanup: bool = True
) -> aiohttp.ClientSession:
    """Create a session whose cookie jar accepts cookies from IP addresses.

    The login is bound to a session cookie, and aiohttp ignores cookies from
    IP addresses by default. With auto_cleanup the session is detached when
    the config entry is unloaded.
    """
    return async_create_clientsession(
        hass, auto_cleanup=auto_cleanup, cookie_jar=aiohttp.CookieJar(unsafe=True)
    )


async def async_setup_entry(hass: HomeAssistant, entry: BrotherAdsConfigEntry) -> bool:
    """Set up the scanner from a config entry."""
    session = create_session(hass)
    client = BrotherAdsClient(
        session, entry.data[CONF_HOST], entry.data.get(CONF_PASSWORD, "")
    )
    coordinator = BrotherAdsCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BrotherAdsConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: BrotherAdsConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

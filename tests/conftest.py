"""Fixtures for the Brother ADS-2700W tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from aiohttp.test_utils import TestServer
import pytest

from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.brother_ads_2700w.const import (
    CONF_FIRMWARE,
    CONF_MODEL,
    DOMAIN,
)

from .fake_scanner import SERIAL, FakeScanner


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the integration from custom_components."""


@pytest.fixture
async def scanner(socket_enabled: None) -> AsyncGenerator[tuple[FakeScanner, str]]:
    """Run the fake scanner on localhost and return it with its host:port."""
    fake = FakeScanner()
    server = TestServer(fake.app(), host="127.0.0.1")
    await server.start_server()
    yield fake, f"127.0.0.1:{server.port}"
    await server.close()


@pytest.fixture
def config_entry(scanner: tuple[FakeScanner, str]) -> MockConfigEntry:
    """A config entry pointing at the fake scanner."""
    _, host = scanner
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL,
        title="Brother ADS-2700W",
        data={
            CONF_HOST: host,
            CONF_PASSWORD: "geheim",
            CONF_MODEL: "ADS-2700W",
            CONF_FIRMWARE: "M:4.28/P:3.89",
        },
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry

"""Tests for setup, entities, offline handling and time sync."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.brother_ads_2700w.const import CONF_AUTO_TIME_SYNC, DOMAIN

from .fake_scanner import SERIAL, FakeScanner

SUMMER = "2026-10-10 17:59:00+00:00"  # Europe/Berlin: CEST, UTC+2
WINTER = "2026-11-10 17:59:00+00:00"  # Europe/Berlin: CET, UTC+1


def _sync_body(offset: int) -> str:
    sign = 1 if offset < 0 else 0
    return (
        f"TimeMethod=1&&TimeZoneNegativ={sign}&&TimeDiffSecs={abs(offset)}"
        "&&ClockType=0&&AutoDaylight=0&&Date_Save"
    )


@pytest.fixture(autouse=True)
async def _berlin_summer(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Run all tests in Europe/Berlin at a fixed time during DST."""
    freezer.move_to(SUMMER)
    await hass.config.async_set_time_zone("Europe/Berlin")


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{SERIAL}_{key}"
    )
    assert entity_id, f"{platform} {key} not registered"
    return entity_id


def _state(hass: HomeAssistant, platform: str, key: str) -> State:
    state = hass.states.get(_entity_id(hass, platform, key))
    assert state is not None
    return state


async def _go_offline(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    coordinator = entry.runtime_data
    coordinator.client._host = "127.0.0.1:1"  # noqa: SLF001
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_setup_and_values(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Values from the maintenance export end up in the sensors."""
    assert setup_integration.state is ConfigEntryState.LOADED

    assert _state(hass, "binary_sensor", "online").state == STATE_ON
    page_count = _state(hass, "sensor", "page_count")
    assert page_count.state == "1060"
    assert page_count.attributes["unit_of_measurement"] == "pages"
    assert page_count.entity_id == "sensor.brother_ads_2700w_scanned_pages"
    assert _state(hass, "sensor", "roller_remaining").state == "98.9"
    assert _state(hass, "sensor", "roller_remaining_pages").state == "98940"
    assert _state(hass, "sensor", "maintenance_remaining").state == "78.8"
    assert _state(hass, "sensor", "maintenance_remaining_pages").state == "3940"
    assert _state(hass, "sensor", "paper_jams").state == "0"
    assert _state(hass, "sensor", "errors").state == "0"
    assert abs(float(_state(hass, "sensor", "clock_offset").state)) < 5


async def test_auto_time_sync(
    hass: HomeAssistant,
    scanner: tuple[FakeScanner, str],
    config_entry: MockConfigEntry,
) -> None:
    """A wrong device clock triggers an SNTP sync with Home Assistant's zone."""
    fake, _ = scanner
    fake.clock_error = timedelta(days=-3000)  # factory reset date

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # The offset currently in effect (CEST), not standard time + DST flag,
    # because the device ignores its own DST switch.
    assert fake.sync_requests == [_sync_body(7200)]
    # Logged out again afterwards.
    assert not any(fake.sessions.values())

    # No second attempt within the retry interval.
    fake.clock_error = timedelta(days=-3000)
    await config_entry.runtime_data.async_refresh()
    assert len(fake.sync_requests) == 1


async def test_auto_time_sync_disabled(
    hass: HomeAssistant,
    scanner: tuple[FakeScanner, str],
    config_entry: MockConfigEntry,
) -> None:
    """No sync when the option is off."""
    fake, _ = scanner
    fake.clock_error = timedelta(days=-3000)
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_AUTO_TIME_SYNC: False}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert fake.sync_requests == []
    assert float(_state(hass, "sensor", "clock_offset").state) < -86400


async def test_time_zone_settings(
    hass: HomeAssistant,
    scanner: tuple[FakeScanner, str],
    config_entry: MockConfigEntry,
) -> None:
    """Negative offsets and zones without daylight saving are handled."""
    fake, _ = scanner
    fake.clock_error = timedelta(days=-3000)
    await hass.config.async_set_time_zone("America/Phoenix")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert fake.sync_requests == [_sync_body(-25200)]


async def test_no_sync_when_clock_is_right(
    hass: HomeAssistant,
    scanner: tuple[FakeScanner, str],
    setup_integration: MockConfigEntry,
) -> None:
    """A device showing the right local time is left alone."""
    fake, _ = scanner
    await setup_integration.runtime_data.async_refresh()
    assert fake.sync_requests == []


async def test_wrong_utc_offset_is_fixed(
    hass: HomeAssistant,
    scanner: tuple[FakeScanner, str],
    config_entry: MockConfigEntry,
) -> None:
    """A device showing standard time during DST is detected and synced.

    The Date header carries the displayed local time, so a wrong offset shows
    up as clock offset although the device clock is right in UTC.
    """
    fake, _ = scanner
    fake.utc_offset = 3600  # CET while CEST is in effect
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert fake.sync_requests == [_sync_body(7200)]
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert abs(float(_state(hass, "sensor", "clock_offset").state)) < 5


async def test_resync_on_dst_change(
    hass: HomeAssistant,
    scanner: tuple[FakeScanner, str],
    setup_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After the switch to standard time the device is synced again."""
    fake, _ = scanner
    coordinator = setup_integration.runtime_data

    freezer.move_to(WINTER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert fake.sync_requests == [_sync_body(3600)]
    assert fake.utc_offset == 3600


async def test_offline_keeps_values(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Switching the scanner off keeps counters but marks live entities."""
    await _go_offline(hass, setup_integration)

    assert _state(hass, "binary_sensor", "online").state == STATE_OFF
    assert _state(hass, "sensor", "page_count").state == "1060"
    assert _state(hass, "sensor", "roller_remaining").state == "98.9"
    assert _state(hass, "sensor", "clock_offset").state == STATE_UNAVAILABLE
    assert _state(hass, "button", "sync_time").state == STATE_UNAVAILABLE


async def test_setup_while_offline_restores_values(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """After a restart with the scanner off the last values are restored."""
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    entity_id = registry.async_get_or_create(
        "sensor", DOMAIN, f"{SERIAL}_page_count", config_entry=config_entry
    ).entity_id
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(entity_id, "1000"),
                {"native_value": 1000, "native_unit_of_measurement": None},
            )
        ],
    )
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, "host": "127.0.0.1:1"}
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(entity_id).state == "1000"
    assert _state(hass, "binary_sensor", "online").state == STATE_OFF


async def test_errors_sensor(
    hass: HomeAssistant,
    scanner: tuple[FakeScanner, str],
    config_entry: MockConfigEntry,
) -> None:
    """Entries of the error history are exposed as attribute."""
    fake, _ = scanner
    fake.errors = [("Paper Jam", 2)]
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = _state(hass, "sensor", "errors")
    assert state.state == "1"
    assert state.attributes["errors"] == [{"message": "Paper Jam", "count": 2}]


async def test_sync_button(
    hass: HomeAssistant,
    scanner: tuple[FakeScanner, str],
    setup_integration: MockConfigEntry,
) -> None:
    """Pressing the button triggers a sync."""
    fake, _ = scanner
    fake.sync_requests.clear()
    with patch("custom_components.brother_ads_2700w.button.REFRESH_DELAY", 0):
        await hass.services.async_call(
            "button",
            "press",
            {ATTR_ENTITY_ID: _entity_id(hass, "button", "sync_time")},
            blocking=True,
        )
    assert fake.sync_requests == [_sync_body(7200)]


async def test_unload(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    """The entry can be unloaded."""
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state is ConfigEntryState.NOT_LOADED


async def test_entity_icons(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Every entity has an icon defined in icons.json."""
    icons = (await async_get_icons(hass, "entity", {DOMAIN}))[DOMAIN]
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, setup_integration.entry_id)
    assert entries
    for entry in entries:
        assert entry.translation_key in icons[entry.domain], entry.entity_id
    assert icons["binary_sensor"]["online"]["state"]["on"] == "mdi:scanner"
    assert _state(hass, "binary_sensor", "online").name == "Brother ADS-2700W Online"

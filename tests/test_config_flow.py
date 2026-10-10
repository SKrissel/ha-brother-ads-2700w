"""Tests for the config and options flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.brother_ads_2700w.const import CONF_AUTO_TIME_SYNC, DOMAIN

from .fake_scanner import SERIAL, FakeScanner


async def test_user_flow(hass: HomeAssistant, scanner: tuple[FakeScanner, str]) -> None:
    """A working host and password create an entry keyed by serial number."""
    _, host = scanner
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host, CONF_PASSWORD: "geheim"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Brother ADS-2700W"
    assert result["result"].unique_id == SERIAL
    assert result["data"][CONF_HOST] == host
    assert result["data"]["firmware"] == "M:4.28/P:3.89"


async def test_user_flow_without_password(
    hass: HomeAssistant, scanner: tuple[FakeScanner, str]
) -> None:
    """The password is optional, the maintenance export needs no login."""
    _, host = scanner
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host, CONF_PASSWORD: ""}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, scanner: tuple[FakeScanner, str]
) -> None:
    """A wrong password is reported and can be corrected."""
    _, host = scanner
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host, CONF_PASSWORD: "falsch"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host, CONF_PASSWORD: "geheim"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, socket_enabled: None
) -> None:
    """An unreachable scanner is reported."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1:1", CONF_PASSWORD: ""}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    scanner: tuple[FakeScanner, str],
    config_entry: MockConfigEntry,
) -> None:
    """The same scanner cannot be added twice."""
    _, host = scanner
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host, CONF_PASSWORD: ""}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Host and password can be changed."""
    entry = setup_integration
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: entry.data[CONF_HOST], CONF_PASSWORD: ""}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PASSWORD] == ""


async def test_options_flow(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Automatic time sync can be switched off."""
    entry = setup_integration
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_AUTO_TIME_SYNC: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_AUTO_TIME_SYNC: False}

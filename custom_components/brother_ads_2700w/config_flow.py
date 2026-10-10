"""Config flow for the Brother ADS-2700W integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import create_session
from .api import (
    BrotherAdsClient,
    CannotConnect,
    InvalidAuth,
    InvalidResponse,
    Maintenance,
)
from .const import (
    CONF_AUTO_TIME_SYNC,
    CONF_FIRMWARE,
    CONF_MODEL,
    DEFAULT_AUTO_TIME_SYNC,
    DOMAIN,
)
from .coordinator import BrotherAdsConfigEntry

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Optional(CONF_PASSWORD, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


async def _validate(hass: HomeAssistant, host: str, password: str) -> Maintenance:
    session = create_session(hass, auto_cleanup=False)
    try:
        client = BrotherAdsClient(session, host, password)
        status = await client.async_get_status()
        if password:
            await client.async_validate_auth()
        return status.maintenance
    finally:
        session.detach()


class BrotherAdsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def _async_try(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> Maintenance | None:
        try:
            return await _validate(
                self.hass,
                user_input[CONF_HOST].strip(),
                user_input.get(CONF_PASSWORD, ""),
            )
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except InvalidResponse:
            errors["base"] = "unsupported"
        except Exception:
            _LOGGER.exception("Unexpected error")
            errors["base"] = "unknown"
        return None

    @staticmethod
    def _entry_data(user_input: dict[str, Any], info: Maintenance) -> dict[str, Any]:
        return {
            CONF_HOST: user_input[CONF_HOST].strip(),
            CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
            CONF_MODEL: info.model,
            CONF_FIRMWARE: info.firmware_sub,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for host and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            info = await self._async_try(user_input, errors)
            if info is not None:
                await self.async_set_unique_id(info.serial)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: user_input[CONF_HOST].strip()}
                )
                return self.async_create_entry(
                    title=f"Brother {info.model}",
                    data=self._entry_data(user_input, info),
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host or password."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            info = await self._async_try(user_input, errors)
            if info is not None:
                await self.async_set_unique_id(info.serial)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates=self._entry_data(user_input, info)
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: BrotherAdsConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return BrotherAdsOptionsFlow()


class BrotherAdsOptionsFlow(OptionsFlow):
    """Handle options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTO_TIME_SYNC,
                        default=self.config_entry.options.get(
                            CONF_AUTO_TIME_SYNC, DEFAULT_AUTO_TIME_SYNC
                        ),
                    ): bool,
                }
            ),
        )

"""Client for the embedded web server of the Brother ADS-2700W."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
import io
import logging
from typing import Any

import aiohttp

from .const import MAINTENANCE_INTERVAL, ROLLER_LIFE

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5
# Saving the date settings makes the device contact its SNTP server, which
# takes a couple of seconds before it answers.
TIME_SYNC_TIMEOUT = 20

MAINTENANCE_PATH = "/ft/gen_export_maintenance"
STATUS_PAGE_PATH = "/EWS/general/status.html"
DATE_PAGE_PATH = "/EWS/admin/date.html"
LOGIN_PATH = "/auth/login"
LOGIN_STATUS_PATH = "/auth/status"
LOGOUT_PATH = "/auth/logout"
DATE_INFO_PATH = "/ft/date_info"


class BrotherAdsError(Exception):
    """Base error."""


class CannotConnect(BrotherAdsError):
    """The device could not be reached."""


class InvalidAuth(BrotherAdsError):
    """The administrator password was rejected."""


class InvalidResponse(BrotherAdsError):
    """The device answered with something unexpected."""


@dataclass(frozen=True)
class DeviceError:
    """An entry of the device error history."""

    message: str
    count: int | None


@dataclass(frozen=True)
class Maintenance:
    """Parsed content of the maintenance CSV export."""

    model: str
    serial: str
    firmware_main: str
    firmware_sub: str
    memory_mb: int | None
    page_count: int | None
    roller_used: int | None
    roller_replace_count: int | None
    maintenance_used: int | None
    maintenance_reset_count: int | None
    paper_jams: int | None
    errors: tuple[DeviceError, ...] = field(default_factory=tuple)

    @property
    def roller_remaining(self) -> int | None:
        """Pages left until the pick-up roller should be replaced."""
        return _remaining(self.roller_used, ROLLER_LIFE)

    @property
    def roller_percent(self) -> float | None:
        """Remaining pick-up roller life in percent."""
        return _percent(self.roller_used, ROLLER_LIFE)

    @property
    def maintenance_remaining(self) -> int | None:
        """Pages left until the scheduled maintenance is due."""
        return _remaining(self.maintenance_used, MAINTENANCE_INTERVAL)

    @property
    def maintenance_percent(self) -> float | None:
        """Remaining scheduled maintenance interval in percent."""
        return _percent(self.maintenance_used, MAINTENANCE_INTERVAL)


@dataclass(frozen=True)
class DeviceStatus:
    """Result of a single poll."""

    maintenance: Maintenance
    device_time: datetime | None


@dataclass(frozen=True)
class TimeSettings:
    """Time zone settings written to the device together with the sync."""

    utc_offset_seconds: int
    auto_daylight: bool


def _remaining(used: int | None, limit: int) -> int | None:
    if used is None:
        return None
    return max(limit - used, 0)


def _percent(used: int | None, limit: int) -> float | None:
    remaining = _remaining(used, limit)
    if remaining is None:
        return None
    return round(remaining / limit * 100, 1)


def _int(data: dict[str, str], key: str) -> int | None:
    try:
        return int(data.get(key, "").strip())
    except ValueError:
        return None


def parse_maintenance(text: str) -> Maintenance:
    """Parse the maintenance CSV export (one header row, one value row)."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if len(rows) < 2 or not rows[0] or rows[0][0] != "Model Name":
        raise InvalidResponse("Unexpected maintenance export format")
    data = dict(zip(rows[0], rows[1], strict=False))

    errors = []
    for i in range(1, 11):
        message = data.get(f"Error{i}", "").strip()
        if message:
            errors.append(DeviceError(message, _int(data, f"Error Count {i}")))

    return Maintenance(
        model=data.get("Model Name", "").strip(),
        serial=data.get("Serial No.", "").strip(),
        firmware_main=data.get("Main Firmware Version", "").strip(),
        firmware_sub=data.get("Sub3 Firmware Version", "").strip(),
        memory_mb=_int(data, "Memory Size"),
        page_count=_int(data, "Scan Page Count"),
        # Despite the column name these count used pages since the last
        # replacement / reset, see the "used / limit" display in the web UI.
        roller_used=_int(data, "Remaining Life(Pick up Roller)"),
        roller_replace_count=_int(data, "Replace Count(Pick up Roller)"),
        maintenance_used=_int(data, "Remaining Life(Scheduled Maintenance)"),
        maintenance_reset_count=_int(data, "Reset Count(Scheduled Maintenance)"),
        paper_jams=_int(data, "Total Paper Jams"),
        errors=tuple(errors),
    )


def _parse_date_header(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


class BrotherAdsClient:
    """Talks to the embedded web server (Mongoose) of the scanner.

    The session must use a cookie jar that accepts cookies from IP addresses
    (``aiohttp.CookieJar(unsafe=True)``), because the login is bound to the
    ``access`` session cookie.
    """

    def __init__(
        self, session: aiohttp.ClientSession, host: str, password: str = ""
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._host = host
        self._password = password

    @property
    def base_url(self) -> str:
        """Base URL of the web interface."""
        return f"http://{self._host}"

    async def _request(
        self,
        method: str,
        path: str,
        data: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> tuple[int, str, dict[str, str]]:
        headers: dict[str, str] = {}
        body: bytes | None = None
        if data is not None:
            body = data.encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["Referer"] = f"{self.base_url}{DATE_PAGE_PATH}"
        try:
            async with self._session.request(
                method,
                f"{self.base_url}{path}",
                data=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=False,
            ) as resp:
                try:
                    text = await resp.text(errors="replace")
                except aiohttp.ClientPayloadError:
                    # Some endpoints close the connection without a proper body.
                    text = ""
                return resp.status, text, dict(resp.headers)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(f"{method} {path}: {err!r}") from err

    async def async_get_status(self) -> DeviceStatus:
        """Fetch the maintenance export. Works without login."""
        status, text, headers = await self._request("GET", MAINTENANCE_PATH)
        if status != 200:
            raise InvalidResponse(f"Maintenance export returned HTTP {status}")
        return DeviceStatus(
            maintenance=parse_maintenance(text),
            device_time=_parse_date_header(headers.get("Date")),
        )

    async def _async_login(self) -> None:
        # The session cookie is handed out before the login and then unlocked.
        self._session.cookie_jar.clear()
        await self._request("GET", STATUS_PAGE_PATH)
        if not self._password:
            return
        # The web UI escapes "&" this way instead of URL-encoding.
        password = self._password.replace("&", "&amp;")
        try:
            await self._request(
                "POST", LOGIN_PATH, f"PASS={password}&&Admin_Password_Save"
            )
        except CannotConnect:
            # The login response is malformed on some firmware versions;
            # the status check below tells whether it worked.
            _LOGGER.debug("Ignoring error while reading login response")
        status, _, _ = await self._request("GET", LOGIN_STATUS_PATH)
        if status == 401:
            raise InvalidAuth("Password rejected")

    async def _async_logout(self) -> None:
        if not self._password:
            return
        try:
            await self._request("POST", LOGOUT_PATH, "")
        except BrotherAdsError:
            _LOGGER.debug("Logout failed", exc_info=True)

    async def async_validate_auth(self) -> None:
        """Log in and out once to check the password."""
        await self._async_login()
        await self._async_logout()

    async def async_sync_time(self, settings: TimeSettings) -> None:
        """Save the SNTP date settings, which makes the device sync its clock."""
        offset = settings.utc_offset_seconds
        payload: dict[str, Any] = {
            "TimeMethod": 1,  # SNTP
            "TimeZoneNegativ": 1 if offset < 0 else 0,
            "TimeDiffSecs": abs(offset),
            "ClockType": 0,
            "AutoDaylight": 1 if settings.auto_daylight else 0,
        }
        body = "&&".join(f"{k}={v}" for k, v in payload.items()) + "&&Date_Save"

        await self._async_login()
        try:
            status, _, _ = await self._request(
                "POST", DATE_INFO_PATH, body, timeout=TIME_SYNC_TIMEOUT
            )
        finally:
            await self._async_logout()
        if status == 401:
            raise InvalidAuth("Not allowed to change the date settings")
        if status != 200:
            raise InvalidResponse(f"Date settings returned HTTP {status}")

"""Tests for parsing device responses."""

from __future__ import annotations

import pytest

from custom_components.brother_ads_2700w.api import (
    InvalidResponse,
    parse_scanner_state,
)


def test_parse_state_captured() -> None:
    """Responses as captured from the device."""
    state = parse_scanner_state(
        '<?xml version="1.0" encoding="utf-8"?><ScannerStatus>'
        "<Device_Status>Cover is Open</Device_Status><Contact></Contact>"
        "<Location></Location></ScannerStatus>"
    )
    assert state.message == "Cover is Open"
    assert state.status_type is None


def test_parse_state_with_type() -> None:
    """StatusType is read when the firmware sends it."""
    state = parse_scanner_state(
        "<ScannerStatus><Device_Status>Paper Jam</Device_Status>"
        "<StatusType>5</StatusType></ScannerStatus>"
    )
    assert state.status_type == 5


@pytest.mark.parametrize(
    "text", ["", "not xml", "<ScannerStatus><Device_Status/></ScannerStatus>"]
)
def test_parse_state_invalid(text: str) -> None:
    """Broken responses raise InvalidResponse."""
    with pytest.raises(InvalidResponse):
        parse_scanner_state(text)

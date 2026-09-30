"""UI setup and entry lifecycle checks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.needle import async_setup_entry, async_unload_entry
from custom_components.needle.config_flow import NeedleConfigFlow, _schema


async def test_user_creates_entry(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    flow = NeedleConfigFlow()
    flow.hass = hass
    with (
        patch.object(flow, "async_set_unique_id", AsyncMock()),
        patch.object(flow, "_abort_if_unique_id_configured"),
    ):
        result = await flow.async_step_user({"min_confidence": 0.8})
    assert result["type"] == "create_entry"
    assert result["data"] == {"min_confidence": 0.8}
    await hass.async_stop(force=True)


async def test_invalid_confidence_shows_form(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    flow = NeedleConfigFlow()
    flow.hass = hass
    with (
        patch.object(flow, "async_set_unique_id", AsyncMock()),
        patch.object(flow, "_abort_if_unique_id_configured"),
    ):
        result = await flow.async_step_user({"min_confidence": 2})
    assert result["errors"] == {"base": "invalid_confidence"}
    await hass.async_stop(force=True)


def test_schema_default():
    assert _schema(0.8)({}) == {"min_confidence": 0.8}


async def test_loading_failure_is_retryable():
    hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(side_effect=OSError("missing library"))
    )
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, SimpleNamespace())


async def test_setup_and_unload_forward_conversation():
    hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(),
        config_entries=SimpleNamespace(
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
        ),
    )
    entry = SimpleNamespace()
    assert await async_setup_entry(hass, entry)
    assert await async_unload_entry(hass, entry)
    hass.config_entries.async_forward_entry_setups.assert_awaited_once()
    hass.config_entries.async_unload_platforms.assert_awaited_once()

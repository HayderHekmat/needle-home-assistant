"""Local Needle 3 conversation integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .engine import warm_up

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.CONVERSATION]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load Needle outside the event loop, then register the agent."""
    try:
        await hass.async_add_executor_job(warm_up)
    except Exception as err:
        _LOGGER.warning("Unable to load Needle: %s", err)
        raise ConfigEntryNotReady(
            f"Unable to load Needle engine or model: {err}"
        ) from err
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the conversation entity."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

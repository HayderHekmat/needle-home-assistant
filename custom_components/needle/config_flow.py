"""UI configuration for Needle."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_MIN_CONFIDENCE, DEFAULT_MIN_CONFIDENCE, DOMAIN


def _schema(default: float) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_MIN_CONFIDENCE, default=default): vol.All(
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=1, step=0.05, mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
                vol.Range(min=0, max=1),
            )
        }
    )


class NeedleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a single local agent."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            try:
                data = _schema(DEFAULT_MIN_CONFIDENCE)(user_input)
            except vol.Invalid:
                return self.async_show_form(
                    step_id="user",
                    data_schema=_schema(DEFAULT_MIN_CONFIDENCE),
                    errors={"base": "invalid_confidence"},
                )
            return self.async_create_entry(title="Needle 3", data=data)
        return self.async_show_form(
            step_id="user", data_schema=_schema(DEFAULT_MIN_CONFIDENCE)
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return NeedleOptionsFlow()


class NeedleOptionsFlow(config_entries.OptionsFlow):
    """Change the confidence threshold without reloading the model."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        default = self.config_entry.options.get(
            CONF_MIN_CONFIDENCE,
            self.config_entry.data.get(CONF_MIN_CONFIDENCE, DEFAULT_MIN_CONFIDENCE),
        )
        if user_input is not None:
            try:
                data = _schema(default)(user_input)
            except vol.Invalid:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_schema(default),
                    errors={"base": "invalid_confidence"},
                )
            return self.async_create_entry(title="", data=data)
        return self.async_show_form(step_id="init", data_schema=_schema(default))

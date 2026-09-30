"""Exercise real HA chat logs and LLM APIs with controlled model predictions."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm

from custom_components.needle.const import CONF_MIN_CONFIDENCE
from custom_components.needle.conversation import (
    NeedleConversationEntity,
    _prepare_calls,
    _result_speech,
)


class Tool(llm.Tool):
    name = "HassTurnOn"
    description = "Turn on a light."
    parameters = vol.Schema({vol.Required("name"): str})

    def __init__(self, executed, fail=False):
        self.executed = executed
        self.fail = fail

    async def async_call(self, hass, tool_input, llm_context):
        self.executed.append(tool_input.tool_args["name"])
        if self.fail:
            raise HomeAssistantError("Light unavailable")
        return {
            "speech": {"plain": {"speech": f"Turned on {tool_input.tool_args['name']}"}}
        }


@pytest.fixture
async def setup_agent(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    executed = []
    context = llm.LLMContext("needle", Context(), "en", "conversation", None)
    api = llm.APIInstance(
        api=SimpleNamespace(hass=hass),
        api_prompt="Available light: Kitchen",
        llm_context=context,
        tools=[Tool(executed)],
    )
    entry = SimpleNamespace(entry_id="test", data={}, options={})
    entity = NeedleConversationEntity(entry)
    entity.hass = hass
    entity.entity_id = "conversation.needle_3"
    chat_log = conversation.ChatLog(hass, "test_conversation")
    user_input = conversation.ConversationInput(
        text="turn on Kitchen",
        context=context.context,
        conversation_id="test_conversation",
        device_id=None,
        satellite_id=None,
        language="en",
        agent_id=entity.entity_id,
    )
    with patch("homeassistant.helpers.llm.async_get_api", AsyncMock(return_value=api)):
        yield entity, chat_log, user_input, executed, api
    await hass.async_stop(force=True)


def prediction(names=("Kitchen",), **overrides):
    return {
        "type": "call",
        "confidence": 0.95,
        "function_calls": [
            {"name": "HassTurnOn", "arguments": {"name": name}} for name in names
        ],
        **overrides,
    }


async def test_actions_run_in_order_and_speech_is_from_tools(setup_agent):
    entity, log, user_input, executed, _ = setup_agent
    with patch(
        "custom_components.needle.conversation.complete",
        return_value=prediction(("Kitchen", "Bedroom")),
    ):
        result = await entity._async_handle_message(user_input, log)
    assert executed == ["Kitchen", "Bedroom"]
    assert result.conversation_id == "test_conversation"
    assert (
        result.response.speech["plain"]["speech"]
        == "Turned on Kitchen Turned on Bedroom"
    )
    assert log.content[-1].role == "assistant"


@pytest.mark.parametrize(
    "output",
    [
        prediction(confidence=0.5),
        prediction(confidence=None),
        prediction(validation={"negation": True}),
        prediction(
            function_calls=[
                {"name": "HassTurnOn", "arguments": {"name": "Kitchen"}},
                {"name": "Unknown", "arguments": {}},
            ]
        ),
        prediction(
            function_calls=[
                {"name": "HassTurnOn", "arguments": {"name": "Kitchen"}},
                {"name": "HassTurnOn", "arguments": {"name": 123}},
            ]
        ),
    ],
)
async def test_rejected_batch_has_no_side_effects(setup_agent, output):
    entity, log, user_input, executed, _ = setup_agent
    with patch("custom_components.needle.conversation.complete", return_value=output):
        result = await entity._async_handle_message(user_input, log)
    assert executed == []
    assert result.response.error_code is not None


async def test_stops_on_tool_error_and_reports_failure(setup_agent):
    entity, log, user_input, executed, api = setup_agent
    api.tools = [Tool(executed, fail=True)]
    with patch(
        "custom_components.needle.conversation.complete",
        return_value=prediction(("Kitchen", "Bedroom")),
    ):
        result = await entity._async_handle_message(user_input, log)
    assert executed == ["Kitchen"]
    assert result.response.error_code is not None
    assert "Light unavailable" in result.response.speech["plain"]["speech"]


async def test_options_threshold_takes_effect_without_reload(setup_agent):
    entity, log, user_input, executed, _ = setup_agent
    entity.entry.options[CONF_MIN_CONFIDENCE] = 0.99
    with patch(
        "custom_components.needle.conversation.complete", return_value=prediction()
    ):
        result = await entity._async_handle_message(user_input, log)
    assert executed == []
    assert result.response.error_code is not None


async def test_model_error_is_reported(setup_agent):
    entity, log, user_input, executed, _ = setup_agent
    with patch(
        "custom_components.needle.conversation.complete",
        side_effect=RuntimeError("native failure"),
    ):
        result = await entity._async_handle_message(user_input, log)
    assert executed == []
    assert result.response.error_code is not None


async def test_assist_context_is_forwarded_to_model(setup_agent):
    entity, log, user_input, _, _ = setup_agent
    with patch(
        "custom_components.needle.conversation.complete", return_value=prediction()
    ) as complete:
        await entity._async_handle_message(user_input, log)
    text, tools, system = complete.call_args.args
    assert text == user_input.text
    assert tools[0]["parameters"]["required"] == ["name"]
    assert "Available light: Kitchen" in system


async def test_suppressed_calls_are_logged_without_executing(setup_agent, caplog):
    entity, log, user_input, executed, _ = setup_agent
    entity.entry.options[CONF_MIN_CONFIDENCE] = 0
    output = prediction(
        suppressed_calls=[{"name": "HassTurnOn", "arguments": {"name": "Secret"}}]
    )
    with patch("custom_components.needle.conversation.complete", return_value=output):
        result = await entity._async_handle_message(user_input, log)
    assert executed == []
    assert result.response.error_code is not None
    assert "Needle rejected command: Some commands could not be verified" in caplog.text
    assert "Secret" not in caplog.text
    assert user_input.text not in caplog.text


async def test_debug_logs_include_prediction_and_available_tools(setup_agent, caplog):
    entity, log, user_input, executed, _ = setup_agent
    output = prediction(
        function_calls=[],
        suppressed_calls=[{"name": "HassTurnOn", "arguments": {"name": "Kitchen"}}],
        reasoning="Missing required argument",
    )
    with (
        caplog.at_level(logging.DEBUG, logger="custom_components.needle.conversation"),
        patch("custom_components.needle.conversation.complete", return_value=output),
    ):
        await entity._async_handle_message(user_input, log)
    assert executed == []
    assert "Needle request:" in caplog.text
    assert "Available light: Kitchen" in caplog.text
    assert "HassTurnOn" in caplog.text
    assert "Needle prediction:" in caplog.text
    assert "suppressed_calls" in caplog.text
    assert "Missing required argument" in caplog.text


async def test_tool_errors_are_logged_for_background_requests(setup_agent, caplog):
    entity, log, user_input, executed, api = setup_agent
    api.tools = [Tool(executed, fail=True)]
    with patch(
        "custom_components.needle.conversation.complete", return_value=prediction()
    ):
        await entity._async_handle_message(user_input, log)
    assert executed == ["Kitchen"]
    assert "Needle Assist tool returned an error: Light unavailable" in caplog.text


async def test_unknown_tool_preflight(setup_agent):
    _, _, _, _, api = setup_agent
    with pytest.raises(ValueError):
        _prepare_calls([{"name": "RunAnyService", "arguments": {}}], api)


def test_intent_error_speech_is_not_treated_as_success():
    speech, failed = _result_speech(
        {
            "response_type": "error",
            "speech": {"plain": {"speech": "No matching entity"}},
        }
    )
    assert failed
    assert speech == "No matching entity"

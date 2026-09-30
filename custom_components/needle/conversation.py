"""Expose Needle as a Home Assistant Assist conversation agent."""

import json
import logging
from typing import Literal

import voluptuous as vol
from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import intent, llm
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from probatio import to_openapi

from .const import CONF_MIN_CONFIDENCE, DEFAULT_MIN_CONFIDENCE, DOMAIN, MAX_CALLS
from .engine import RejectedCommand, complete, validate_response

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([NeedleConversationEntity(entry)])


def _prepare_calls(calls: list[dict], api: llm.APIInstance) -> list[llm.ToolInput]:
    """Reject unknown tools and bad schemas before executing any part of a batch."""
    tools = {tool.name: tool for tool in api.tools}
    prepared = []
    for call in calls:
        if (tool := tools.get(call["name"])) is None:
            raise RejectedCommand("That command is not available to this assistant.")
        try:
            args = tool.parameters(call["arguments"])
        except vol.Invalid as err:
            raise RejectedCommand("The command arguments were invalid.") from err
        prepared.append(llm.ToolInput(tool_name=tool.name, tool_args=args))
    return prepared


def _result_speech(result: dict) -> tuple[str, bool]:
    """Speak actual tool results rather than generating a success claim."""
    if result.get("error"):
        return str(result.get("error_text") or result["error"]), True
    speech = result.get("speech", {})
    if isinstance(speech, dict) and (plain := speech.get("plain")):
        return str(plain.get("speech", "")), result.get("response_type") == "error"
    if result.get("response_type") == "error":
        return "Home Assistant could not complete the command.", True
    # Context queries return structured state data, not an IntentResponse.
    return json.dumps(result, ensure_ascii=False, default=str), False


class NeedleConversationEntity(
    conversation.ConversationEntity, conversation.AbstractConversationAgent
):
    """One-shot local tool calling, executed through the built-in Assist API."""

    _attr_name = "Needle 3"
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._attr_unique_id = entry.entry_id

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

    async def async_will_remove_from_hass(self) -> None:
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        response = intent.IntentResponse(language=user_input.language)
        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                llm.LLM_API_ASSIST,
                "Interpret the user's home-control command using the available tools.",
                user_input.extra_system_prompt,
            )
            api = chat_log.llm_api
            if api is None or not api.tools:
                raise RejectedCommand("No home-control tools are available.")
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description or tool.name,
                    "parameters": to_openapi(
                        tool.parameters, custom_serializer=api.custom_serializer
                    ),
                }
                for tool in api.tools
            ]
            system = chat_log.content[0].content or ""
            output = await self.hass.async_add_executor_job(
                complete, user_input.text, tools, system
            )
            minimum = self.entry.options.get(
                CONF_MIN_CONFIDENCE,
                self.entry.data.get(CONF_MIN_CONFIDENCE, DEFAULT_MIN_CONFIDENCE),
            )
            calls = _prepare_calls(validate_response(output, minimum, MAX_CALLS), api)
            speeches = []
            failed = False
            # One call per chat-log message preserves model order even when a
            # later command targets the same entity as an earlier command.
            for call in calls:
                async for tool_result in chat_log.async_add_assistant_content(
                    conversation.AssistantContent(
                        agent_id=self.entity_id, tool_calls=[call]
                    )
                ):
                    speech, failed = _result_speech(tool_result.tool_result)
                    speeches.append(speech)
                if failed:
                    break
            text = " ".join(part for part in speeches if part) or "Command completed."
            if failed:
                response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, text)
            else:
                response.async_set_speech(text)
        except conversation.ConverseError as err:
            return err.as_conversation_result()
        except RejectedCommand as err:
            response.async_set_error(
                intent.IntentResponseErrorCode.NO_INTENT_MATCH, str(err)
            )
        except (HomeAssistantError, vol.Invalid) as err:
            _LOGGER.warning("Needle Assist tool failure: %s", err)
            response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                "Home Assistant could not complete the command.",
            )
        except Exception:
            _LOGGER.exception("Needle inference failed")
            response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                "Needle could not process the command. Check the integration logs.",
            )
        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(
                agent_id=self.entity_id,
                content=response.speech.get("plain", {}).get("speech", ""),
            )
        )
        return conversation.ConversationResult(
            response=response, conversation_id=chat_log.conversation_id
        )

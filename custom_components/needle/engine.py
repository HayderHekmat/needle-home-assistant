"""Serialize access to Needle's process-global native runtime."""

import math
import os
from threading import Lock
from typing import Any

_ENGINE_LOCK = Lock()


def _create_agent(tools: list[dict[str, Any]], system: str):
    # The SDK and its native engine both honor this switch.
    os.environ["NEEDLE_TELEMETRY"] = "0"
    from needle import Needle

    return Needle(tools=tools, system=system, generation=3)


def warm_up() -> None:
    """Download/load the native engine and official weights in an executor."""
    with _ENGINE_LOCK:
        with _create_agent([], ""):
            pass


def complete(text: str, tools: list[dict[str, Any]], system: str) -> dict[str, Any]:
    """Run one independent command without leaking context across users."""
    with _ENGINE_LOCK:
        with _create_agent(tools, system) as agent:
            agent.reset()
            return agent.complete(text)


class RejectedCommand(ValueError):
    """The model did not produce an actionable, trusted command."""


def validate_response(
    response: dict[str, Any], minimum_confidence: float, max_calls: int
) -> list[dict[str, Any]]:
    """Validate the entire envelope before any Home Assistant action runs."""
    if not isinstance(response, dict):
        raise RejectedCommand("Needle returned an invalid response.")
    if response.get("success") is False or response.get("error"):
        raise RejectedCommand("Needle could not complete that prediction.")
    if response.get("suppressed_calls"):
        raise RejectedCommand(
            "Some commands could not be verified. Please rephrase them."
        )
    confidence = response.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not minimum_confidence <= confidence <= 1
    ):
        raise RejectedCommand(
            "I could not understand that confidently. Please rephrase the command."
        )
    validation = response.get("validation") or {}
    if (
        not isinstance(validation, dict)
        or validation.get("ungrounded")
        or validation.get("negation")
    ):
        raise RejectedCommand("I could not verify that command. Please rephrase it.")
    calls = response.get("function_calls")
    if response.get("type") != "call" or not isinstance(calls, list) or not calls:
        raise RejectedCommand("I could not match that to a home-control command.")
    if len(calls) > max_calls:
        raise RejectedCommand("Please split that into fewer commands.")
    for call in calls:
        if (
            not isinstance(call, dict)
            or not isinstance(call.get("name"), str)
            or not isinstance(call.get("arguments"), dict)
        ):
            raise RejectedCommand("Needle returned an invalid tool call.")
    return calls

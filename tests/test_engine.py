"""Confidence and native-runtime lifecycle regression tests."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from custom_components.needle import engine


def envelope(**overrides):
    return {
        "type": "call",
        "confidence": 0.95,
        "function_calls": [{"name": "HassTurnOn", "arguments": {"name": "Kitchen"}}],
        **overrides,
    }


@pytest.mark.parametrize(
    "confidence", [None, False, -1, 0.79, 1.1, float("nan"), "0.9"]
)
def test_untrusted_confidence_rejected(confidence):
    with pytest.raises(engine.RejectedCommand):
        engine.validate_response(envelope(confidence=confidence), 0.8, 8)


@pytest.mark.parametrize(
    "overrides",
    [
        {"success": False},
        {"error": "inference failed"},
        {"suppressed_calls": [{"name": "HassTurnOn"}]},
        {"type": "text"},
        {"function_calls": []},
        {"function_calls": [{"name": "a", "arguments": "{}"}]},
        {"function_calls": [{"arguments": {}}]},
        {"validation": {"ungrounded": ["HassTurnOn.name"]}},
        {"validation": {"negation": True}},
        {"validation": "bad"},
        {"function_calls": [{"name": "a", "arguments": {}}] * 9},
    ],
)
def test_invalid_envelope_rejected(overrides):
    with pytest.raises(engine.RejectedCommand):
        engine.validate_response(envelope(**overrides), 0.8, 8)


def test_accepts_threshold_boundary():
    assert engine.validate_response(envelope(confidence=0.8), 0.8, 8)


def test_native_calls_are_serialized_and_closed(monkeypatch):
    active = 0
    peak = 0
    closed = []
    state_lock = threading.Lock()

    class Agent:
        def reset(self):
            pass

        def __enter__(self):
            nonlocal active, peak
            with state_lock:
                active += 1
                peak = max(active, peak)
            return self

        def complete(self, text):
            time.sleep(0.01)
            return envelope()

        def __exit__(self, *args):
            nonlocal active
            with state_lock:
                active -= 1
                closed.append(True)

    monkeypatch.setattr(engine, "_create_agent", lambda *args: Agent())
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: engine.complete("on", [], ""), range(4)))
    assert len(results) == len(closed) == 4
    assert peak == 1


def test_exception_closes_agent(monkeypatch):
    closed = []

    class Agent:
        def reset(self):
            pass

        def __enter__(self):
            return self

        def complete(self, text):
            raise RuntimeError("inference failed")

        def __exit__(self, *args):
            closed.append(True)

    monkeypatch.setattr(engine, "_create_agent", lambda *args: Agent())
    with pytest.raises(RuntimeError):
        engine.complete("on", [], "")
    assert closed == [True]

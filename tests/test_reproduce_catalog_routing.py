import json
import sys
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from scripts.reproduce_catalog_routing import (
    CASES,
    catalog_variant,
    run,
    synthetic_catalog,
)


def test_public_fixtures_are_fixed_and_contain_valid_synthetic_labels():
    tools = synthetic_catalog()
    assert len(tools) == len({t["name"] for t in tools}) == 25
    assert tools == synthetic_catalog()
    schemas = {t["name"]: t["parameters"] for t in tools}
    for tool in tools:
        Draft202012Validator.check_schema(tool["parameters"])
    for _, name, arguments in CASES:
        Draft202012Validator(schemas[name]).validate(arguments)
    serialized = json.dumps(tools)
    assert "vacuum_test" not in serialized
    assert "play_rooms" not in serialized
    assert "Main Light" not in json.dumps(CASES)


@pytest.mark.parametrize("name,size", [("five", 5), ("six", 6), ("full", 25)])
def test_variants_keep_target_tools(name, size):
    tools = catalog_variant(name)
    assert len(tools) == size
    assert {case[1] for case in CASES} <= {t["name"] for t in tools}


def test_reverse_only_changes_order():
    assert catalog_variant("reversed") == list(reversed(synthetic_catalog()))
    with pytest.raises(ValueError):
        catalog_variant("unknown")


def test_standalone_probe_never_passes_callbacks_and_resets(tmp_path, monkeypatch):
    events = []
    expected = {q: [{"name": name, "arguments": args}] for q, name, args in CASES}

    class FakeNeedle:
        def __init__(self, **kwargs):
            assert set(kwargs) == {"tools", "generation", "auto_date"}
            assert all(isinstance(tool, dict) for tool in kwargs["tools"])
            assert len(kwargs["tools"]) == 25

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("close")

        def reset(self):
            events.append("reset")

        def complete(self, query):
            assert events[-1] == "reset"
            events.append("complete")
            return {"function_calls": expected[query]}

    monkeypatch.setitem(sys.modules, "needle", SimpleNamespace(Needle=FakeNeedle))
    monkeypatch.setitem(
        sys.modules,
        "needle.agent.fetch",
        SimpleNamespace(engine_version=lambda _: "3.0.2"),
    )
    monkeypatch.setattr("scripts.reproduce_catalog_routing.version", lambda _: "3.0.6")
    monkeypatch.setenv("NEEDLE_TELEMETRY", "1")
    monkeypatch.setenv("DO_NOT_TRACK", "0")
    out = tmp_path / "report.json"
    report = run("full", out)
    assert events == ["reset", "complete"] * 3 + ["close"]
    assert all(row["exact"] for row in report["results"])
    assert report["synthetic_only"] is True
    assert len(report["metadata"]["catalog_sha256"]) == 64
    assert json.loads(out.read_text()) == report
    assert str(tmp_path) not in out.read_text()

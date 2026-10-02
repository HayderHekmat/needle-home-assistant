import copy
import json
import sys
from types import SimpleNamespace

import pytest

from scripts.diagnose_routing import ALIASES, run, variants


def catalog():
    names = list(ALIASES) + [f"extra_{i}" for i in range(8)]
    return [
        {"name": name, "description": "original", "parameters": {"type": "object"}}
        for name in names
    ]


def test_catalog_ablations_preserve_schemas_and_input():
    tools = catalog()
    original = copy.deepcopy(tools)
    groups = variants(tools)
    assert tools == original
    assert [len(groups[name]) for name in ("three", "five", "six")] == [3, 5, 6]
    assert groups["reversed"] == list(reversed(tools))
    for group in groups.values():
        assert len({t["name"] for t in group}) == len(group)
    for old, renamed in zip(tools, groups["readable_full"], strict=True):
        assert old["parameters"] == renamed["parameters"]
        assert old["description"] == renamed["description"]


@pytest.mark.parametrize("bad", [[], catalog()[:5], catalog() + [catalog()[0]]])
def test_diagnostic_requires_a_complete_unique_catalog(bad):
    with pytest.raises(ValueError):
        variants(bad)


def test_readable_variant_only_renames_the_three_control_tools():
    tools = catalog()
    renamed = variants(tools)["readable_full"]
    for old, new in zip(tools, renamed, strict=True):
        assert new["name"] == ALIASES.get(old["name"], old["name"])


def test_alias_collision_is_rejected():
    tools = catalog() + [{"name": "turn_on", "parameters": {"type": "object"}}]
    with pytest.raises(ValueError, match="collide"):
        variants(tools)


def test_probe_uses_only_schemas_resets_and_saves_every_prediction(
    tmp_path, monkeypatch
):
    events = []

    class FakeNeedle:
        def __init__(self, **kwargs):
            assert all(isinstance(tool, dict) for tool in kwargs["tools"])
            assert "tool_index_path" not in kwargs
            events.append("construct")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("close")

        def reset(self):
            events.append("reset")

        def complete(self, query):
            assert events[-1] == "reset"
            events.append("complete")
            return {"function_calls": [], "suppressed_calls": []}

    monkeypatch.setitem(sys.modules, "needle", SimpleNamespace(Needle=FakeNeedle))
    report = tmp_path / "nested" / "report.json"
    rows = run(catalog(), report)
    assert len(rows) == 18
    assert events.count("reset") == events.count("complete") == 18
    assert events.count("construct") == events.count("close") == 6
    assert json.loads(report.read_text()) == rows

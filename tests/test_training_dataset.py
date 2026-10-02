"""Dataset labels, benchmark protection and catalog order are deterministic."""

from collections import Counter

import pytest
from jsonschema import ValidationError

from scripts.training_dataset import (
    CLIMATE,
    CONTEXT,
    LIGHT,
    NEXT,
    OFF,
    ON,
    PAUSE,
    POSITION,
    PREVIOUS,
    RESUME,
    assign_tools,
    build_dataset,
    contamination,
    sample,
    tool_call,
    validate_labels,
)


def catalog():
    rows = []
    for name in (
        ON,
        OFF,
        LIGHT,
        NEXT,
        PREVIOUS,
        CLIMATE,
        POSITION,
        PAUSE,
        RESUME,
        CONTEXT,
    ):
        properties = {"name": {"type": "string"}}
        required = []
        if name == LIGHT:
            properties["brightness"] = {"type": "integer", "minimum": 0, "maximum": 100}
        if name == CLIMATE:
            properties["temperature"] = {"type": "number"}
            required = ["temperature"]
        if name == POSITION:
            properties["position"] = {"type": "integer", "minimum": 0, "maximum": 100}
            required = ["position"]
        rows.append(
            {
                "name": name,
                "description": name,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            }
        )
    return rows


@pytest.mark.parametrize(
    "query,blocked,reason",
    [
        ("Turn ON Main Light!", ["turn on main light"], "exact"),
        ("Please turn on Main Light", ["turn on main light"], "substring"),
        (
            "Could you please turn on the Bedroom Lamp",
            ["Could you please turn on the Study Lamp"],
            "trigram",
        ),
        ("Deactivate Hall Lamp", ["Would you switch off Study Lamp"], None),
    ],
)
def test_split_contamination_filters(query, blocked, reason):
    assert contamination(query, blocked) == reason


def test_dataset_balances_refusals_and_protects_all_test_queries():
    def measure(row):
        return len(row["tools"]) * 40 + 30

    first = build_dataset(catalog(), measure=measure)
    assert first == build_dataset(catalog(), measure=measure)
    train, focused, full, metadata = first
    assert len(train) == 160
    assert len(focused) == len(full) == 100
    assert sum(not row["answers"] for row in train) == 48
    assert {r["capability"] for r in train} == {r["capability"] for r in focused}
    depths = Counter(r["depth"] for r in train if not r["answers"])
    assert depths["missing_target"] and depths["negation"] and depths["out_of_bounds"]
    for row in train:
        assert not contamination(row["query"], [r["query"] for r in focused])
        validate_labels(row)
        assert all(tool in catalog() for tool in row["tools"])
    for compact, complete in zip(focused, full, strict=True):
        assert compact["id"] == complete["id"]
        assert compact["query"] == complete["query"]
        assert compact["answers"] == complete["answers"]
        assert complete["tools"] == catalog()
    assert metadata["tool_schemas_modified"] is False


def test_training_context_stays_two_tools_unless_scaled_up():
    def measure(row):
        return len(row["tools"]) * 40 + 30

    default_train = build_dataset(catalog(), measure=measure)[0]
    assert all(len(row["tools"]) <= 3 for row in default_train)

    scaled = build_dataset(
        catalog(),
        measure=measure,
        train_tools=5,
        distractor_pool=[tool["name"] for tool in catalog()],
    )[0]
    assert all(len(row["tools"]) == 5 for row in scaled)
    names = [tool["name"] for tool in catalog()]
    for row in scaled:
        selected = [tool["name"] for tool in row["tools"]]
        assert selected == [name for name in names if name in selected]
        for answer in row["answers"]:
            assert answer["name"] in selected
        validate_labels(row)


def test_tool_order_does_not_reveal_target():
    row = sample(
        "Turn off Main Light",
        [tool_call(OFF, name="Main Light")],
        "power",
        "imperative",
    )
    assigned = assign_tools(row, catalog(), measure=lambda _: 20, max_tokens=512)
    names = [t["name"] for t in assigned["tools"]]
    assert names == [t["name"] for t in catalog() if t["name"] in names]


def test_oversized_required_schema_is_rejected():
    row = sample(
        "Turn on Main Light", [tool_call(ON, name="Main Light")], "power", "imperative"
    )
    with pytest.raises(ValueError, match="Required schemas exceed"):
        assign_tools(row, catalog(), measure=lambda _: 600, max_tokens=512)


def test_labels_reject_unsupported_fields_and_missing_numeric_evidence():
    row = {
        "query": "Turn on Main Light",
        "tools": catalog(),
        "answers": [tool_call(ON, name="Main Light", invented="area")],
    }
    with pytest.raises(ValidationError, match="Additional properties"):
        validate_labels(row)
    row = {
        "query": "Set Kitchen Light brightness to 72 percent",
        "tools": catalog(),
        "answers": [tool_call(LIGHT, name="Kitchen Light", brightness=2)],
    }
    with pytest.raises(ValueError, match="numeric argument"):
        validate_labels(row)

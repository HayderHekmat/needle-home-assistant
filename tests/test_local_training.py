"""Offline training preparation never controls devices or trusts raw scores."""

import json
import sys
from argparse import Namespace
from types import SimpleNamespace

import pytest

from scripts.local_training import (
    FOCUS,
    assess,
    check_lengths,
    evaluate,
    make_examples,
    prepare,
    prepare_v3,
    read_tools,
    save_report,
    train,
)


def tools():
    return [{"name": name, "parameters": {"type": "object"}} for name in FOCUS]


def test_extract_log_schemas_without_context(tmp_path):
    path = tmp_path / "ha.log"
    path.write_text(
        f"DEBUG Needle request: text='test' tools={tools()!r} "
        "system=Private home context\n",
        encoding="utf-8",
    )
    assert read_tools(path) == tools()


def test_missing_catalog_is_rejected(tmp_path):
    path = tmp_path / "ha.log"
    path.write_text("Needle request: text='x' tools=[] system=x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="five focus tools"):
        read_tools(path)


def test_prepare_does_not_export_home_context(tmp_path):
    path = tmp_path / "ha.log"
    path.write_text(
        f"Needle request: text='test' tools={tools()!r} system=PRIVATE_HOME_STATE\n",
        encoding="utf-8",
    )
    out = tmp_path / "output"
    prepare(Namespace(log=path, out=out))
    assert {p.name for p in out.glob("*.jsonl")} == {
        "train.jsonl",
        "test.jsonl",
        "test-full-catalog.jsonl",
        "regression-full-catalog.jsonl",
    }
    for output in out.iterdir():
        assert "PRIVATE_HOME_STATE" not in output.read_text()
    regressions = [
        json.loads(line)
        for line in (out / "regression-full-catalog.jsonl").read_text().splitlines()
    ]
    assert [r["answers"][0]["name"] for r in regressions] == list(FOCUS[:2])


def test_prepare_v3_scales_tool_contexts_and_freezes_benchmark(tmp_path, monkeypatch):
    from tests.test_training_dataset import catalog

    monkeypatch.setitem(
        sys.modules,
        "needle.model.finetune",
        SimpleNamespace(render_example=lambda _: ("prompt", "target")),
    )
    monkeypatch.setitem(
        sys.modules,
        "needle.model.tokenizer",
        SimpleNamespace(
            get_tokenizer=lambda: SimpleNamespace(encode=lambda text: list(text))
        ),
    )
    tools_path = tmp_path / "tools.json"
    tools_path.write_text(json.dumps(catalog()), encoding="utf-8")
    protect = tmp_path / "test.jsonl"
    protect.write_text("", encoding="utf-8")
    out = tmp_path / "v3"
    prepare_v3(
        Namespace(
            tools=tools_path,
            protect=protect,
            out=out,
            count=160,
            max_tokens=1024,
            train_tools=5,
        )
    )
    assert {path.name for path in out.iterdir()} == {"train.jsonl", "dataset.json"}
    rows = [
        json.loads(line)
        for line in (out / "train.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 160
    names = [tool["name"] for tool in catalog()]
    for row in rows:
        assert len(row["tools"]) == 5
        selected = [tool["name"] for tool in row["tools"]]
        assert selected == [name for name in names if name in selected]
        for answer in row["answers"]:
            assert answer["name"] in selected
    metadata = json.loads((out / "dataset.json").read_text(encoding="utf-8"))
    assert metadata["train_tools_per_example"] == 5
    assert metadata["distractor_pool"] == "full catalog"


def test_token_limit_refuses_truncation(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "needle.model.finetune",
        SimpleNamespace(render_example=lambda _: ("prompt", "target")),
    )
    monkeypatch.setitem(
        sys.modules,
        "needle.model.tokenizer",
        SimpleNamespace(
            get_tokenizer=lambda: SimpleNamespace(encode=lambda text: list(text))
        ),
    )
    with pytest.raises(ValueError, match="refusing silent truncation"):
        check_lengths([{}], 13)
    check_lengths([{}], 14)


def test_training_worker_retains_validation_and_disables_redundant_score(
    tmp_path, monkeypatch
):
    data = tmp_path / "train.jsonl"
    data.write_text(
        "\n".join(json.dumps(r) for r in make_examples(tools())), encoding="utf-8"
    )
    commands = []
    monkeypatch.setattr("importlib.metadata.version", lambda _: "3.0.6")
    monkeypatch.setattr("scripts.local_training.check_lengths", lambda *args: None)
    monkeypatch.setattr(
        "scripts.local_training.subprocess.run",
        lambda command, **kwargs: commands.append((command, kwargs)),
    )
    train(
        Namespace(
            data=data,
            out=tmp_path / "model",
            epochs=1,
            batch_size=1,
            max_len=1024,
            sdk_score=False,
        )
    )
    settings = json.loads(commands[0][0][-1])
    assert settings["val_split"] == 0.1
    assert settings["score"] is False
    assert settings["generate"] == 0
    assert len(commands) == 2
    assert all(kwargs["check"] for _, kwargs in commands)
    assert all(kwargs["env"]["NEEDLE_TELEMETRY"] == "0" for _, kwargs in commands)
    assert "--upload" not in commands[1][0]


def test_starter_data_has_disjoint_queries_and_no_call_examples():
    train = make_examples(tools())
    test = make_examples(tools(), held_out=True)
    assert not {r["query"] for r in train} & {r["query"] for r in test}
    assert any(not r["answers"] for r in train)
    assert any(len(r["answers"]) == 2 for r in train)
    assert {c["name"] for r in train for c in r["answers"]} == set(FOCUS)
    for example in train + test:
        json.dumps(example)
        for c in example["answers"]:
            for value in c["arguments"].values():
                assert str(value) in example["query"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"suppressed_calls": [{"name": "wrong"}]},
        {"validation": {"ungrounded": ["name"]}},
        {"validation": {"negation": True}},
        {"error": "engine failed"},
        {"success": False},
        {"type": "text"},
        {"function_calls": [{"name": "wrong", "arguments": {}}]},
    ],
)
def test_evaluation_rejects_bad_predictions(overrides):
    expected = [{"name": FOCUS[0], "arguments": {"name": "Main Light"}}]
    response = {
        "type": "call",
        "function_calls": expected,
        "confidence": None,
        **overrides,
    }
    assert not assess(response, expected)


def test_missing_confidence_only_allowed_for_offline_comparison():
    expected = [{"name": FOCUS[0], "arguments": {"name": "Main Light"}}]
    assert assess(
        {"type": "call", "function_calls": expected, "confidence": None}, expected
    )
    assert assess({"function_calls": []}, [])


def test_evaluate_only_uses_schemas_and_writes_failed_results(tmp_path, monkeypatch):
    expected = [{"name": FOCUS[0], "arguments": {"name": "Main Light"}}]
    data = tmp_path / "test.jsonl"
    data.write_text(
        json.dumps(
            {"query": "Turn on Main Light", "tools": tools(), "answers": expected}
        ),
        encoding="utf-8",
    )
    report = tmp_path / "result.json"
    constructed = []

    class FakeNeedle:
        def __init__(self, **kwargs):
            constructed.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def reset(self):
            pass

        def complete(self, query):
            return {"type": "call", "function_calls": []}

    monkeypatch.setitem(sys.modules, "needle", SimpleNamespace(Needle=FakeNeedle))
    args = Namespace(data=data, weights=None, report=report, limit=0)
    assert evaluate(args) == 1
    assert constructed[0]["tools"] == tools()
    assert not json.loads(report.read_text())[0]["passed"]


def test_evaluator_reuses_only_identical_context_and_resets(tmp_path, monkeypatch):
    data = tmp_path / "test.jsonl"
    rows = [
        {"query": "first", "tools": tools(), "answers": []},
        {"query": "second", "tools": tools(), "answers": []},
        {"query": "third", "tools": tools(), "system": "different", "answers": []},
    ]
    data.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    instances = []

    class FakeNeedle:
        def __init__(self, **kwargs):
            self.events = []
            self.settings = kwargs
            instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def reset(self):
            self.events.append("reset")

        def complete(self, query):
            self.events.append(query)
            return {"function_calls": []}

    monkeypatch.setitem(sys.modules, "needle", SimpleNamespace(Needle=FakeNeedle))
    assert (
        evaluate(
            Namespace(data=data, weights=None, report=tmp_path / "report.json", limit=0)
        )
        == 0
    )
    assert len(instances) == 2
    assert instances[0].events == ["reset", "first", "reset", "second"]
    assert instances[1].events == ["reset", "third"]
    assert instances[1].settings["system"] == "different"


def test_report_retries_replace_and_preserves_previous_file(tmp_path, monkeypatch):
    from pathlib import Path

    report = tmp_path / "report.json"
    report.write_text("[]", encoding="utf-8")
    replace = Path.replace
    attempts = []

    def flaky_replace(path, target):
        attempts.append(path)
        if len(attempts) == 1:
            assert report.read_text() == "[]"
            raise OSError("temporary file lock")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr("scripts.local_training.time.sleep", lambda _: None)
    save_report(report, [{"passed": True}])
    assert json.loads(report.read_text()) == [{"passed": True}]
    assert len(attempts) == 2
    assert not report.with_suffix(".json.tmp").exists()

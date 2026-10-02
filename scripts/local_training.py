"""Prepare, train and evaluate Needle locally without executing device actions."""

import argparse
import ast
import json
import os
import random
import subprocess
import sys
import time
from itertools import groupby
from pathlib import Path

SDK_VERSION = "3.0.6"
FOCUS = (
    "intent__HassTurnOn",
    "intent__HassTurnOff",
    "light__HassLightSet",
    "media_player__HassMediaNext",
    "media_player__HassMediaPrevious",
)
TRAIN_NAMES = ("Main Light", "Kitchen Light", "Bedroom Lamp", "Hall Lamp")
TEST_NAMES = ("Office Lamp", "Guest Room Light")
MEDIA_NAMES = ("Living Room Speaker", "Kitchen Speaker")
TRAIN_PHRASES = ("Turn {state} {name}", "Please turn {state} {name}")
TEST_PHRASES = ("Could you turn {state} {name}", "Switch {name} {state}")
REFUSALS = (
    "Tell me a joke",
    "What is the capital of France?",
    "Write a poem",
    "Create a daily automation",
    "Tell me tomorrow's weather",
    "Explain quantum physics",
    "Do not turn on Main Light",
    "Do not turn off Main Light",
)


def read_tools(log_path: Path) -> list[dict]:
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if "Needle request:" in line and " tools=" in line:
            text = line.split(" tools=", 1)[1].split(" system=", 1)[0]
            tools = ast.literal_eval(text)
            if not isinstance(tools, list) or not all(
                isinstance(t, dict) for t in tools
            ):
                raise ValueError("The log does not contain a valid tool list")
            names = [t.get("name") for t in tools]
            if len(names) != len(set(names)) or not set(FOCUS).issubset(names):
                raise ValueError("The log needs all five focus tools with unique names")
            return tools
    raise ValueError("No debug-level Needle request with tool schemas found in the log")


def row(query, tools, answers, reasoning):
    return {"query": query, "tools": tools, "answers": answers, "reasoning": reasoning}


def call(tool_name, **arguments):
    return {"name": tool_name, "arguments": arguments}


def make_examples(tools, *, held_out=False):
    names = TEST_NAMES if held_out else TRAIN_NAMES
    phrases = TEST_PHRASES if held_out else TRAIN_PHRASES
    rows = []
    for name in names:
        for state, tool in (("on", FOCUS[0]), ("off", FOCUS[1])):
            for phrase in phrases:
                rows.append(
                    row(
                        phrase.format(state=state, name=name),
                        tools,
                        [call(tool, name=name)],
                        f"'{state}' selects {tool}; '{name}' is the name.",
                    )
                )
        for brightness in (35, 65) if held_out else (10, 25, 50, 75, 100):
            query = f"Set {name} brightness to {brightness} percent"
            rows.append(
                row(
                    query,
                    tools,
                    [call(FOCUS[2], name=name, brightness=brightness)],
                    f"'{name}' is the name; '{brightness}' is brightness.",
                )
            )
    for name in MEDIA_NAMES:
        for tool, action in ((FOCUS[3], "next"), (FOCUS[4], "previous")):
            query = (
                f"Play the {action} track on {name}"
                if held_out
                else f"Skip {name} to the {action} track"
            )
            rows.append(
                row(
                    query,
                    tools,
                    [call(tool, name=name)],
                    f"'{action}' selects {tool}; '{name}' is the name.",
                )
            )
    for first, second in zip(names, names[1:], strict=False):
        rows.append(
            row(
                f"Turn on {first} and turn off {second}",
                tools,
                [call(FOCUS[0], name=first), call(FOCUS[1], name=second)],
                f"'on {first}' selects on; 'off {second}' selects off, in order.",
            )
        )
    refusals = (
        ("Who wrote Hamlet?", "Do not turn on Office Lamp") if held_out else REFUSALS
    )
    for query in refusals:
        rows.append(
            row(query, tools, [], "No affirmative command for an available tool.")
        )
    random.Random(7).shuffle(rows)
    return rows


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=True) + "\n" for r in rows), encoding="utf-8"
    )


def prepare(args):
    tools = read_tools(args.log)
    focus = [next(t for t in tools if t["name"] == name) for name in FOCUS]
    args.out.mkdir(parents=True, exist_ok=True)
    train = make_examples(focus)
    test = make_examples(focus, held_out=True)
    write_jsonl(args.out / "train.jsonl", train)
    write_jsonl(args.out / "test.jsonl", test)
    write_jsonl(
        args.out / "test-full-catalog.jsonl", make_examples(tools, held_out=True)
    )
    regressions = [
        row(
            f"Turn {state} Main Light",
            tools,
            [call(tool, name="Main Light")],
            f"'{state}' selects {tool}; 'Main Light' is the name.",
        )
        for state, tool in (("on", FOCUS[0]), ("off", FOCUS[1]))
    ]
    write_jsonl(args.out / "regression-full-catalog.jsonl", regressions)
    (args.out / "tools.json").write_text(json.dumps(tools, indent=2), encoding="utf-8")
    print(
        f"Prepared {len(train)} training and {len(test)} held-out examples "
        f"in {args.out}"
    )
    print("Synthetic starter data: review labels, add real phrasings, then retrain.")
    print(
        "Training uses five tools; also evaluate test-full-catalog.jsonl "
        "before deployment."
    )


def read_rows(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_rows(args, *, train_tools, distractor_pool, write_benchmark):
    from needle.model.finetune import render_example
    from needle.model.tokenizer import get_tokenizer

    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    from scripts.training_dataset import build_dataset

    tokenizer = get_tokenizer()

    def measure(example):
        prompt, target = render_example(example)
        return len(tokenizer.encode(prompt)) + len(tokenizer.encode(target)) + 2

    catalog = json.loads(args.tools.read_text(encoding="utf-8"))
    blocked = [r["query"] for r in read_rows(args.protect)]
    regressions = args.protect.parent / "regression-full-catalog.jsonl"
    if regressions.exists():
        blocked.extend(r["query"] for r in read_rows(regressions))
    pool = (
        [t["name"] for t in catalog]
        if distractor_pool == "catalog"
        else distractor_pool
    )
    train_rows, focused, full, metadata = build_dataset(
        catalog,
        measure=measure,
        max_tokens=args.max_tokens,
        count=args.count,
        blocked=blocked,
        train_tools=train_tools,
        distractor_pool=pool,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    outputs = [("train", train_rows)]
    if write_benchmark:
        outputs += [("benchmark-focused", focused), ("benchmark-full", full)]
    for name, rows in outputs:
        write_jsonl(args.out / f"{name}.jsonl", rows)
    metadata["sources"] = [
        "https://docs.liquid.ai/examples/customize-models/home-assistant",
        "https://www.cactuscompute.com/blog/finetuning-needle",
    ]
    (args.out / "dataset.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


def prepare_v2(args):
    build_rows(args, train_tools=2, distractor_pool=None, write_benchmark=True)


def prepare_v3(args):
    build_rows(
        args,
        train_tools=args.train_tools,
        distractor_pool="catalog",
        write_benchmark=False,
    )
    metadata = json.loads((args.out / "dataset.json").read_text(encoding="utf-8"))
    print(
        f"Training contexts use up to {args.train_tools} tools; longest example is "
        f"{metadata['train_max_tokens']} tokens. Evaluate with the frozen "
        "training-output/v2/benchmark-*.jsonl files."
    )


def check_lengths(rows, max_len):
    from needle.model.finetune import render_example
    from needle.model.tokenizer import get_tokenizer

    tokenizer = get_tokenizer()
    lengths = []
    for example in rows:
        prompt, target = render_example(example)
        lengths.append(
            len(tokenizer.encode(prompt)) + len(tokenizer.encode(target)) + 2
        )
    longest = max(lengths)
    if longest > max_len:
        raise ValueError(
            f"Longest example is {longest} tokens; --max-len is {max_len}. "
            "Raise the limit; refusing silent truncation."
        )
    print(f"Longest training example: {longest} tokens", flush=True)


def train(args):
    from importlib.metadata import version

    if version("cactus-needle") != SDK_VERSION:
        raise ValueError(
            f"Use cactus-needle[train]=={SDK_VERSION} for compatible exports"
        )
    rows = read_rows(args.data)
    if len(rows) < 10 or not any(not r["answers"] for r in rows):
        raise ValueError("Provide at least ten examples including no-call examples")
    if args.epochs < 1 or args.batch_size < 1 or args.max_len < 1:
        raise ValueError("Epochs, batch size and token limit must be positive")
    check_lengths(rows, args.max_len)
    args.out.mkdir(parents=True, exist_ok=True)
    adapter = args.out / "adapter.safetensors"
    env = {**os.environ, "NEEDLE_TELEMETRY": "0", "PYTHONUNBUFFERED": "1"}
    # Native evaluation below avoids the slow token-by-token JAX scorer.
    settings = {
        "checkpoint": None,
        "jsonl_path": str(args.data),
        "generate": 0,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "max_len": args.max_len,
        "seed": 7,
        "val_split": 0.1,
        "lr": 1e-4,
        "lora_rank": 16,
        "lora_alpha": 32,
        "checkpoint_dir": str(args.out),
        "out": str(adapter),
        "score": args.sdk_score,
    }
    command = [
        sys.executable,
        "-c",
        "import json, sys; from argparse import Namespace; "
        "from needle.model.finetune import finetune_local; "
        "finetune_local(Namespace(**json.loads(sys.argv[1])))",
        json.dumps(settings),
    ]
    (args.out / "run.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    with (args.out / "train.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            command, check=True, env=env, stdout=log, stderr=subprocess.STDOUT
        )
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from needle.cli import main; main()",
            "build",
            "--lora",
            str(adapter),
            "--out",
            str(args.out / "tuned.cact"),
        ],
        check=True,
        env=env,
    )
    print("Export complete. This local model has no calibrated confidence score.")
    print("Use evaluate next; no model has been installed in Home Assistant.")


def assess(response, expected):
    validation = response.get("validation") or {}
    safe = (
        response.get("success") is not False
        and not response.get("error")
        and not response.get("suppressed_calls")
        and isinstance(validation, dict)
        and not validation.get("ungrounded")
        and not validation.get("negation")
    )
    calls = response.get("function_calls")
    exact = isinstance(calls, list) and calls == expected
    if expected:
        safe = safe and response.get("type") == "call"
    return bool(safe and exact)


def save_report(path, reports):
    payload = json.dumps(reports, indent=2)
    temporary = path.with_suffix(path.suffix + ".tmp")
    for attempt in range(5):
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(path)
            return
        except OSError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


def evaluate(args):
    from needle import Needle

    os.environ["NEEDLE_TELEMETRY"] = "0"
    rows = read_rows(args.data)
    if not rows or args.limit < 0:
        raise ValueError("Provide test examples and a non-negative limit")
    if args.limit:
        rows = rows[: args.limit]
    reports = []
    args.report.parent.mkdir(parents=True, exist_ok=True)

    def context_key(example):
        return (json.dumps(example["tools"], sort_keys=True), example.get("system", ""))

    for _, cohort in groupby(rows, key=context_key):
        cohort = list(cohort)
        # Reset every request; reuse loaded weights only for an identical context.
        with Needle(
            tools=cohort[0]["tools"],
            system=cohort[0].get("system", ""),
            weights=str(args.weights) if args.weights else None,
            tool_index_path=str(args.report.with_suffix(".tools.idx")),
            generation=3,
            auto_date=False,
        ) as agent:
            for example in cohort:
                agent.reset()
                result = agent.complete(example["query"])
                passed = assess(result, example["answers"])
                reports.append(
                    {
                        "query": example["query"],
                        "expected": example["answers"],
                        "passed": passed,
                        "prediction": result,
                        "capability": example.get("capability", "legacy"),
                        "id": example.get("id"),
                    }
                )
                save_report(args.report, reports)
                print(f"{'PASS' if passed else 'FAIL'}: {example['query']}", flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    save_report(args.report, reports)
    passed = sum(r["passed"] for r in reports)
    print(
        f"Exact predictions passing grounding checks: {passed}/{len(reports)}; "
        "no device actions executed."
    )
    print(
        "This is an offline experiment, not authorization to bypass confidence checks."
    )
    for capability in sorted({r["capability"] for r in reports}):
        group = [r for r in reports if r["capability"] == capability]
        print(f"{capability}: {sum(r['passed'] for r in group)}/{len(group)}")
    return 0 if passed == len(reports) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("training-output"))
    p.set_defaults(func=prepare)
    p = sub.add_parser("prepare-v2")
    p.add_argument("--tools", type=Path, default=Path("training-output/tools.json"))
    p.add_argument("--protect", type=Path, default=Path("training-output/test.jsonl"))
    p.add_argument("--out", type=Path, default=Path("training-output/v2"))
    p.add_argument("--count", type=int, default=160)
    p.add_argument("--max-tokens", type=int, default=512)
    p.set_defaults(func=prepare_v2)
    p = sub.add_parser("prepare-v3")
    p.add_argument("--tools", type=Path, default=Path("training-output/tools.json"))
    p.add_argument("--protect", type=Path, default=Path("training-output/test.jsonl"))
    p.add_argument("--out", type=Path, default=Path("training-output/v3"))
    p.add_argument("--count", type=int, default=160)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument(
        "--train-tools",
        type=int,
        default=5,
        help="Tool schemas per training example; benchmark files stay frozen",
    )
    p.set_defaults(func=prepare_v3)
    p = sub.add_parser("train")
    p.add_argument("--data", type=Path, default=Path("training-output/train.jsonl"))
    p.add_argument("--out", type=Path, default=Path("training-output/model"))
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--max-len", type=int, default=2048)
    p.add_argument(
        "--sdk-score",
        action="store_true",
        help="Also run the slow JAX exact-call scorer before export",
    )
    p.set_defaults(func=train)
    p = sub.add_parser("evaluate")
    p.add_argument("--data", type=Path, default=Path("training-output/test.jsonl"))
    p.add_argument("--weights", type=Path)
    p.add_argument(
        "--report", type=Path, default=Path("training-output/evaluation.json")
    )
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=evaluate)
    args = parser.parse_args()
    try:
        return args.func(args) or 0
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

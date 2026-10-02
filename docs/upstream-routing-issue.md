# Needle 3 selects unrelated tools with a 25-tool synthetic catalog; result changes with order

Posted as [cactus-compute/needle#166](https://github.com/cactus-compute/needle/issues/166)
on October 2, 2026; the reproducer was re-run that day with identical counts.
A [follow-up comment](https://github.com/cactus-compute/needle/issues/166#issuecomment-5962916988)
records the same four counts and identical wrong calls on engine 3.1.0.

## Summary

With official Needle 3 weights, three simple commands return the expected calls
with five or six tools. With a 25-tool synthetic catalog, all three instead return
unrelated media-player calls. Reversing the same 25 tools changes the result to
two correct calls and one unrelated todo-list call.

This is a tool-selection reliability report, not a demonstrated indexing or
retrieval bug. Could maintainers confirm the intended behavior and how to
inspect the native engine's retrieved subset and alias mapping?

## Environment

- `cactus-needle==3.0.6`, native engine 3.0.2.
- Windows AMD64, Python 3.12.10.
- Official weights; no adapter or custom checkpoint.
- One catalog per fresh Python process; `reset()` before each command.
- `auto_date=False`, no system text, no tool index cache.
- Only synthetic raw schemas; no Home Assistant dependency, callbacks or device actions.

## Observed Results

| Catalog | Exact calls |
| --- | --- |
| First five tools | 3/3 |
| First six tools | 3/3 |
| All 25 tools | 0/3 |
| Same 25 tools, reversed order | 2/3 |

With the original 25-tool order:

| Query | Expected tool | Returned tool | Confidence |
| --- | --- | --- | --- |
| Turn on Sample Lamp | intent__HassTurnOn | media_player__HassMediaUnpause | 0.1808 |
| Turn off Sample Lamp | intent__HassTurnOff | media_player__HassMediaUnpause | 0.1444 |
| Set Test Lamp brightness to 35 percent | light__HassLightSet | media_player__HassSetVolume | 0.1123 |

The returned calls contain the copied `name` argument, but select the wrong tool.
Reasoning text describes turning the lamp on/off or setting brightness.
In reversed order, the on command selected `todo__HassListRemoveItem` at 0.3964;
off and brightness matched the expected calls.

All results are prediction comparisons, not permission to execute low-confidence
calls. These simplified distractor schemas are deliberately synthetic and are
not claimed to implement full Home Assistant service semantics.

## Self-Contained Reproduction

Save the following as `reproduce_catalog_routing.py`. Install
`cactus-needle==3.0.6`; no training dependencies are needed. The first run may
download official engine/model files. Run each command in its own process:

```sh
python reproduce_catalog_routing.py --variant five
python reproduce_catalog_routing.py --variant six
python reproduce_catalog_routing.py --variant full
python reproduce_catalog_routing.py --variant reversed
```

The reports contain only the synthetic schemas, synthetic queries and
non-identifying platform/version metadata.

```python
"""Shareable Needle catalog probe built entirely from synthetic fixtures."""

import argparse
import hashlib
import json
import os
import platform
from importlib.metadata import version
from pathlib import Path

CASES = (
    ("Turn on Sample Lamp", "intent__HassTurnOn", {"name": "Sample Lamp"}),
    ("Turn off Sample Lamp", "intent__HassTurnOff", {"name": "Sample Lamp"}),
    (
        "Set Test Lamp brightness to 35 percent",
        "light__HassLightSet",
        {"name": "Test Lamp", "brightness": 35},
    ),
)


def synthetic_catalog():
    specs = [
        ("intent__HassTurnOn", "Turn on a named device"),
        ("intent__HassTurnOff", "Turn off a named device"),
        ("light__HassLightSet", "Set the brightness of a named light"),
        ("climate__HassClimateSetTemperature", "Set a thermostat temperature"),
        ("assist_satellite__HassBroadcast", "Broadcast a spoken message"),
        ("homeassistant__GetLiveContext", "Read the current state of devices"),
        ("llm__GetDateTime", "Read the current date and time"),
        ("media_player__HassMediaNext", "Play the next media track"),
        ("media_player__HassMediaPrevious", "Play the previous media track"),
        ("media_player__HassMediaPause", "Pause a media player"),
        ("media_player__HassMediaUnpause", "Resume a media player"),
        ("media_player__HassMediaPlayerMute", "Mute a media player"),
        ("media_player__HassMediaPlayerUnmute", "Unmute a media player"),
        ("media_player__HassSetVolume", "Set a media player's volume"),
        ("media_player__HassSetVolumeRelative", "Change a media player's volume"),
        ("media_player__HassMediaSearchAndPlay", "Search and play media"),
        ("intent__HassStopMoving", "Stop a moving cover"),
        ("intent__HassSetPosition", "Set a cover position"),
        ("intent__HassCancelAllTimers", "Cancel all timers"),
        ("todo__get_items", "Read tasks from a task list"),
        ("todo__HassListAddItem", "Add a task to a task list"),
        ("todo__HassListRemoveItem", "Remove a task from a task list"),
        ("todo__HassListCompleteItem", "Complete a task from a task list"),
        ("script__run_cleaning", "Run a synthetic cleaning script"),
        ("script__run_music", "Run a synthetic music script"),
    ]
    schemas = []
    for name, description in specs:
        properties = {"name": {"type": "string"}}
        required = ["name"]
        if name == "light__HassLightSet":
            properties["brightness"] = {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
            }
            required.append("brightness")
        schemas.append(
            {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            }
        )
    return schemas


def catalog_variant(name):
    tools = synthetic_catalog()
    if name == "five":
        return tools[:5]
    if name == "six":
        return tools[:6]
    if name == "full":
        return tools
    if name == "reversed":
        return list(reversed(tools))
    raise ValueError("Unknown catalog variant")


def run(variant, out):
    os.environ["NEEDLE_TELEMETRY"] = "0"
    os.environ["DO_NOT_TRACK"] = "1"
    from needle import Needle
    from needle.agent.fetch import engine_version

    tools = catalog_variant(variant)
    encoded = json.dumps(tools, sort_keys=True).encode("utf-8")
    report = {
        "synthetic_only": True,
        "metadata": {
            "sdk": version("cactus-needle"),
            "engine": engine_version(3),
            "python": platform.python_version(),
            "os": platform.system(),
            "architecture": platform.machine(),
            "variant": variant,
            "catalog_sha256": hashlib.sha256(encoded).hexdigest(),
        },
        "tools": tools,
        "results": [],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with Needle(tools=tools, generation=3, auto_date=False) as agent:
        for query, name, arguments in CASES:
            agent.reset()
            prediction = agent.complete(query)
            expected = [{"name": name, "arguments": arguments}]
            exact = (
                prediction.get("function_calls") == expected
                and not prediction.get("suppressed_calls")
                and not prediction.get("error")
            )
            report["results"].append(
                {
                    "query": query,
                    "expected": expected,
                    "exact": exact,
                    "prediction": prediction,
                }
            )
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"{variant}: {'EXACT' if exact else 'DIFF'}: {query}", flush=True)
    print("Synthetic fixtures only; no callbacks or device actions.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--variant", choices=("five", "six", "full", "reversed"), default="full"
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    out = args.out or Path("training-output/public-reproducer") / f"{args.variant}.json"
    run(args.variant, out)


if __name__ == "__main__":
    main()
```

## Questions

1. Is this behavior expected model accuracy degradation, or a known catalog-handling issue?
2. Can the actual retrieved tool subset and normalized aliases be inspected?
3. Is catalog-order dependence expected for these fixtures?
4. Is there a published runtime update to test against engine 3.0.2?

Related but different: [#34](https://github.com/cactus-compute/needle/issues/34)
uses an older checkpoint retrieval API;
[#61](https://github.com/cactus-compute/needle/issues/61) reports a Needle 2
routing evaluation. This reproduction uses the Needle 3 native public API.


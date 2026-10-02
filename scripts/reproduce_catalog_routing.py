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

"""Controlled, offline tool-catalog ablations; no Home Assistant connection."""

import argparse
import copy
import json
import os
from pathlib import Path

ALIASES = {
    "intent__HassTurnOn": "turn_on",
    "intent__HassTurnOff": "turn_off",
    "light__HassLightSet": "set_light",
}
CASES = (
    ("Turn on Main Light", "intent__HassTurnOn", {"name": "Main Light"}),
    ("Turn off Main Light", "intent__HassTurnOff", {"name": "Main Light"}),
    (
        "Set Study Lamp brightness to 35 percent",
        "light__HassLightSet",
        {"name": "Study Lamp", "brightness": 35},
    ),
)


def variants(catalog):
    names = [tool["name"] for tool in catalog]
    if len(names) != len(set(names)) or not set(ALIASES) <= set(names):
        raise ValueError("Catalog needs unique names and all three control tools")
    if len(catalog) < 6:
        raise ValueError("At least six tools are needed to test retrieval")
    core = [t for t in catalog if t["name"] in ALIASES]
    others = [t for t in catalog if t["name"] not in ALIASES]
    selections = {
        "three": core,
        "five": core + others[:2],
        "six": core + others[:3],
        "full": catalog,
        "reversed": list(reversed(catalog)),
    }
    readable = copy.deepcopy(catalog)
    for tool in readable:
        tool["name"] = ALIASES.get(tool["name"], tool["name"])
    if len({t["name"] for t in readable}) != len(readable):
        raise ValueError("Diagnostic aliases collide")
    selections["readable_full"] = readable
    return selections


def run(catalog, out, weights=None):
    os.environ["NEEDLE_TELEMETRY"] = "0"
    from needle import Needle

    out.parent.mkdir(parents=True, exist_ok=True)
    reports = []
    for variant, schemas in variants(catalog).items():
        # No index cache: this also excludes a stale cache as the mechanism.
        with Needle(
            tools=schemas,
            weights=str(weights) if weights else None,
            generation=3,
            auto_date=False,
        ) as agent:
            for query, original, arguments in CASES:
                agent.reset()
                response = agent.complete(query)
                name = ALIASES[original] if variant == "readable_full" else original
                expected = [{"name": name, "arguments": arguments}]
                calls = response.get("function_calls") or []
                selected = [call.get("name") for call in calls]
                held = [
                    call.get("name") for call in response.get("suppressed_calls") or []
                ]
                reports.append(
                    {
                        "variant": variant,
                        "query": query,
                        "expected": expected,
                        "exact": calls == expected
                        and not response.get("suppressed_calls")
                        and not response.get("error"),
                        "expected_tool_emitted": name in selected,
                        "expected_tool_suppressed": name in held,
                        "prediction": response,
                    }
                )
                out.write_text(json.dumps(reports, indent=2), encoding="utf-8")
                print(f"{variant}: {query}: calls={selected}, held={held}", flush=True)
    print("Diagnostic only: no device actions or integration changes.")
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tools", type=Path, default=Path("training-output/tools.json")
    )
    parser.add_argument("--weights", type=Path)
    parser.add_argument(
        "--out", type=Path, default=Path("training-output/routing/base.json")
    )
    args = parser.parse_args()
    run(json.loads(args.tools.read_text(encoding="utf-8")), args.out, args.weights)


if __name__ == "__main__":
    main()

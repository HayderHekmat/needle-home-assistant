"""Download Needle and verify a real prediction without controlling any devices."""

import argparse
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-libc-recovery", action="store_true")
    args = parser.parse_args()
    # Load the actual wrapper without importing HA, so Alpine can test only
    # the native runtime and SDK dependencies used by the integration.
    spec = importlib.util.spec_from_file_location(
        "needle_engine", ROOT / "custom_components/needle/engine.py"
    )
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    if args.test_libc_recovery:
        from needle.agent import fetch

        if not fetch._is_musl():
            raise RuntimeError("The libc recovery check requires a musl container")
        wrong_tag = fetch._platform_tag().replace("musllinux_1_2_", "manylinux2014_")
        # Reproduce the original misleading platform detection and cached
        # glibc library. The SDK must retry with musl after CDLL rejects it.
        with patch.object(fetch, "_platform_tag", return_value=wrong_tag):
            fetch.fetch_library(
                dest_dir=fetch.cache_dir(3), tag=wrong_tag, generation=3
            )
            print("Checking recovery from a misdetected platform and glibc cache.")
            engine.warm_up()
    else:
        engine.warm_up()
    tools = [
        {
            "name": "turn_on_light",
            "description": "Turn on a light by its room name.",
            "parameters": {
                "type": "object",
                "properties": {"room": {"type": "string", "enum": ["kitchen"]}},
                "required": ["room"],
            },
        }
    ]
    result = engine.complete("Turn on the kitchen light", tools, "Rooms: kitchen")
    print(json.dumps(result, indent=2))
    calls = engine.validate_response(result, 0.8, 8)
    assert calls == [{"name": "turn_on_light", "arguments": {"room": "kitchen"}}]
    print("Real Needle 3 inference passed; no Home Assistant actions executed.")


if __name__ == "__main__":
    main()

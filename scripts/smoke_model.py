"""Download Needle and verify a real prediction without controlling any devices."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.needle.engine import complete, validate_response  # noqa: E402


def main():
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
    result = complete("Turn on the kitchen light", tools, "Rooms: kitchen")
    print(json.dumps(result, indent=2))
    calls = validate_response(result, 0.8, 8)
    assert calls == [{"name": "turn_on_light", "arguments": {"room": "kitchen"}}]
    print("Real Needle 3 inference passed; no Home Assistant actions executed.")


if __name__ == "__main__":
    main()

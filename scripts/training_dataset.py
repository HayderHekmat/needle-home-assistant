"""Deterministic command labels and split protection for offline Needle training."""

import hashlib
import random
import re
from collections import Counter, defaultdict

ON = "intent__HassTurnOn"
OFF = "intent__HassTurnOff"
LIGHT = "light__HassLightSet"
CLIMATE = "climate__HassClimateSetTemperature"
NEXT = "media_player__HassMediaNext"
PREVIOUS = "media_player__HassMediaPrevious"
PAUSE = "media_player__HassMediaPause"
RESUME = "media_player__HassMediaUnpause"
POSITION = "intent__HassSetPosition"
CONTEXT = "homeassistant__GetLiveContext"
CORE = (ON, OFF, LIGHT, NEXT, PREVIOUS)

TRAIN_TARGETS = (
    "Main Light",
    "Kitchen Light",
    "Bedroom Lamp",
    "Hall Lamp",
    "Desk Fan",
    "Porch Switch",
    "Ceiling Lamp",
    "Reading Lamp",
)
TEST_TARGETS = ("Study Lamp", "Guest Ceiling", "Library Fan", "Attic Switch")
TRAIN_LIGHTS = ("Kitchen Light", "Bedroom Lamp", "Hall Lamp", "Reading Lamp")
TEST_LIGHTS = ("Study Lamp", "Guest Ceiling", "Library Lamp", "Attic Lamp")
TRAIN_MEDIA = ("Kitchen Speaker", "Living Room Speaker", "Den Player")
TEST_MEDIA = ("Patio Speaker", "Study Player")
PHRASINGS = ("imperative", "polite", "colloquial", "question")


def tool_call(tool_name, **arguments):
    return {"name": tool_name, "arguments": arguments}


def sample(query, answers, capability, phrasing, depth="literal"):
    arguments = [
        f"'{value}' -> {key}" for c in answers for key, value in c["arguments"].items()
    ]
    actions = {
        ON: "enable",
        OFF: "disable",
        LIGHT: "brightness",
        CLIMATE: "temperature",
        NEXT: "next track",
        PREVIOUS: "previous track",
        PAUSE: "pause",
        RESUME: "resume",
        POSITION: "position",
        CONTEXT: "current state",
    }
    reasoning = (
        ", then ".join(actions[c["name"]] for c in answers)
        + ": "
        + "; ".join(arguments)
        + "; no other fields requested."
        if answers
        else "No complete affirmative request supported by these tools."
    )
    return {
        "query": query,
        "answers": answers,
        "reasoning": reasoning,
        "capability": capability,
        "phrasing": phrasing,
        "depth": depth,
    }


def normalize(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def trigrams(text):
    words = normalize(text).split()
    return set(zip(words, words[1:], words[2:], strict=False))


def contamination(query, blocked):
    normalized = normalize(query)
    grams = trigrams(query)
    for other in blocked:
        other_normalized = normalize(other)
        if normalized == other_normalized:
            return "exact"
        if normalized in other_normalized or other_normalized in normalized:
            return "substring"
        other_grams = trigrams(other)
        denominator = min(len(grams), len(other_grams))
        if denominator and len(grams & other_grams) / denominator > 0.5:
            return "trigram"
    return None


def positive_candidates(*, benchmark=False):
    targets = TEST_TARGETS if benchmark else TRAIN_TARGETS
    media = TEST_MEDIA if benchmark else TRAIN_MEDIA
    on_forms = (
        (
            "Switch {name} on now",
            "Would you activate {name}",
            "Get {name} powered on",
            "Can {name} be enabled",
        )
        if benchmark
        else (
            "Turn on {name}",
            "Please enable {name}",
            "Activate {name} for me",
            "Could you power on {name}",
            "Enable {name}",
            "Please turn {name} on",
        )
    )
    off_forms = (
        (
            "Switch {name} off now",
            "Would you deactivate {name}",
            "Get {name} powered off",
            "Can {name} be disabled",
        )
        if benchmark
        else (
            "Turn off {name}",
            "Please disable {name}",
            "Deactivate {name} for me",
            "Could you power off {name}",
            "Disable {name}",
            "Please turn {name} off",
        )
    )
    for target in targets:
        for tool_name, forms in ((ON, on_forms), (OFF, off_forms)):
            for i, form in enumerate(forms):
                yield sample(
                    form.format(name=target),
                    [tool_call(tool_name, name=target)],
                    "power",
                    PHRASINGS[i % 4],
                    "semantic" if i > 1 else "literal",
                )
    brightness_values = (
        (0, 35, 65, 100) if benchmark else (0, 10, 20, 25, 40, 50, 75, 90, 100)
    )
    brightness_forms = (
        (
            "Adjust {name} brightness to {value} percent",
            "Can {name} have {value} percent brightness",
        )
        if benchmark
        else (
            "Set {name} brightness to {value} percent",
            "Please dim {name} to {value} percent",
            "Make {name} brightness {value} percent",
        )
    )
    for target in TEST_LIGHTS if benchmark else TRAIN_LIGHTS:
        for value in brightness_values:
            for i, form in enumerate(brightness_forms):
                yield sample(
                    form.format(name=target, value=value),
                    [tool_call(LIGHT, name=target, brightness=value)],
                    "brightness",
                    PHRASINGS[i % 4],
                    "boundary" if value in (0, 100) else "literal",
                )
    for name in media:
        for tool_name, action in (
            (NEXT, "next"),
            (PREVIOUS, "previous"),
            (PAUSE, "pause"),
            (RESUME, "resume"),
        ):
            if action in ("next", "previous"):
                forms = (
                    (
                        f"Move {name} to the {action} song",
                        f"Could you play the {action} track on {name}",
                    )
                    if benchmark
                    else (
                        f"Skip {name} to the {action} track",
                        f"Please play the {action} song on {name}",
                        f"On {name}, select the {action} track",
                    )
                )
            else:
                forms = (
                    (f"Would you {action} playback on {name}",)
                    if benchmark
                    else (
                        f"{action.title()} {name}",
                        f"Please {action} playback on {name}",
                        f"Can you {action} {name}",
                    )
                )
            for i, query in enumerate(forms):
                yield sample(
                    query,
                    [tool_call(tool_name, name=name)],
                    "media",
                    PHRASINGS[i % 4],
                    "semantic" if i else "literal",
                )
    climate_targets = (
        ("Study Thermostat", "Guest Thermostat")
        if benchmark
        else ("Bedroom Thermostat", "Kitchen Thermostat", "Den Thermostat")
    )
    temperatures = (17, 23) if benchmark else (16, 18, 19, 20, 21, 22, 24)
    for target in climate_targets:
        for value in temperatures:
            forms = (
                (f"Adjust {target} target temperature to {value}",)
                if benchmark
                else (
                    f"Set {target} temperature to {value}",
                    f"Please set {target} to {value} degrees",
                    f"Can {target} be set to {value} degrees",
                )
            )
            for i, query in enumerate(forms):
                yield sample(
                    query,
                    [tool_call(CLIMATE, name=target, temperature=value)],
                    "climate",
                    PHRASINGS[i % 4],
                )
    covers = (
        ("Study Blind", "Attic Shade")
        if benchmark
        else ("Bedroom Blind", "Kitchen Shade", "Den Blind")
    )
    positions = (0, 35, 100) if benchmark else (0, 10, 25, 50, 75, 90, 100)
    for target in covers:
        for value in positions:
            query = (
                f"Adjust {target} position to {value} percent"
                if benchmark
                else f"Set {target} position to {value} percent"
            )
            yield sample(
                query,
                [tool_call(POSITION, name=target, position=value)],
                "cover",
                "imperative",
                "boundary" if value in (0, 100) else "literal",
            )
    for first, second in zip(targets[:4], targets[1:4], strict=False):
        if benchmark:
            queries = (
                f"Activate {first}, then deactivate {second}",
                f"Can you enable {first} and disable {second}",
            )
        else:
            queries = (
                f"Turn on {first} and turn off {second}",
                f"Please enable {first} then disable {second}",
                f"Activate {first} and deactivate {second}",
            )
        for query in queries:
            yield sample(
                query,
                [tool_call(ON, name=first), tool_call(OFF, name=second)],
                "multi_tool",
                "imperative",
                "semantic",
            )
    for target in targets[:4]:
        query = (
            f"Would you tell me the current state of {target}"
            if benchmark
            else f"What is the current state of {target}"
        )
        yield sample(query, [tool_call(CONTEXT, name=target)], "state", "question")


def refusal_candidates(*, benchmark=False):
    target = "Study Lamp" if benchmark else "Main Light"
    templates = (
        (
            "missing_target",
            (
                "Turn it on",
                "Switch it off",
                "Set brightness to 50 percent",
                "Pause",
                "Resume",
                "Turn on",
                "Turn off",
                "Dim it to 30 percent",
            ),
        ),
        (
            "negation",
            (
                f"Do not turn on {target}",
                f"Do not turn off {target}",
                f"Don't enable {target}",
                f"Never deactivate {target}",
                f"Please do not activate {target}",
                f"Do not dim {target} to 20 percent",
            ),
        ),
        (
            "reported",
            (
                f'She said "turn on {target}"',
                f'I heard someone say "turn off {target}"',
                f'The text says "activate {target}"',
            ),
        ),
        (
            "unsupported",
            (
                "Create a new automation",
                "Write a poem",
                "Tell me a joke",
                "Delete all my integrations",
                "Download a movie",
                "Send an email",
                "Purchase a light bulb",
                "Generate a weekly schedule",
            ),
        ),
        (
            "missing_number",
            (
                f"Dim {target} a bit",
                "Make the thermostat warmer",
                "Set the blind to a position",
                f"Set {target} brightness",
            ),
        ),
        (
            "out_of_bounds",
            (
                f"Set {target} brightness to 101 percent",
                f"Set {target} brightness to -5 percent",
                f"Set {target} brightness to 200 percent",
                "Set Bedroom Blind position to 120 percent",
            ),
        ),
        (
            "delay",
            (f"Turn off {target} in 10 seconds", f"Turn on {target} after 20 seconds"),
        ),
    )
    if not benchmark:
        templates = (
            (
                "missing_target",
                (
                    "Power it up",
                    "Power it down",
                    "Deactivate that one",
                    "Activate it for me",
                    "Change its brightness to 40 percent",
                    "Set the thermostat",
                    "Stop playback",
                    "Enable the device",
                    "Disable that device",
                    "I want it activated",
                ),
            ),
            (
                "negation",
                tuple(
                    query
                    for name in TRAIN_TARGETS
                    for query in (
                        f"Do not power on {name}",
                        f"Don't switch {name} on",
                        f"Never power down {name}",
                        f"Do not deactivate {name}",
                        f"I do not want {name} turned on",
                        f"Please don't change {name}",
                    )
                ),
            ),
            (
                "reported",
                tuple(
                    query
                    for name in TRAIN_TARGETS
                    for query in (
                        f"Someone mentioned activating {name}; this is not a command",
                        f"The phrase 'disable {name}' was quoted, not requested",
                        f"A note quotes 'power on {name}'; no action was requested",
                    )
                ),
            ),
            (
                "unsupported",
                (
                    "Calculate my tax",
                    "Book a flight",
                    "Translate this paragraph",
                    "Compose an automation rule",
                    "Build an hourly automation",
                    "Tell a bedtime story",
                    "Install a new integration",
                    "Invent an automation with triggers and conditions",
                    "Order a replacement bulb",
                    "Summarize an article",
                ),
            ),
            (
                "missing_number",
                tuple(
                    query
                    for name in TRAIN_LIGHTS
                    for query in (
                        f"Make {name} dimmer",
                        f"Set {name} to a different brightness",
                        f"Change {name} brightness",
                    )
                )
                + (
                    "Change Den Thermostat target temperature",
                    "Move Hall Shade to a new position",
                ),
            ),
            (
                "out_of_bounds",
                tuple(
                    query
                    for name in TRAIN_LIGHTS
                    for query in (
                        f"Dim {name} to 125 percent",
                        f"Make {name} brightness -20 percent",
                        f"Adjust {name} to 250 percent brightness",
                    )
                ),
            ),
            (
                "delay",
                tuple(f"Enable {name} after 30 seconds" for name in TRAIN_TARGETS),
            ),
        )
    for depth, queries in templates:
        for query in queries:
            if benchmark and depth == "unsupported":
                query = "Could you " + query[0].lower() + query[1:]
            yield sample(query, [], "rejection", "imperative", depth)


def validate_labels(example):
    from jsonschema import Draft202012Validator

    schemas = {t["name"]: t["parameters"] for t in example["tools"]}
    for c in example["answers"]:
        if c["name"] not in schemas:
            raise ValueError(f"Unknown target tool {c['name']}")
        Draft202012Validator(schemas[c["name"]]).validate(c["arguments"])
        for value in c["arguments"].values():
            if isinstance(value, (int, float)):
                pattern = rf"(?<![\w.]){re.escape(str(value))}(?![\w.])"
                if not re.search(pattern, example["query"]):
                    raise ValueError("An expected numeric argument is not in the query")
            elif (
                not isinstance(value, str)
                or value.lower() not in example["query"].lower()
            ):
                raise ValueError("An expected argument is not evidenced in the query")


def assign_tools(
    example,
    catalog,
    *,
    measure,
    max_tokens,
    benchmark=False,
    train_tools=2,
    distractor_pool=None,
):
    by_name = {t["name"]: t for t in catalog}
    required = list(dict.fromkeys(c["name"] for c in example["answers"]))
    if not required:
        required = (
            [ON, OFF]
            if example["depth"] in ("negation", "reported", "missing_target", "delay")
            else [LIGHT, CLIMATE]
        )
    if not set(required).issubset(by_name):
        raise ValueError(f"Missing schemas: {set(required) - by_name.keys()}")
    result = {**example, "tools": [by_name[name] for name in required]}
    if not benchmark and measure(result) > max_tokens:
        raise ValueError(
            f"Required schemas exceed the {max_tokens} token training budget"
        )
    target = 5 if benchmark else train_tools
    if train_tools < 1:
        raise ValueError("Training tool count must be positive")
    candidates = (
        list(CORE)
        if benchmark
        else list(distractor_pool)
        if distractor_pool is not None
        else [OFF, ON, LIGHT, NEXT, PREVIOUS, CLIMATE, POSITION, PAUSE, RESUME]
    )
    if not benchmark:
        # Rotate distractors without changing any original schema or tool name.
        seed = int(hashlib.sha256(example["query"].encode()).hexdigest()[:8], 16)
        random.Random(seed).shuffle(candidates)
    for name in candidates:
        if name not in by_name or name in required:
            continue
        candidate = {**result, "tools": result["tools"] + [by_name[name]]}
        if benchmark or measure(candidate) <= max_tokens:
            result = candidate
            required.append(name)
            if len(required) >= target:
                break
    # Keep the original catalog order, not an order that reveals the target label.
    result["tools"] = [t for t in catalog if t["name"] in required]
    validate_labels(result)
    return result


def balanced_select(rows, count, seed=17):
    groups = defaultdict(list)
    for r in rows:
        key = r["capability"] + (
            ":" + r["depth"] if r["capability"] == "rejection" else ""
        )
        groups[key].append(r)
    rng = random.Random(seed)
    for group in groups.values():
        rng.shuffle(group)
    selected = []
    while groups and len(selected) < count:
        for key in list(sorted(groups)):
            selected.append(groups[key].pop())
            if not groups[key]:
                del groups[key]
            if len(selected) == count:
                break
    rng.shuffle(selected)
    return selected


def build_dataset(
    catalog,
    *,
    measure,
    max_tokens=512,
    count=160,
    blocked=(),
    train_tools=2,
    distractor_pool=None,
):
    if count < 40 or max_tokens < 1:
        raise ValueError("Use at least 40 examples and a positive token budget")
    raw_benchmark = list(positive_candidates(benchmark=True)) + list(
        refusal_candidates(benchmark=True)
    )
    benchmark = balanced_select(raw_benchmark, 100)
    protected = list(blocked) + [r["query"] for r in raw_benchmark]
    candidates = list(positive_candidates()) + list(refusal_candidates())
    seen, filtered, clean = set(), Counter(), []
    for example in candidates:
        key = normalize(example["query"])
        reason = (
            "duplicate" if key in seen else contamination(example["query"], protected)
        )
        if reason:
            filtered[reason] += 1
            continue
        seen.add(key)
        clean.append(
            assign_tools(
                example,
                catalog,
                measure=measure,
                max_tokens=max_tokens,
                train_tools=train_tools,
                distractor_pool=distractor_pool,
            )
        )
    refusal_count = round(count * 0.3)
    refusals = balanced_select([r for r in clean if not r["answers"]], refusal_count)
    if len(refusals) < refusal_count:
        raise ValueError(
            "Not enough uncontaminated refusal examples for the 30 percent quota"
        )
    train = (
        balanced_select([r for r in clean if r["answers"]], count - refusal_count)
        + refusals
    )
    random.Random(17).shuffle(train)
    if len(train) < count:
        raise ValueError(
            f"Only {len(train)} uncontaminated examples; requested {count}"
        )
    focused = [
        assign_tools(r, catalog, measure=measure, max_tokens=max_tokens, benchmark=True)
        for r in benchmark
    ]
    full = [{**r, "tools": catalog} for r in benchmark]
    for i, r in enumerate(focused):
        r["id"] = f"ha-v2-{i + 1:03d}"
        full[i]["id"] = r["id"]
        validate_labels(full[i])
    return (
        train,
        focused,
        full,
        {
            "train_examples": len(train),
            "benchmark_examples": len(focused),
            "candidate_examples": len(candidates),
            "filtered": dict(filtered),
            "train_capabilities": dict(Counter(r["capability"] for r in train)),
            "test_capabilities": dict(Counter(r["capability"] for r in focused)),
            "train_max_tokens": max(measure(r) for r in train),
            "train_tools_per_example": max(len(r["tools"]) for r in train),
            "distractor_pool": "full catalog" if distractor_pool else "fixed core",
            "seed": 17,
            "tool_schemas_modified": False,
            "generation": "deterministic templates; no external teacher or API",
        },
    )

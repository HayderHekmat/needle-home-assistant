# Full-catalog routing investigation

## Method

An offline probe runs Main Light on, Main Light off, and Study Lamp brightness
at 35 percent. It passes JSON schemas only, without callbacks, Home Assistant
access or device actions. Each request is reset. No index cache is used.
SDK: 3.0.6; native engine: 3.0.2; host: Windows x86-64.

Smaller catalogs deliberately include the three expected tools. This is a
controlled diagnosis, not held-out accuracy. Schemas and descriptions stay
unchanged; the simpler-name variant renames only the three target tools.

## Results

Counts require exact arguments, no suppressed calls and no reported error.
They are not authorization to act or a substitute for confidence/grounding gates.

| Catalog | Official exact calls | Four-epoch export exact calls |
| --- | --- | --- |
| Three tools | 3/3 | 3/3 |
| Five tools | 3/3 | 3/3 |
| Six tools | 3/3 | 2/3 |
| Full catalog, 25 tools | 0/3 | 0/3 |
| Full catalog, reversed order | 0/3 | 2/3 |
| Full catalog, simpler target names | 1/3 | 0/3 |

Successful official small-catalog calls had confidence approximately 0.44-0.62,
below the integration's default 0.8 threshold. Local exports have no calibrated
confidence. Neither result justifies lowering or bypassing the checks.

Full-catalog power requests produced unrelated media-player calls. Reversing
catalog order changed incorrect selections. Simpler names did not fix on/off.
The original-name variants reproduced their results in a second probe.

A separate public `agent.embed()` cosine ranking of compact JSON schemas put
both power tools in the top two for "Turn on Main Light". Inference on its
manually selected five-tool subset returned the expected call at confidence
0.4418. This is only a **proxy**: the native retrieval input, normalization and
actual subset are not exposed by the public SDK.

## Conclusion And Limits

Full-catalog handling is a reproducible failure condition with official and
tuned weights. Stale cache and fine-tuning alone cannot explain it. A third run
trained on five-tool contexts, the documented retrieval subset size, reached
13/100 on the full benchmark against the official 24, so training-context size
is not the cause either. The exact cause remains unresolved: retrieval and
internal name mapping cannot yet be separated. Order sensitivity alone does not
prove an indexing bug.

The [SDK documentation](https://cactuscompute.com/blog/needle-python-docs)
describes five-tool retrieval and runtime snake-case aliases. The installed
trainer's `render_example()` instead serializes supplied names unchanged.
That potential training mismatch has not been isolated by paired training and
does not explain the official-model failure on its own.

As checked October 1, 2026, the
[upstream fetch configuration](https://github.com/cactus-compute/needle/blob/main/needle/agent/fetch.py)
named engine 3.0.3 while published SDK 3.0.6 pinned 3.0.2, and the official
`Cactus-Compute/needle3` repository listed no 3.0.3 wheels. Cactus then published
`cactus-needle` 3.1.0 with engine 3.1.0 on October 2, 2026. The reproducer ran
unchanged in a separate environment on SDK 3.1.0 / engine 3.1.0 and produced the
same four counts: five and six tools 3/3, full 0/3, reversed 2/3. The wrong calls
and their confidences were identical to engine 3.0.2, byte for byte. A published
engine update therefore does not correct full-catalog handling.

## Reproduce

```powershell
.venv-training/Scripts/python.exe scripts/diagnose_routing.py --out training-output/routing/base-controlled.json
.venv-training/Scripts/python.exe scripts/diagnose_routing.py --weights training-output/v2/model/tuned.cact --out training-output/routing/tuned-controlled.json
```

Use the tool catalog extracted by the training workflow. Reports remain in the
ignored `training-output/` directory. Catalogs can contain private script names
and descriptions; review them before sharing. The earlier exploratory
`base.json` renamed distractors too and is excluded from the table above.

The sanitized reproduction below replaced the first option: it is posted
upstream as [cactus-compute/needle#166](https://github.com/cactus-compute/needle/issues/166),
so the next input is maintainer guidance on inspecting the retrieved subset and
alias mapping, or a tested published engine update that exposes or corrects
full-catalog handling. A reduced tool surface also needs a benchmark that does
not select tools from expected answers. This probe made no production changes,
deployment or additional training run.

## Synthetic Upstream Reproduction

The standalone `scripts/reproduce_catalog_routing.py` now reproduces the failure
without reading any Home Assistant catalog or logs. It creates 25 fixed synthetic
schemas and uses Sample Lamp/Test Lamp commands. Each CLI invocation is a fresh
process. These are simplified test schemas, not full Assist implementations.

On SDK 3.0.6 / engine 3.0.2, five and six tools each produced 3/3 exact calls,
the full 25 produced 0/3, and reversed order produced 2/3. Full-catalog power
commands selected media-unpause and brightness selected set-volume. A repeated
full-catalog run also produced 0/3. No tool callbacks or device actions ran.

```powershell
.venv-training/Scripts/python.exe scripts/reproduce_catalog_routing.py --variant five
.venv-training/Scripts/python.exe scripts/reproduce_catalog_routing.py --variant six
.venv-training/Scripts/python.exe scripts/reproduce_catalog_routing.py --variant full
.venv-training/Scripts/python.exe scripts/reproduce_catalog_routing.py --variant reversed
```

Synthetic reports are under `training-output/public-reproducer/`. The
[upstream issue](upstream-routing-issue.md) includes the complete standalone
source and observed results. It was re-verified on October 2, 2026 with the same
counts and posted as
[cactus-compute/needle#166](https://github.com/cactus-compute/needle/issues/166).

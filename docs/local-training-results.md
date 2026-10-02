# Local training results

This pilot verifies the training and export pipeline, not a fix for the
integration's model-routing failures. **Do not deploy this pilot model.**

## Configuration

- Windows x86-64, 16 GB RAM, CPU backend; Intel Iris Xe was not used for training.
- Python 3.12.10, cactus-needle 3.0.6, JAX/jaxlib 0.11.2, Flax 0.12.10,
  Optax 0.2.8.
- 51 synthetic examples using five original Assist tool schemas; seed 7.
- One epoch, batch size 2, LoRA rank 16, alpha 32, learning rate 0.0001.
- Five examples in the SDK validation split. Longest complete example: 817
  tokens; training padded to 1024, without truncation.
- Export: 20 layers, W4A8, 63,437,076 bytes. The confidence head is absent.

The SDK's final training-batch loss was 0.5142, validation loss 0.6290, and
JAX validation exact-call score 3/5. The initial command also ran the SDK's slow
JAX generation scorer before saving. The project wrapper now disables that
redundant scorer by default and retains validation loss plus separate native
evaluation. Training and SDK scoring took about 27 minutes on this host.

## Native results

| Test | Official base model | One-epoch local pilot |
| --- | --- | --- |
| Focused catalog, 19 held-out commands | 11/19 | 4/19 |
| Full catalog, Main Light on/off regression | 0/2 | 0/2 |

These are strict exact-call scores with grounding/error checks, not device-control
success rates. All comparisons were offline. Confidence was recorded but not
used to score predictions. No Home Assistant services or devices were called.
The full home-state context was not supplied, so these are not a reproduction
of every part of the live Assist request. The two Main Light regression queries
use a training name and are not held-out examples.

The pilot added incorrect arguments on some requests, including `domain: ["lock"]`
for an Office Lamp command. With the full catalog, the on command selected a
media-player tool and the off command exhausted its token budget. The original
reported problem is therefore not fixed by this pilot.

This is a small, undertrained experiment. Its results do not establish that local
fine-tuning cannot work, or that more epochs alone will fix the errors. Improve
the reviewed examples and tool coverage, then compare longer runs against the
same held-out and full-catalog tests. A locally tuned model also needs an explicit
safety policy for its missing confidence score before device control is enabled.
The integration's existing rejection of missing confidence remains unchanged.

## Local artifacts

- `training-output/pilot/adapter.safetensors`
- `training-output/pilot/tuned.cact`
- `training-output/base-focused.json`
- `training-output/base-regression.json`
- `training-output/pilot-focused.json`
- `training-output/pilot-regression.json`

Artifacts, logs, tool descriptions, and datasets stay local and are excluded from
Git. See [the workflow](local-training.md) for preparing and evaluating new runs.

## Broader local experiment

The second experiment uses the same SDK and CPU host, with 160 template-generated
examples across eight categories. There are 48 refusal examples. All labels are
checked against the original Assist schemas and copied argument spans; complete
rendered samples fit within 512 tokens. The training configuration is four
epochs, batch size 2, rank 16, alpha 32, learning rate 0.0001 and seed 7.
The SDK holds out 16 training examples for validation loss.

Training took about 80 minutes on this CPU host. Validation losses after each
epoch were 0.8223, 0.5688, 0.4678 and 0.4542. The final training-batch loss was
1.3854; this is not an epoch average. Native export succeeded: 20 layers, W4A8,
63,437,076 bytes, with no confidence head. Its SHA-256 is
`3F839A3694536C36D5B409BD6F0A03205511D3FE392126D83670E69B4582962B`.

A separate, frozen 100-task benchmark uses different names and phrasing.
Training candidates matching benchmark prompts exactly, by substring or by high
trigram overlap are excluded. The older held-out and Main Light regression
prompts are also protected. This remains a small synthetic benchmark with no
independent teacher review or live home-state context.

The focused benchmark deliberately includes each expected tool among at most
five schemas. The full variant uses all 25 original tools. A focused improvement
alone cannot demonstrate that full-catalog routing is fixed.

| Category | Tasks | Official, focused | Tuned, focused | Official, full | Tuned, full |
| --- | --- | --- | --- | --- | --- |
| Power | 16 | 1 | 2 | 0 | 0 |
| Brightness | 17 | 17 | 17 | 12 | 0 |
| Temperature | 4 | 4 | 4 | 4 | 0 |
| Media | 12 | 9 | 4 | 4 | 7 |
| Covers | 6 | 4 | 2 | 0 | 0 |
| Multiple tools | 6 | 0 | 0 | 0 | 1 |
| State queries | 4 | 4 | 4 | 4 | 0 |
| Refusals | 35 | 3 | 9 | 0 | 3 |
| Total | 100 | 42 | 42 | 24 | 11 |

Scores require exact calls plus grounding/error checks. A refusal with an
incorrect suppressed call fails this strict prediction test even though runtime
guards prevented execution. These are not live device-control success rates.
Benchmark reports are under `training-output/v2/` and stay local.

The older 19-command focused set scored 11/19 for the official model, 4/19 for
the first pilot and 8/19 for this run. The official result was rerun with the
updated evaluator and matched its original score. The full-catalog Main Light
regressions remain 0/2 for the new export.

**Do not deploy this export.** Lower validation loss did not translate into
better overall native accuracy. Refusal coverage improved in the focused test,
but other categories regressed, and full-catalog accuracy fell. Predictions
still added unrequested fields or selected unrelated tools. The cause is not
established by this experiment; adding epochs alone is not a demonstrated fix.

The next investigation should use reviewed examples matching actual runtime
tool subsets and home context, and separately check retrieval/tool mapping.
Neither this run nor the pilot adds automation creation or resolves the missing
confidence policy. Home Assistant still uses the official model and unchanged
safety checks. No artifacts were published and no device actions ran.

New artifacts include `model/adapter.safetensors`, `model/tuned.cact`,
`model/run.json`, `model/train.log`, `base-focused.json`, `base-full.json`,
`tuned-focused.json`, `tuned-full.json`, `legacy-focused.json` and
`regression.json`, all beneath `training-output/v2/`.

## Third Experiment: Runtime-Shaped Tool Contexts

The second dataset gave each training example only two or three tool schemas
while evaluation passed five or twenty-five. The third dataset changes that one
variable: every training example carries five schemas, and the four distractors
are drawn from the complete 25-tool catalog instead of a fixed core list. The
100-task benchmark and its focused and full variants are unchanged, so all three
runs remain comparable. There are again 160 training examples with 48 refusal
examples; the longest rendered example is 894 tokens.

Training used four epochs, batch size 2, rank 16, alpha 32, learning rate
0.0001, seed 7 and a token cap of 1024. It took about two hours and ten minutes
on this CPU host. Validation losses after each epoch were 0.8554, 0.5999, 0.4969
and 0.4814. Native export succeeded: 20 layers, W4A8, 63,437,076 bytes, with no
confidence head.

| Category | Tasks | Official, focused | Second run, focused | Third run, focused |
| --- | --- | --- | --- | --- |
| Power | 16 | 1 | 2 | 3 |
| Brightness | 17 | 17 | 17 | 17 |
| Temperature | 4 | 4 | 4 | 4 |
| Media | 12 | 9 | 4 | 4 |
| Covers | 6 | 4 | 2 | 3 |
| Multiple tools | 6 | 0 | 0 | 0 |
| State queries | 4 | 4 | 4 | 4 |
| Refusals | 35 | 3 | 9 | 9 |
| Total | 100 | 42 | 42 | 44 |

| Category | Tasks | Official, full | Second run, full | Third run, full |
| --- | --- | --- | --- | --- |
| Power | 16 | 0 | 0 | 0 |
| Brightness | 17 | 12 | 0 | 2 |
| Temperature | 4 | 4 | 0 | 0 |
| Media | 12 | 4 | 7 | 7 |
| Covers | 6 | 0 | 0 | 0 |
| Multiple tools | 6 | 0 | 1 | 1 |
| State queries | 4 | 4 | 0 | 0 |
| Refusals | 35 | 0 | 3 | 3 |
| Total | 100 | 24 | 11 | 13 |

The older 19-command focused set scored 9/19 for this export, against 11/19 for
the official model and 8/19 for the second run. The full-catalog Main Light
regressions remain 0/2.

Matching the training context to the five-tool subset produced a small focused
gain, 44 against 42 for both earlier models, carried by power and covers while
refusals held at the second run's level. Media on the focused set stayed below
the official result. Full-catalog accuracy recovered only from 11 to 13 and
remains below the official 24, and lower validation loss again did not predict
better native accuracy.

**Do not deploy this export.** It has no calibrated confidence score, it is
still below the official model overall, and its predictions remain
indistinguishable from the earlier runs in the failure modes the routing
investigation describes. Together the three runs show that dataset size,
epoch count and training-context size do not resolve the full-catalog failure
condition; that condition reproduces with official weights. Home Assistant
continues to use the official model with unchanged safety checks.

New artifacts are `model/adapter.safetensors`, `model/tuned.cact`,
`model/run.json`, `model/train.log`, `tuned-focused.json`, `tuned-full.json`,
`legacy-focused.json` and `regression.json`, all beneath `training-output/v3/`.
The frozen benchmark files remain those under `training-output/v2/`.

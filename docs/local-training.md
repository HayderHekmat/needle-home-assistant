# Local Needle training for Home Assistant

This is an offline experiment. It prepares synthetic examples using the actual
Assist tool schemas from a Needle debug log, trains a LoRA adapter with Cactus's
SDK, exports a `.cact` file, and checks predictions without calling any devices.
It needs no Cactus or OpenRouter API key. Initial checkpoint/tokenizer downloads
need internet access; training runs on this computer.

The integration does not yet load custom weights. Local fine-tunes have no
calibrated confidence score, so they cannot pass its existing confidence checks.
Those checks remain unchanged. Do not replace production weights or bypass the
checks merely because an offline test passes.

The [initial one-epoch pilot](local-training-results.md) exported successfully
but performed worse than the base model and did not fix the Main Light failures.
It is not ready for device control.

The broader four-epoch run also remains unsuitable for deployment: its focused
score matched the official model, while its full-catalog score dropped from
24/100 to 11/100. The third run trained on five-tool contexts and reached 44/100
focused and 13/100 full, still below the official model. The results document
records all three experiments.

The [routing investigation](routing-investigation.md) isolates a reproducible
full-catalog failure condition with both official and locally trained weights.
Check that evidence before investing in another training run.

## Install the separate training environment

Run these commands from the project directory in PowerShell:

```powershell
uv venv --python 3.12 .venv-training
uv pip install --python .venv-training/Scripts/python.exe -r scripts/training-requirements.txt
```

The training environment is separate from Home Assistant's Python dependencies.
CPU training works on this Windows host. An Intel integrated GPU is not the
NVIDIA CUDA or Apple Metal backend described by Cactus. No GPU acceleration is
enabled by these commands.

## Prepare examples

Enable Needle debug logging, send a command, and download the Home Assistant
log. A `Needle request` entry must contain the tool schemas.

```powershell
.venv-training/Scripts/python.exe scripts/local_training.py prepare --log "C:/path/to/home-assistant.log"
```

Generated files go under `training-output/`, which is excluded from Git along
with checkpoints and the training environment. Keep these files private; tool
descriptions can contain your script names. The full home-state context is not
exported. Review the files before sharing or publishing anything.

The starter set covers on/off, brightness, next/previous media tracks,
two-command requests, off-topic requests, and negated commands. It copies five
tool schemas without renaming or simplifying their arguments. It uses synthetic
entity names, not a record of actual device actions. Held-out names and phrasings
are separate from training. Broader tools, aliases, languages, risky actions and
real home contexts need additional reviewed examples.

## Train and export

### Prepare the broader benchmark first

After extracting the tool catalog, prepare the second dataset:

```powershell
.venv-training/Scripts/python.exe scripts/local_training.py prepare-v2
```

This creates 160 training examples and 100 benchmark tasks under
`training-output/v2/`. Training includes 48 no-call examples. Tasks cover power,
brightness, temperature, media, covers, multiple tool calls, state queries and
refusals. Labels are validated against the original JSON schemas. Exact,
substring and high trigram-overlap matches to benchmark prompts are excluded
from training. Keep the benchmark fixed while comparing models.

The method borrows taxonomy, refusal coverage and contamination checks from
[Liquid AI's Home Assistant example](https://docs.liquid.ai/examples/customize-models/home-assistant).
It does not use their model, cloud training or teacher service. These examples
are deterministic templates, not independently reviewed real household requests.

### Prepare runtime-shaped tool contexts

The second dataset gave each training example only two or three tool schemas,
while evaluation passes five or twenty-five. The third dataset changes that one
variable: every training example carries five schemas, and the four distractors
are drawn from the complete Assist catalog instead of a fixed core list. The
benchmark files are not regenerated, so both runs stay comparable.

```powershell
.venv-training/Scripts/python.exe scripts/local_training.py prepare-v3
```

Output goes to `training-output/v3/train.jsonl` with metadata in
`training-output/v3/dataset.json`. Evaluation keeps using
`training-output/v2/benchmark-focused.jsonl` and `benchmark-full.jsonl`.
Five-schema examples are longer, so training needs `--max-len 1024`:

```powershell
.venv-training/Scripts/python.exe scripts/local_training.py train --data training-output/v3/train.jsonl --out training-output/v3/model --epochs 4 --batch-size 2 --max-len 1024
.venv-training/Scripts/python.exe scripts/local_training.py evaluate --data training-output/v2/benchmark-focused.jsonl --weights training-output/v3/model/tuned.cact --report training-output/v3/tuned-focused.json
.venv-training/Scripts/python.exe scripts/local_training.py evaluate --data training-output/v2/benchmark-full.jsonl --weights training-output/v3/model/tuned.cact --report training-output/v3/tuned-full.json
```

For the shorter CPU experiment:

```powershell
.venv-training/Scripts/python.exe scripts/local_training.py train --data training-output/v2/train.jsonl --out training-output/v2/model --epochs 4 --batch-size 2 --max-len 512
```

Settings and training output are saved as `run.json` and `train.log` in the
chosen output directory. The complete rendered training samples must fit the
token cap; tool schemas are not shortened to make them fit.

```powershell
.venv-training/Scripts/python.exe scripts/local_training.py train
```

Defaults: 10 epochs, batch size 2, token cap 2048, seed 7, and a 10 percent
validation split. The script checks complete rendered token lengths before
training and refuses silent truncation. Output files are
`training-output/model/adapter.safetensors` and
`training-output/model/tuned.cact`. CPU training may take a long time. An initial
pipeline check can use `--epochs 1`; that is not adequate evidence of model quality.

The wrapper uses the pinned SDK's training function in a separate process. It
retains validation-loss checks but disables the SDK's slow JAX exact-call scoring
by default; that scorer repeatedly evaluates the full prompt on CPU before saving
the adapter. Use the native evaluator below instead, or pass `--sdk-score` to run
both. This changes evaluation scheduling, not the LoRA training objective.

Watch the validation loss, not just training loss. If validation loss rises while
training loss falls, use an earlier run or improve the dataset rather than blindly
adding epochs. The SDK saves its final adapter; it does not automatically select
the epoch with the best validation loss. Keep separate output directories when
comparing runs.

## Compare without device actions

For the second dataset, run both catalog variants for both models:

```powershell
.venv-training/Scripts/python.exe scripts/local_training.py evaluate --data training-output/v2/benchmark-focused.jsonl --report training-output/v2/base-focused.json
.venv-training/Scripts/python.exe scripts/local_training.py evaluate --data training-output/v2/benchmark-full.jsonl --report training-output/v2/base-full.json
.venv-training/Scripts/python.exe scripts/local_training.py evaluate --data training-output/v2/benchmark-focused.jsonl --weights training-output/v2/model/tuned.cact --report training-output/v2/tuned-focused.json
.venv-training/Scripts/python.exe scripts/local_training.py evaluate --data training-output/v2/benchmark-full.jsonl --weights training-output/v2/model/tuned.cact --report training-output/v2/tuned-full.json
```

The focused variant deliberately includes the expected tools and is diagnostic,
not a production accuracy estimate. The full variant retains the complete Assist
catalog. Reports are saved after every prediction and summarize each category.
Model context is reset for every request; cached tool indexes and loaded weights
may be reused. Run the older held-out and Main Light regression checks below as
well, using the new weight path.

```powershell
.venv-training/Scripts/python.exe scripts/local_training.py evaluate --report training-output/base.json
.venv-training/Scripts/python.exe scripts/local_training.py evaluate --weights training-output/model/tuned.cact --report training-output/tuned.json
.venv-training/Scripts/python.exe scripts/local_training.py evaluate --data training-output/test-full-catalog.jsonl --weights training-output/model/tuned.cact --report training-output/tuned-full.json
.venv-training/Scripts/python.exe scripts/local_training.py evaluate --data training-output/regression-full-catalog.jsonl --weights training-output/model/tuned.cact --report training-output/regression.json
```

Only JSON schemas are passed to Needle. There are no Python tool callbacks and
no connection to Home Assistant, so predictions cannot change devices. Every
expected call must match exactly, including argument values and call order.
Suppressed, ungrounded, negated, and error responses fail. An incorrect result
causes a nonzero exit code; the detailed report is still written.

Confidence is recorded but is not used to score this offline comparison, because
the local export has no calibrated score. A passing base-model prediction may
still fall below the integration's minimum confidence. These reports do not
establish that either model is authorized to execute a command.

Run the full catalog check as well as the focused test. Needle retrieves a subset
when many tools are available; a correct result among five tools does not show
that the correct tool remains reachable in the full Assist catalog. The provided
test set is small and synthetic, not proof of production accuracy or safety.
The separate regression file checks the reported Main Light on/off failures with
the full catalog. Those names occur in training, so do not count these checks as
held-out accuracy. No live home-state context is included in either test set.

Fine-tuning changes model predictions, not the integration's execution design.
It does not add persistent memory, automatic automation creation, or an agent
loop that plans from tool results.

Source: [Cactus's local fine-tuning guide](https://www.cactuscompute.com/blog/finetuning-needle).

# Training Notes

This directory contains local preparation code for the training phase. It does
not require GPU access.

## Current Warm-Start Data

Generate Java oracle SFT examples:

```bash
PYTHONPATH=. python -m legacy_cobol_env.training.build_java_sft_dataset
```

Artifact:

- `outputs/training/java_oracle_sft.jsonl`

Generate compact Java oracle SFT examples for smaller context windows:

```bash
PYTHONPATH=. python -m legacy_cobol_env.training.build_java_sft_dataset --compact
```

Artifact:

- `outputs/training/java_oracle_sft_compact.jsonl`

Java SFT is the current training starting point. Each row uses the active Java
file-edit completion schema:

```json
{
  "files": {
    "src/main/java/com/example/migration/MigrationService.java": "...java source..."
  }
}
```

The dataset includes all six task families and marks `invoice_occurs_001` as
the primary training target because it remains unsolved after Azure Java
repair-1: zero-shot scored `0.35`, repair-1 improved to `0.5625`, and the task
still failed hidden/fresh generalization.

## Legacy Python Warm-Start Data

Generate oracle SFT examples:

```bash
PYTHONPATH=. .venv/bin/python -m legacy_cobol_env.training.build_sft_dataset
```

Artifact:

- `outputs/training/oracle_sft.jsonl`

The old Python SFT dataset is retained for backward compatibility with the
legacy Python path. It is not the primary training artifact for the current
COBOL-to-Java evaluation.

The current public rollout schema is Java file-edit JSON:

```json
{
  "files": {
    "src/main/java/com/example/migration/MigrationService.java": "...java source..."
  }
}
```

## Current Training Target

The first SFT/RL generalization target is `invoice_occurs_001`.

Why:

- It is now the hardest task: multi-file COBOL, `OCCURS` parsing, and tax-code
  lookup through `TAXRATE.cbl`.
- The task is still verifiable with hidden and fresh fixed-width records.
- The committed Azure Java repair-1 artifact improved the public score from
  `0.35` to `0.5625`, but the task still failed hidden/fresh generalization.

## Dry-Run Artifacts

The dry-run path writes scaffold evidence without GPU access:

- `outputs/training/sft_run_metadata.json`
- `outputs/training/sft_loss.csv`
- `outputs/training/sft_loss.svg`

These files prove the training command wiring. They are not a trained model
result and should not be described as model improvement.

## Next GPU Step

Before retraining, audit prompt lengths and run a generation-only smoke test.
The failed first Qwen2.5-Coder-3B adapter produced malformed Java
(`cimport ...`) on `invoice_occurs_001`, so do not run full OpenEnv rollout
until the smoke test emits valid Java `files` JSON.

Length audit:

```bash
PYTHONPATH=. python -m legacy_cobol_env.training.audit_java_sft_lengths \
  --dataset legacy_cobol_env/outputs/training/java_oracle_sft_compact.jsonl \
  --model-name Qwen/Qwen2.5-Coder-3B-Instruct \
  --max-seq-length 2048
```

Generation smoke test:

```bash
LOCAL_MODEL_PATH=Qwen/Qwen2.5-Coder-3B-Instruct \
LOCAL_ADAPTER_PATH=legacy_cobol_env/outputs/training/java-sft-qwen-coder-3b \
PYTHONPATH=. python -m legacy_cobol_env.training.smoke_generate_sft \
  --compact \
  --output legacy_cobol_env/outputs/evals/local_java_sft3b_invoice_generation_smoke.json
```

Use a small open code model for SFT warm-start, then evaluate with the same
OpenEnv rollout harness. If SFT alone does not close the invoice gap, move to
RL on the environment reward.

Recommended first run:

```bash
python -m venv .venv-gpu
. .venv-gpu/bin/activate
pip install -r legacy_cobol_env/training/requirements-gpu.txt
pip install -e legacy_cobol_env
PYTHONPATH=. python -m legacy_cobol_env.training.build_java_sft_dataset --compact
PYTHONPATH=. python -m legacy_cobol_env.training.train_sft \
  --dataset legacy_cobol_env/outputs/training/java_oracle_sft_compact.jsonl \
  --model-name Qwen/Qwen2.5-Coder-3B-Instruct \
  --output-dir legacy_cobol_env/outputs/training/java-sft-qwen-coder-3b \
  --max-seq-length 4096 \
  --num-train-epochs 3 \
  --learning-rate 1e-4 \
  --per-device-train-batch-size 1 \
  --gradient-accumulation-steps 1 \
  --no-bf16 \
  --dry-run
PYTHONPATH=. python -m legacy_cobol_env.training.train_sft \
  --dataset legacy_cobol_env/outputs/training/java_oracle_sft_compact.jsonl \
  --model-name Qwen/Qwen2.5-Coder-3B-Instruct \
  --output-dir legacy_cobol_env/outputs/training/java-sft-qwen-coder-3b \
  --max-seq-length 4096 \
  --num-train-epochs 3 \
  --learning-rate 1e-4 \
  --per-device-train-batch-size 1 \
  --gradient-accumulation-steps 1 \
  --no-bf16
```

`train_sft` now defaults to the Java dataset
`legacy_cobol_env/outputs/training/java_oracle_sft.jsonl` and output directory
`legacy_cobol_env/outputs/training/java-sft-qwen-coder-7b`. The default model is
`Qwen/Qwen2.5-Coder-7B-Instruct`, chosen as a conservative first GPU target.
Override it with `--model-name` for a larger code model.

For T4 GPUs, prefer the compact dataset, 3 to 5 epochs, `--no-bf16`, and a
sequence length selected by the audit output. Avoid 20 epochs on six examples;
it memorizes brittle continuations instead of reliable Java file-edit JSON.

To dry-run the legacy Python dataset instead, pass the dataset and output
directory explicitly:

```bash
PYTHONPATH=. python -m legacy_cobol_env.training.train_sft \
  --dataset legacy_cobol_env/outputs/training/oracle_sft.jsonl \
  --output-dir legacy_cobol_env/outputs/training/legacy-python-sft-qwen-coder-7b \
  --dry-run
```

Smoke-test the trained checkpoint before OpenEnv rollout:

```bash
LOCAL_MODEL_PATH=Qwen/Qwen2.5-Coder-3B-Instruct \
LOCAL_ADAPTER_PATH=legacy_cobol_env/outputs/training/java-sft-qwen-coder-3b \
PYTHONPATH=. python -m legacy_cobol_env.training.smoke_generate_sft \
  --compact \
  --task-id invoice_occurs_001 \
  --output legacy_cobol_env/outputs/evals/local_java_sft3b_invoice_generation_smoke.json
```

Smoke success criterion:

- `validation.valid_schema` is `true`.
- `validation.valid_edits` is `true`.
- the response is Java `files` JSON, not free-form Java or Python `code`.

OpenEnv rollout success criterion after the smoke test passes:

- invoice public score improves over the current rerun baseline, ideally to
  0.80+ accepted.
- no regression in package validation or local tests.

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

Use a small open code model for SFT warm-start, then evaluate with the same
OpenEnv rollout harness. If SFT alone does not close the invoice gap, move to
RL on the environment reward.

Recommended first run:

```bash
python -m venv .venv-gpu
. .venv-gpu/bin/activate
pip install -r legacy_cobol_env/training/requirements-gpu.txt
pip install -e legacy_cobol_env
PYTHONPATH=. python -m legacy_cobol_env.training.build_java_sft_dataset
PYTHONPATH=. python -m legacy_cobol_env.training.train_sft --dry-run
PYTHONPATH=. python -m legacy_cobol_env.training.train_sft
```

`train_sft` now defaults to the Java dataset
`legacy_cobol_env/outputs/training/java_oracle_sft.jsonl` and output directory
`legacy_cobol_env/outputs/training/java-sft-qwen-coder-7b`. The default model is
`Qwen/Qwen2.5-Coder-7B-Instruct`, chosen as a conservative first GPU target.
Override it with `--model-name` for a larger code model.

To dry-run the legacy Python dataset instead, pass the dataset and output
directory explicitly:

```bash
PYTHONPATH=. python -m legacy_cobol_env.training.train_sft \
  --dataset legacy_cobol_env/outputs/training/oracle_sft.jsonl \
  --output-dir legacy_cobol_env/outputs/training/legacy-python-sft-qwen-coder-7b \
  --dry-run
```

Evaluate the trained checkpoint:

```bash
LOCAL_MODEL_PATH=legacy_cobol_env/outputs/training/java-sft-qwen-coder-7b \
PYTHONPATH=. python -m legacy_cobol_env.eval.run_model_rollouts \
  --provider local-transformers \
  --task-id invoice_occurs_001 \
  --max-repairs 1 \
  --output legacy_cobol_env/outputs/evals/local_sft_invoice_rollout.json
```

Success criterion:

- invoice public score improves over the current rerun baseline, ideally to
  0.80+ accepted.
- no regression in package validation or local tests.

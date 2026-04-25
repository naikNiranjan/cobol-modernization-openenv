# Training Notes

This directory contains local preparation code for the training phase. It does
not require GPU access.

## Current Warm-Start Data

Generate oracle SFT examples:

```bash
PYTHONPATH=. .venv/bin/python -m legacy_cobol_env.training.build_sft_dataset
```

Artifact:

- `outputs/training/oracle_sft.jsonl`

The current public rollout schema is Java file-edit JSON:

```json
{
  "files": {
    "src/main/java/com/example/migration/MigrationService.java": "...java source..."
  }
}
```

The training generator is retained for compatibility until the Java SFT phase updates it. Do not treat the existing warm-start JSONL as the primary Java evaluation artifact.

## Current Training Target

The first RL/generalization target is `invoice_occurs_001`.

Why:

- It is now the hardest task: multi-file COBOL, `OCCURS` parsing, and tax-code
  lookup through `TAXRATE.cbl`.
- The task is still verifiable with hidden and fresh fixed-width records.
- The prior pre-hardening Azure repair run exposed the right failure shape:
  visible tests can pass while hidden/fresh generalization still fails.

Rerun the live Azure baseline after local gates pass before claiming a current
trained-vs-baseline improvement.

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
PYTHONPATH=. python -m legacy_cobol_env.training.train_sft --dry-run
PYTHONPATH=. python -m legacy_cobol_env.training.train_sft
```

The default model is `Qwen/Qwen2.5-Coder-7B-Instruct`, chosen as a conservative
first GPU target. Override it with `--model-name` for a larger code model.

Evaluate the trained checkpoint:

```bash
LOCAL_MODEL_PATH=legacy_cobol_env/outputs/training/sft-qwen-coder-7b \
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

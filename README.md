# Legacy COBOL-to-Java Migration Workbench

Root-level submission entrypoint for an OpenEnv COBOL-to-Java modernization workbench. The environment asks an agent to inspect COBOL source and copybooks, edit Java files, run Maven/JUnit visible tests, and submit for hidden plus fresh-test scoring. The full environment documentation lives in `legacy_cobol_env/README.md`.

The primary model completion schema is Java file-edit JSON:

```json
{
  "files": {
    "src/main/java/com/example/migration/MigrationService.java": "...java source..."
  }
}
```

The Python tool path is still present for backward compatibility, but the public demo, oracle trajectories, model rollouts, and root inference path now use Java.

## Gate Commands

Build the root Docker image:

```bash
docker build -t openenvr2-gate .
```

Run the server from that image:

```bash
docker run --rm -p 8000:8000 openenvr2-gate
```

Smoke-test the server:

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/schema
```

Run the inference contract in static mode without network access:

```bash
python inference.py --mode static --max-repairs 0 --output /tmp/java-static-result.json
```

Run the live baseline with Azure OpenAI or an OpenAI-compatible endpoint. For Azure OpenAI, use the Azure endpoint as `API_BASE_URL`, the deployment as `MODEL_NAME`, and the API key as `HF_TOKEN`:

```bash
API_BASE_URL="https://..." \
MODEL_NAME="..." \
HF_TOKEN="..." \
python inference.py --max-repairs 1 --output /tmp/java-live-result.json
```

`inference.py` emits strict `[START]`, `[STEP]`, and `[END]` JSON records and runs all six task families by default. It prompts for Java file-edit JSON and uses the Java OpenEnv tool path. Use `--task-id invoice_occurs_001` to isolate one task.

Regenerate Java oracle artifacts. Java 17+ and Maven are required because visible, hidden, and fresh tests run through JUnit:

```bash
PYTHONPATH=. python -m legacy_cobol_env.eval.run_oracles
PYTHONPATH=. python -m legacy_cobol_env.eval.run_model_rollouts \
  --provider oracle-model \
  --output legacy_cobol_env/outputs/evals/oracle_model_rollouts.json
```

Current regenerated oracle artifacts score `1.0000` mean public reward with `6 / 6` accepted tasks.

Run the compiler-backed invoice authenticity check:

```bash
PYTHONPATH=. python -m legacy_cobol_env.eval.run_cobol_oracle_checks --build
```

For the problem statement, Java tool sequence, reward components, local/Azure validation, and training scope, see `legacy_cobol_env/README.md`.

---
title: Legacy COBOL-to-Java Migration Workbench
emoji: 🧾
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
app_port: 8000
base_path: /web
tags:
  - openenv
  - cobol
  - reinforcement-learning
---

# Legacy COBOL-to-Java Migration Workbench

An OpenEnv environment where an agent acts like a legacy modernization engineer. The agent receives a migration ticket, inspects COBOL and copybooks through tools, edits Java source files, runs Maven/JUnit visible tests, and submits a final Java migration scored on hidden and fresh tests.

The current build includes six judge-facing task families covering payroll, customer records, insurance claims, banking account status, invoice OCCURS tables, and legacy date normalization. The Python path still exists for backward compatibility, but Java is the primary public demo and evaluation path.

## Problem

This environment frames COBOL-to-Java modernization as a long-horizon professional task. A model must inspect fixed-width COBOL layouts, infer business rules, preserve exact record widths, handle implied decimals with Java types such as `BigDecimal`, respond to compiler/test feedback, and produce maintainable Java that generalizes beyond visible examples.

## Environment Overview

Each episode starts with a partial ticket. The agent can discover details through MCP tools:

- `read_cobol_file`
- `read_copybook`
- `parse_copybook_layout`
- `inspect_business_rules`
- `get_source_to_java_metadata`
- `generate_java_skeleton`
- `read_java_file`
- `edit_java_file`
- `run_junit_tests`
- `inspect_test_failure`
- `submit_final`

The primary Java tool sequence is:

```text
read_cobol_file -> read_copybook -> parse_copybook_layout ->
inspect_business_rules -> get_source_to_java_metadata ->
generate_java_skeleton -> edit_java_file -> run_junit_tests -> submit_final
```

If visible JUnit tests fail, the agent can call `inspect_test_failure` and repair the same Java file-edit JSON. The environment also keeps `write_python_solution`, `run_visible_tests`, and `inspect_diff` for backward compatibility with older callers; they are not the primary rollout path.

The generated Java project uses package `com.example.migration`. The required class is `MigrationService`, with this method:

```java
public String migrate(String inputRecord)
```

Allowed editable files are:

- `src/main/java/com/example/migration/MigrationService.java`
- `src/main/java/com/example/migration/RecordParser.java`
- `src/main/java/com/example/migration/RecordFormatter.java`

Model completions must return only Java file-edit JSON:

```json
{
  "files": {
    "src/main/java/com/example/migration/MigrationService.java": "...java source..."
  }
}
```

The final score combines Java compile/JUnit results, hidden and fresh pass rates, type/decimal fidelity, fixed-width layout fidelity, anti-hardcoding checks, and safety. Episodes are capped by the environment step limit. The next action after terminal returns a no-op reward of `0.0`, and all post-terminal mutations are blocked.

## Quick Start

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

Java validation requires Java 17+ and Maven on `PATH`. Without Maven, Java runner tests return structured failures or pytest skips instead of crashing.

Run the server locally:

```bash
.venv/bin/python -m legacy_cobol_env.server.app --port 8000
```

Then open `/web` or connect with the client:

```python
from legacy_cobol_env import LegacyCobolEnv

with LegacyCobolEnv(base_url="http://localhost:8000") as env:
    env.reset()
    print([tool.name for tool in env.list_tools()])
```

Build and smoke-test the Docker image:

```bash
cd legacy_cobol_env
../.venv/bin/openenv build -t legacy-cobol-env:local
docker run -d --rm --name legacy-cobol-env-smoke -p 18000:8000 legacy-cobol-env:local
curl -sS http://127.0.0.1:18000/health
curl -sS -X POST http://127.0.0.1:18000/reset -H 'Content-Type: application/json' -d '{"task_id":"payroll_net_pay_001"}'
docker stop legacy-cobol-env-smoke
```

## Reward Components

```text
final_reward =
  0.12 * java_compile
+ 0.45 * hidden_junit_pass_rate
+ 0.15 * fresh_junit_pass_rate
+ 0.10 * type_and_decimal_fidelity
+ 0.08 * layout_fidelity
+ 0.05 * anti_hardcoding
+ 0.05 * safety
```

Visible JUnit tests are for debugging and repair. Final submission runs hidden JUnit cases and generated fresh tests through `evaluate_java_files`; aggregate hidden/fresh counts are returned, but hidden/fresh case details and expected outputs are not revealed. The fresh split and anti-hardcoding checks are intended to penalize visible-output memorization.

## Task Families

| Task | Difficulty | COBOL concepts | Main failure modes |
| --- | --- | --- | --- |
| `fixed_width_customer` | easy | `PIC X`, padding/truncation, status mapping | trimmed spaces, lost ZIP leading zeros, bad output width |
| `decimal_copybook_payroll` | medium | copybook layout, implied decimals, level-88 bonus flag | float drift, wrong rounding, wrong fixed-width net pay |
| `claims_eligibility_branching` | medium | `EVALUATE TRUE`, branch precedence | wrong first-match branch, boundary mistakes |
| `account_status_level88` | medium | level-88 status conditions, signed amount | treating condition names as variables, wrong precedence |
| `date_normalization` | medium | legacy YYMMDD windowing, validation | wrong century window, over-rejecting legacy dates |
| `invoice_occurs_totals` | hard | multi-file `INVTOTAL.cbl`/`TAXRATE.cbl`, `OCCURS`, copybook tax-code metadata | wrong stride, ignoring tax-code lookup, overfitting visible invoice IDs |

`inspect_business_rules` exposes agent-facing hints only. Exact reference rules stay internal for tests and documentation.

## Baseline Evidence

Run deterministic non-model baselines:

```bash
PYTHONPATH=. .venv/bin/python legacy_cobol_env/eval/run_baselines.py
```

Current baseline means:

```text
identity     0.15
blank_width  0.1767
```

Artifacts:

- `outputs/evals/baseline_results.json`
- `plots/baseline_scores.svg`

Run Java oracle sanity trajectories:

```bash
PYTHONPATH=. .venv/bin/python legacy_cobol_env/eval/run_oracles.py
```

Current Java oracle sanity result:

```text
mean public score  1.0
accepted tasks     6 / 6
```

Artifact:

- `outputs/evals/oracle_trajectories.json`

Run provider-backed model rollouts. The `oracle-model` provider returns Java `files` JSON and exercises the same Java tool path as model completions:

```bash
PYTHONPATH=. .venv/bin/python -m legacy_cobol_env.eval.run_model_rollouts --provider oracle-model
```

Supported local/provider modes:

- `oracle-model`: model-shaped plumbing check using reference solutions
- `static`: fixed response from `STATIC_RESPONSE`
- `azure-openai`: requires `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and `AZURE_OPENAI_DEPLOYMENT`
- `hf-endpoint`: requires `HF_INFERENCE_ENDPOINT` and `HF_TOKEN`

Artifact:

- `outputs/evals/oracle_model_rollouts.json`

Run the compiler-backed invoice oracle check:

```bash
PYTHONPATH=. .venv/bin/python -m legacy_cobol_env.eval.run_cobol_oracle_checks --build
```

This builds a Dockerized GnuCOBOL oracle for the hard invoice task, compiles the actual task COBOL sources (`INVTOTAL.cbl` and `TAXRATE.cbl`), then compares visible, hidden, and fresh invoice outputs against the Python reference.

Current compiler-backed result:

```text
invoice COBOL oracle cases  13 / 13 matched
task COBOL source compile   passed
```

Artifact:

- `outputs/evals/cobol_invoice_oracle_check.json`

Current regenerated Java evidence:

| Policy | Mean public score | Accepted tasks |
| --- | ---: | ---: |
| deterministic identity | 0.1500 | 0 / 6 |
| deterministic blank width | 0.1767 | 0 / 6 |
| `oracle-model` plumbing check | 1.0000 | 6 / 6 |
| Azure Java zero-shot | 0.7833333333333333 | 4 / 6 |
| Azure Java repair-1 | 0.9270833333333334 | 5 / 6 |

Task-level Azure Java comparison:

| Task | Zero-shot | Repair-1 |
| --- | --- | --- |
| `payroll_net_pay_001` | 1.0 accepted | 1.0 accepted |
| `customer_format_001` | 0.5 failed | 1.0 accepted |
| `claims_eligibility_001` | 1.0 accepted | 1.0 accepted |
| `account_status_001` | 1.0 accepted | 1.0 accepted |
| `invoice_occurs_001` | 0.35 failed | 0.5625 failed |
| `date_normalization_001` | 0.85 accepted | 1.0 accepted |

`invoice_occurs_001` remains unsolved after one repair loop. It is the best target for SFT/RL because visible feedback improved the public score from `0.35` to `0.5625`, but hidden/fresh generalization remains incomplete: the repair-1 final components report `hidden_junit_pass_rate=0.25`, `fresh_junit_pass_rate=0.5`, and `anti_hardcoding=0.5`.

Latest Azure ML validation:

| Test file | Result |
| --- | --- |
| `legacy_cobol_env/tests/test_model_rollout.py` | 6 passed |
| `legacy_cobol_env/tests/test_inference_contract.py` | 6 passed |
| `legacy_cobol_env/tests/test_eval_harness.py` | 2 passed with Maven/JUnit |
| `legacy_cobol_env/tests/test_java_runner.py` | 18 passed |
| `legacy_cobol_env/tests/test_environment.py` | 24 passed |
| `legacy_cobol_env/tests/test_api_contract.py` | 6 passed |

`run_evidence_report` uses the committed Azure Java rollout artifacts generated after the invoice task hardening.

Azure Java artifacts:

- `outputs/evals/azure_java_zeroshot_rollouts.json`
- `outputs/evals/azure_java_repair1_rollouts.json`

Generate the submission evidence summary and score plot:

```bash
PYTHONPATH=. .venv/bin/python -m legacy_cobol_env.eval.run_evidence_report
```

Artifacts:

- `outputs/evals/score_summary.json`
- `plots/model_scores.svg`

Run the root submission inference script in static mode:

```bash
python inference.py --mode static --max-repairs 0 --output /tmp/java-static.json
```

Run the root submission inference script against Azure OpenAI or another OpenAI-compatible endpoint:

```bash
API_BASE_URL="https://..." MODEL_NAME="..." HF_TOKEN="..." python inference.py --max-repairs 1
```

The root script uses `openai.OpenAI`, emits `[START]`, one `[STEP]` per task, and `[END]`, prompts for Java file-edit JSON, and defaults to all six tasks.

Generate SFT warm-start data:

```bash
PYTHONPATH=. .venv/bin/python -m legacy_cobol_env.training.build_sft_dataset
```

Artifact:

- `outputs/training/oracle_sft.jsonl`

Dry-run the GPU training command locally:

```bash
PYTHONPATH=. .venv/bin/python -m legacy_cobol_env.training.train_sft --dry-run
```

Dry-run artifacts:

- `outputs/training/sft_run_metadata.json`
- `outputs/training/sft_loss.csv`
- `outputs/training/sft_loss.svg`

Evaluate a trained/local checkpoint:

```bash
LOCAL_MODEL_PATH=legacy_cobol_env/outputs/training/sft-qwen-coder-7b \
PYTHONPATH=. .venv/bin/python -m legacy_cobol_env.eval.run_model_rollouts \
  --provider local-transformers \
  --task-id invoice_occurs_001 \
  --max-repairs 1 \
  --output legacy_cobol_env/outputs/evals/local_sft_invoice_rollout.json
```

## Current Scope

Implemented:

- Six end-to-end task families with visible, hidden, and fresh tests
- Java OpenEnv tool path with Maven/JUnit visible and final validation
- Java file-edit model schema
- Structured visible diffs
- Java source safety checks plus the legacy Python sandbox checks
- Direct environment tests
- Deterministic baseline evaluation harness
- Java oracle solutions and JSON workbench trajectories
- Provider-backed model rollout harness for Azure OpenAI and Hugging Face endpoints
- Compiler-backed GnuCOBOL oracle check for the hard invoice task
- Root Dockerfile, root `inference.py`, root `openenv.yaml`, and root README for submission gates
- Typed project action, observation, reward, and state schemas surfaced at `/schema`
- Max-step and post-terminal no-op enforcement
- Score summary, model-score plot, legacy oracle SFT warm-start dataset, and SFT dry-run artifacts

Next:

- Build Java SFT/RL training around `invoice_occurs_001`
- Evaluate before/after improvement on the committed Azure Java baselines
- Push to Hugging Face Spaces with `openenv push`

## Safety Note

The Java runner rejects unsafe source patterns such as process exit/runtime access, restricts edits to allowed Java paths, generates tests into a temporary Maven project, and applies a timeout. The legacy Python sandbox also remains for compatibility. These checks should still be treated as layered mitigation for a hackathon environment, not as complete secure isolation.

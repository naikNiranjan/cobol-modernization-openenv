# COBOL-to-Java OpenEnv Implementation Plan

This plan started from the original `cobol-modernization-openenv` repo and turns it from a COBOL-to-Python environment into a COBOL-to-Java modernization workbench.

The implementation strategy is intentionally non-destructive at first: add Java support beside the existing Python path, prove the Java runner and rewards, then make Java the primary public environment once the test gates pass.

## 1. Initial Repo Cleanup Position

### What was clean at plan start

- The repo is cloned at `/Users/niranjannaiks/cobol-modernization-openenv`.
- Git status only showed new planning documentation.
- The accidental home-level audit file has been removed.
- No generated outputs, old plots, or Python environment files have been deleted.

### What should not be deleted yet

Do not remove these early:

- `legacy_cobol_env/outputs/`
- `legacy_cobol_env/plots/`
- `legacy_cobol_env/eval/oracle_solutions.py`
- `legacy_cobol_env/server/sandbox.py`
- Python-specific tests
- current `README.md` and `legacy_cobol_env/README.md`

Reason: these files give us working baselines, evidence-report patterns, prompt examples, test coverage, and a rollback point. Deleting them before the Java path works would slow us down.

### Cleanup rule

Until the Java path passes tests, cleanup means:

- add new Java files beside the current Python path,
- keep old files working,
- avoid renaming the package,
- avoid changing public OpenEnv behavior unless a test covers it,
- only remove Python-specific public docs after Java is functional.

## 2. Target Product

Build an OpenEnv-compliant environment where an LLM acts like a mainframe modernization agent.

The agent receives:

- COBOL source,
- copybooks,
- parsed copybook layouts,
- business rules,
- source-to-Java metadata,
- Java project skeleton,
- visible JUnit test feedback.

The agent must produce:

- Java source edits,
- fixed-width record parsing and formatting,
- correct COBOL business logic,
- Java code that compiles,
- Java code that passes hidden and fresh JUnit tests.

The environment should train and evaluate whether models improve at COBOL-to-Java modernization, not just whether they can emit plausible Java.

## 3. Hackathon Fit

Primary theme:

- Theme 3.1, Professional Tasks.

Secondary fit:

- Theme 2, Long-Horizon Planning and Instruction Following.

Why this is strong:

- The task requires tool use, codebase inspection, compilation, test repair, and hidden validation.
- Rewards are objective through Java compilation and JUnit tests.
- The domain is underexplored compared with toy grid-worlds and generic coding tasks.
- The demo story is understandable: old COBOL payroll/customer/claims logic becomes tested Java.

Expected outcome:

- An OpenEnv environment that can be used to train LLM agents on realistic COBOL-to-Java modernization workflows.

## 4. Core Technical Decision

Reuse:

- OpenEnv server structure,
- MCP tool environment loop,
- task bank,
- visible/hidden/fresh test splits,
- copybook layout metadata,
- business-rule metadata,
- reward aggregation shape,
- Azure OpenAI/Hugging Face/local provider adapters,
- SFT dataset flow,
- inference contract,
- Docker/OpenEnv packaging pattern.

Replace:

- Python candidate source contract,
- Python sandbox execution,
- Python oracle solution format,
- Python-specific prompt text,
- Python-specific reward component names.

New execution target:

- Java 17,
- Maven,
- JUnit 5,
- one required service interface:

```java
package com.example.migration;

public final class MigrationService {
    public String migrate(String inputRecord) {
        return inputRecord;
    }
}
```

## 5. Proposed Java Tool Surface

Do not use reserved OpenEnv/MCP tool names such as `reset`, `step`, `state`, or `close`.

Add these tools:

```text
scan_program
get_variables
get_expanded_source
get_source_to_java_metadata
generate_java_skeleton
read_java_file
edit_java_file
run_junit_tests
inspect_test_failure
submit_final
```

Tool responsibilities:

- `scan_program`: mark COBOL/copybooks as scanned and return high-level program structure.
- `get_variables`: return variable names, PIC clauses, offsets, scales, level-88 values, and usage hints.
- `get_expanded_source`: return COBOL source with copybook context included.
- `get_source_to_java_metadata`: return Java class/interface expectations, package name, file paths, field mappings, and recommended Java types.
- `generate_java_skeleton`: initialize the editable Java project skeleton in environment state.
- `read_java_file`: return a Java file from the current project state.
- `edit_java_file`: update one allowed Java source file.
- `run_junit_tests`: run visible tests only and return compile/test diagnostics.
- `inspect_test_failure`: return structured diagnostics for the most recent failed visible test.
- `submit_final`: run hidden plus fresh tests and return final reward.

Keep temporarily:

- `read_cobol_file`
- `read_copybook`
- `parse_copybook_layout`
- `inspect_business_rules`
- `write_python_solution`
- `run_visible_tests`
- `inspect_diff`

Reason: adding Java tools alongside old tools gives us a safe transition. After Java tests pass, remove or hide the Python tools from the public README and model prompts.

## 6. Java Project Skeleton

Add this template directory:

```text
legacy_cobol_env/java_templates/
  pom.xml
  src/main/java/com/example/migration/MigrationService.java
  src/main/java/com/example/migration/RecordParser.java
  src/main/java/com/example/migration/RecordFormatter.java
  src/test/java/com/example/migration/MigrationServiceTest.java
```

Initial files:

- `pom.xml`: Java 17, JUnit 5, Surefire.
- `MigrationService.java`: required entry point.
- `RecordParser.java`: helper for fixed-width parsing.
- `RecordFormatter.java`: helper for fixed-width output.
- test file: generated dynamically from visible, hidden, or fresh cases.

Allowed editable files:

```text
src/main/java/com/example/migration/MigrationService.java
src/main/java/com/example/migration/RecordParser.java
src/main/java/com/example/migration/RecordFormatter.java
```

Disallowed edits:

- `pom.xml` unless explicitly allowed,
- test files,
- generated harness files,
- files outside `src/main/java/com/example/migration/`,
- absolute paths,
- path traversal with `..`.

## 7. Java Runner

Add:

```text
legacy_cobol_env/server/java_runner.py
```

Core responsibilities:

- validate submitted file paths,
- reject unsafe file names,
- create a temporary Maven project,
- write template files,
- apply agent Java edits,
- generate JUnit tests from `TestCase` objects,
- run `mvn test`,
- enforce timeout,
- parse compile/test outcomes,
- return structured diagnostics,
- clean up temporary directories.

Suggested data models:

```python
@dataclass
class JavaCaseResult:
    case_id: str
    passed: bool
    expected: str | None = None
    actual: str | None = None
    error: str | None = None
    failure_type: str | None = None


@dataclass
class JavaEvaluationResult:
    compile_ok: bool
    safety_ok: bool
    timed_out: bool
    passed: int
    total: int
    case_results: list[JavaCaseResult]
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
```

Minimum safety checks:

- only allowed Java file paths,
- no symlinks,
- no path traversal,
- max source size per file,
- max total source size,
- no `System.exit`,
- no `Runtime.getRuntime`,
- no `ProcessBuilder`,
- no `java.nio.file`,
- no `java.io.File`,
- no network imports,
- subprocess timeout.

This does not need to be perfect security for local development, but it must prevent obvious reward hacking and accidental host access.

## 8. JUnit Test Generation

Generate JUnit tests from existing `TestCase` objects.

Each case should become:

```java
@Test
void visible_1() {
    MigrationService service = new MigrationService();
    assertEquals("expected fixed width output", service.migrate("input fixed width record"));
}
```

Visible runs:

- include visible cases only,
- return detailed expected vs actual,
- allow `inspect_test_failure`.

Final runs:

- include hidden and fresh cases,
- do not expose hidden/fresh full expected outputs,
- return aggregate pass rates and selected safe summaries.

Fresh tests:

- reuse `generate_fresh_tests(task)`,
- generate new cases at submit time,
- prevent hardcoding visible/hidden examples.

## 9. Reward Design

Replace the current Python reward names with Java-specific components.

Target components:

```text
java_compile
hidden_junit_pass_rate
fresh_junit_pass_rate
type_and_decimal_fidelity
layout_fidelity
anti_hardcoding
safety
```

Suggested weights:

```python
reward = (
    0.12 * java_compile
    + 0.45 * hidden_junit_pass_rate
    + 0.15 * fresh_junit_pass_rate
    + 0.10 * type_and_decimal_fidelity
    + 0.08 * layout_fidelity
    + 0.05 * anti_hardcoding
    + 0.05 * safety
)
```

Component definitions:

- `java_compile`: 1.0 if Maven compile/test startup succeeds, else 0.0.
- `hidden_junit_pass_rate`: hidden passed / hidden total.
- `fresh_junit_pass_rate`: fresh passed / fresh total.
- `type_and_decimal_fidelity`: rewards correct use of implied decimals, rounding, signs, and `BigDecimal` where needed.
- `layout_fidelity`: rewards exact fixed-width output length and field boundaries.
- `anti_hardcoding`: penalizes code that embeds too many known input/output records.
- `safety`: 1.0 if Java file safety checks pass, else 0.0.

Important: final reward must be objective and mostly verifier-based. LLM-as-judge should not be part of the core reward.

## 10. First Task Family

Start with:

```text
decimal_copybook_payroll
```

Reason:

- it already has COBOL source,
- it already has copybook metadata,
- visible/hidden/fresh tests exist,
- decimals and signed fields make Java migration meaningful,
- `BigDecimal` vs `double` gives a clear training signal,
- fixed-width output makes validation crisp.

Agent failure modes to expose:

- uses `double` and gets rounding drift,
- ignores implied decimal scale,
- mishandles signed leading separate deductions,
- ignores level-88 bonus flag,
- emits human-readable strings instead of fixed-width output,
- hardcodes visible examples.

Oracle behavior:

- parse fixed-width fields by offset,
- use `BigDecimal`,
- round tax half-up to cents,
- apply bonus flag,
- floor negative net to zero,
- emit exact fixed-width output.

## 11. Implementation Phases

### Phase 1: Java Runner Prototype

Goal:

- prove Java compile and JUnit execution work independently of the OpenEnv tool loop.

Changes:

- add Java templates,
- add `java_runner.py`,
- add payroll JUnit generation,
- add `test_java_runner.py`,
- keep all Python tools untouched.

Verification:

```bash
pytest legacy_cobol_env/tests/test_java_runner.py -q
```

Success criteria:

- identity skeleton compiles,
- bad Java returns compile failure cleanly,
- a correct payroll Java solution passes visible tests,
- an incorrect payroll Java solution returns useful expected/actual diagnostics,
- timeout path is covered or manually tested.

### Phase 2: Add Java State and Tools

Goal:

- expose Java project editing through OpenEnv tools.

Changes:

- extend `LegacyCobolState` with Java fields,
- register Java tools in `LegacyCobolEnvironment`,
- add Java file draft handling,
- add visible JUnit run state,
- add failure inspection.

Verification:

```bash
pytest legacy_cobol_env/tests/test_environment.py -q
pytest legacy_cobol_env/tests/test_api_contract.py -q
```

Success criteria:

- Java tool sequence works through `env.step`,
- invalid tool ordering is rejected,
- final submit still terminates correctly,
- old Python tests still pass or are explicitly updated with new expected behavior.

### Phase 3: Java Oracle and Baselines

Goal:

- generate known-good Java trajectories for SFT and demo evidence.

Changes:

- add Java oracle file maps,
- add Java oracle runner,
- add Java baseline runner,
- keep Python oracle solutions until Java has equivalent coverage.

Verification:

```bash
PYTHONPATH=. python -m legacy_cobol_env.eval.run_oracles
PYTHONPATH=. python -m legacy_cobol_env.eval.run_baselines
```

Success criteria:

- Java oracle gets high or perfect reward on payroll,
- weak baseline gets lower reward,
- outputs are saved in `legacy_cobol_env/outputs/evals/`.

### Phase 4: Model Rollout Prompt Switch

Goal:

- make Azure OpenAI/HF/local model rollout ask for Java file edits instead of Python code.

Changes:

- update `model_rollout.py`,
- update `trajectory.py`,
- update prompt schema from legacy Python code JSON to `{"files": {...}}`,
- update repair prompt to include visible JUnit diagnostics,
- update `inference.py` static/provider behavior.

Target completion schema:

```json
{
  "files": {
    "src/main/java/com/example/migration/MigrationService.java": "..."
  }
}
```

Verification:

```bash
pytest legacy_cobol_env/tests/test_model_rollout.py -q
pytest legacy_cobol_env/tests/test_inference_contract.py -q
python inference.py --mode static --max-repairs 0 --output /tmp/java-static.json
```

Success criteria:

- provider adapters still work,
- static inference produces valid Java edit JSON,
- repair loop can consume JUnit failure feedback.

### Phase 5: SFT Dataset and Training Script

Goal:

- create trainable examples for Java modernization behavior.

Changes:

- update `sft_dataset.py` to emit Java edit examples,
- include tool-use trajectory examples,
- include visible test repair examples,
- keep output as JSONL for HF/TRL/Unsloth.

Verification:

```bash
PYTHONPATH=. python -m legacy_cobol_env.training.build_sft_dataset
pytest legacy_cobol_env/tests/test_sft_dataset.py -q
```

Success criteria:

- generated examples include Java file edits,
- examples include COBOL/copybook/layout/business-rule context,
- examples are valid JSONL,
- no secrets or Azure credentials are written.

### Phase 6: RL/GRPO Training Loop

Goal:

- satisfy hackathon requirement with a minimal TRL or Unsloth training script connected to the environment.

Minimum training setup:

- use Hugging Face TRL or Unsloth,
- sample Java file-edit completions,
- run the environment verifier,
- score with JUnit reward,
- save reward/loss plots.

Recommended practical flow:

- start with SFT warm-start,
- run small GRPO/RLVR on payroll only,
- add customer/claims after non-zero reward is stable,
- compare base vs SFT vs RL on reward.

Candidate open model:

- use a coder instruct model that fits available GPU budget.
- avoid huge models until the environment loop is stable.
- use Azure OpenAI only for API-based baselines/evaluation, not for weight training.

Verification:

```bash
python -m legacy_cobol_env.training.train_sft --help
```

and later:

```bash
python -m legacy_cobol_env.training.train_grpo --dry-run
```

Success criteria:

- script runs in Colab or Azure ML,
- training connects to environment/verifier,
- README shows before/after reward,
- plots are committed or linked.

### Phase 7: Docker and Hugging Face Space

Goal:

- make the environment runnable by judges.

Changes:

- install Java 17 and Maven in Dockerfile,
- cache Maven dependencies if practical,
- ensure OpenEnv server starts,
- keep image size reasonable,
- update `openenv.yaml` if needed.

Verification:

```bash
docker build -t cobol-java-openenv .
docker run --rm -p 8000:8000 cobol-java-openenv
```

Success criteria:

- environment starts in container,
- reset/step/state work,
- Java visible tests run inside container,
- no local-only path assumptions.

### Phase 8: Public README and Demo Story

Goal:

- make the submission easy for judges to understand in 3-5 minutes.

Update:

- root `README.md`,
- `legacy_cobol_env/README.md`,
- evidence report,
- plots,
- HF Space link,
- mini-blog/video/slides link.

README structure:

- problem,
- environment,
- tools,
- reward design,
- task families,
- training pipeline,
- results,
- before/after examples,
- setup commands,
- HF Space link.

Success criteria:

- clear story,
- visible reward improvement,
- reproducible commands,
- no missing minimum requirement.

## 12. File Change Map

Add first:

```text
docs/cobol_to_java_reuse_audit.md
docs/cobol_to_java_implementation_plan.md
legacy_cobol_env/server/java_runner.py
legacy_cobol_env/java_templates/pom.xml
legacy_cobol_env/java_templates/src/main/java/com/example/migration/MigrationService.java
legacy_cobol_env/java_templates/src/main/java/com/example/migration/RecordParser.java
legacy_cobol_env/java_templates/src/main/java/com/example/migration/RecordFormatter.java
legacy_cobol_env/tests/test_java_runner.py
```

Modify after runner works:

```text
legacy_cobol_env/models.py
legacy_cobol_env/server/legacy_cobol_env_environment.py
legacy_cobol_env/eval/oracle_solutions.py
legacy_cobol_env/eval/model_rollout.py
legacy_cobol_env/eval/trajectory.py
legacy_cobol_env/training/sft_dataset.py
inference.py
Dockerfile
legacy_cobol_env/server/Dockerfile
README.md
legacy_cobol_env/README.md
```

Avoid early:

```text
package rename
deleting Python sandbox
deleting old eval outputs
deleting old training outputs
large README rewrite before Java tests pass
```

## 13. Testing Strategy

Unit tests:

- Java path validation,
- Java safety checks,
- JUnit test generation,
- compile failure parsing,
- visible test pass/fail parsing,
- reward component calculation.

Integration tests:

- Java tool sequence through environment,
- visible JUnit run,
- final submit with hidden/fresh tests,
- inference output contract.

Regression tests:

- existing API contract still works until intentionally switched,
- old Python tests either pass or are updated in the same commit that removes Python mode.

Minimum local gate:

```bash
pytest -q
```

Focused gates during development:

```bash
pytest legacy_cobol_env/tests/test_java_runner.py -q
pytest legacy_cobol_env/tests/test_environment.py -q
pytest legacy_cobol_env/tests/test_model_rollout.py -q
```

## 14. Azure and Hugging Face Usage

Azure should be used for:

- Azure OpenAI baseline runs,
- Azure ML GPU smoke tests,
- possible training runs if HF credits are not enough.

Required Azure OpenAI environment variables:

```text
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY
AZURE_OPENAI_DEPLOYMENT
AZURE_OPENAI_API_VERSION
```

Do not commit:

- keys,
- endpoints if private,
- `.env`,
- Azure ML job secrets,
- HF tokens.

Hugging Face should be used for:

- Space hosting,
- public environment repo,
- model/dataset artifacts if needed,
- mini-blog/writeup.

Training budget approach:

- develop and verify locally first,
- run tiny SFT/GRPO smoke training,
- only scale GPU runs after reward is non-zero and stable,
- prefer smaller coder models for early experiments.

## 15. Evaluation Evidence Needed

For judges, prepare:

- baseline model reward,
- oracle reward,
- trained model reward,
- reward curve,
- loss curve if SFT is used,
- before/after Java code behavior,
- visible JUnit failure example,
- trained repair example,
- hidden/fresh aggregate score.

Good demo flow:

1. Show COBOL payroll copybook and business rules.
2. Show base model Java attempt failing visible JUnit.
3. Show failure diagnostics.
4. Show trained model or oracle passing.
5. Show final reward components.
6. Show HF Space and training script.

## 16. Main Risks and Mitigations

Risk: Maven/JUnit is slow.

Mitigation:

- small Java skeleton,
- cache dependencies,
- one Maven invocation per eval,
- strict timeout,
- start with one task family.

Risk: reward hacking through Java file or process access.

Mitigation:

- path allowlist,
- import denylist,
- source-size limits,
- no test edits,
- timeout,
- fresh tests.

Risk: model never gets non-zero reward.

Mitigation:

- SFT warm-start from oracle trajectories,
- start with payroll only,
- provide visible tests and repair loop,
- use partial compile/layout rewards.

Risk: too much refactor before demo.

Mitigation:

- add Java path beside Python,
- keep package names until stable,
- only rewrite public docs after tests pass.

Risk: Java tests reveal that current expected outputs are Python-oracle-only.

Mitigation:

- keep COBOL oracle checks,
- compare Java output against same fixed-width expected strings,
- add GnuCOBOL checks where useful.

## 17. Definition of Done

Environment done:

- Java tools exposed through OpenEnv,
- Java code compiles/runs via JUnit,
- hidden/fresh rewards work,
- Docker image starts,
- HF Space runs.

Training done:

- minimal Unsloth or HF TRL script exists,
- script calls the environment or verifier,
- at least one real training run is recorded,
- plots are saved,
- before/after behavior is shown.

Submission done:

- README explains problem, environment, rewards, training, results,
- HF Space link is included,
- training script/Colab is included,
- mini-blog/video/slides link is included,
- no secrets are committed,
- final `pytest -q` or documented subset passes.

## 18. Immediate Next Step

Start with Phase 1.

Implement only:

- Java templates,
- `java_runner.py`,
- `test_java_runner.py`,
- one correct payroll Java solution inside the test.

Do not modify the environment tool list yet. Once the Java runner is proven, wire it into OpenEnv tools.

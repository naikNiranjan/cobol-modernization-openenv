# COBOL-to-Java Reuse Audit

This audit maps the original COBOL-to-Python OpenEnv implementation to the COBOL-to-Java mainframe modernization workbench direction.

The repo already contains a useful OpenEnv foundation. The fastest path is to reuse the server, task-bank, evaluation, inference, and training plumbing while replacing the Python candidate execution path with a Java/Maven/JUnit execution path.

## Original Repo Summary

At the start of this audit, the implementation was a working COBOL-to-Python migration environment. The repo has since been extended so Java is the primary public path, while the Python path remains for compatibility.

Current capabilities:

- OpenEnv/FastAPI server.
- MCP tool-based environment.
- Six COBOL task families.
- Visible, hidden, and fresh tests.
- Copybook parsing metadata.
- Structured visible diffs.
- Python candidate sandbox.
- Reward component aggregation.
- Deterministic oracle solutions.
- Baseline and model rollout harnesses.
- Azure OpenAI, Hugging Face endpoint, and local Transformers provider adapters.
- SFT dataset generation from oracle trajectories.
- Root `inference.py` contract for submission gates.
- Docker/OpenEnv packaging.
- Existing evidence artifacts and plots.
- GnuCOBOL oracle check for the invoice task.

## Reuse Decision Matrix

| Area | Current files | Reuse decision | Notes |
| --- | --- | --- | --- |
| OpenEnv/FastAPI app | `legacy_cobol_env/server/app.py`, `server/app.py`, `openenv.yaml` | Reuse with rename/config updates | The OpenEnv server structure is already correct. Keep it and point tools to Java-specific environment class. |
| Environment loop | `legacy_cobol_env/server/legacy_cobol_env_environment.py` | Reuse heavily, adapt tools | Keep reset/step/state, terminal no-op, max steps, tool registration, reward wiring. Replace Python tools with Java tools. |
| State models | `legacy_cobol_env/models.py` | Reuse and extend | Add Java project state: scanned program, metadata, Java files edited, compile status, JUnit run count. |
| Task bank | `legacy_cobol_env/server/task_bank.py` | Reuse core task data, extend schema | Existing COBOL/copybook/test generators are valuable. Add Java skeleton metadata and expected Java interface. |
| Fresh tests | `generate_fresh_tests` | Reuse | Fresh test generation is directly useful for hidden/fresh JUnit test creation. |
| Copybook layouts | task metadata layouts | Reuse | Existing `copybook_layout`, `output_layout`, field offsets, scale, and hints map well to Java parser/formatter tasks. |
| Business rules tool | `inspect_business_rules` | Reuse, possibly rename | Keep as metadata/rules inspection. For Java direction, add source-to-Java metadata. |
| Python sandbox | `legacy_cobol_env/server/sandbox.py` | Replace for target execution | Keep the result dataclasses concept, but replace AST/Python import checks with Java file restrictions plus Maven/JUnit runner. |
| Reward aggregation | `_reward_components`, `_submit_final` | Reuse structure, change components | Replace `interface_contract` with `java_compile`, add hidden/fresh JUnit pass rate, BigDecimal fidelity, layout fidelity. |
| Visible diffs | `_field_diffs`, `inspect_diff` | Reuse concept | Keep structured diffs. Add JUnit failure diagnostics and Java compile failure diagnostics. |
| Eval providers | `legacy_cobol_env/eval/providers.py` | Reuse with prompt changes | Azure OpenAI/HF/local provider adapters are useful. Change system prompts from Python function to Java/Maven project edits. |
| Model rollouts | `legacy_cobol_env/eval/model_rollout.py` | Reuse flow, rewrite tool sequence | Current rollout already reads COBOL/copybooks/layouts, generates code, tests, repairs. Change to Java tools. |
| Trajectory helper | `legacy_cobol_env/eval/trajectory.py` | Reuse | Generic MCP tool-call trajectory runner can stay. |
| Oracle solutions | `legacy_cobol_env/eval/oracle_solutions.py` | Replace content, keep module role | Add Java oracle files or oracle edit sets instead of Python source strings. |
| SFT generation | `legacy_cobol_env/training/sft_dataset.py` | Reuse, change prompts/completions | Generate SFT examples with Java file edits and JUnit repair traces. |
| Training scripts | `legacy_cobol_env/training/*` | Reuse with renamed dataset target | The SFT script/dry run should remain useful after prompt/completion schema changes. |
| Root inference | `inference.py` | Reuse with wording/schema changes | Keep `[START]`, `[STEP]`, `[END]` contract. Change static response and provider prompt to Java edit payload. |
| Dockerfile | `Dockerfile`, `legacy_cobol_env/server/Dockerfile` | Modify | Add JDK and Maven. Cache Maven dependencies. |
| Tests | `legacy_cobol_env/tests/*` | Reuse patterns, rewrite assertions | Current tests are very useful as a template for Java compile/JUnit behavior. |
| Compiler-backed COBOL oracle | `legacy_cobol_env/eval/cobol_oracle.py`, `cobol_oracles/` | Reuse for authenticity | Keep GnuCOBOL oracle checks for task correctness. Java outputs can be compared against the same generated expected records. |

## Components To Keep Nearly As-Is

These are already aligned with the new direction:

- `openenv.yaml`
- `server/app.py`
- `legacy_cobol_env/server/app.py`
- `LegacyCobolEnvironment.reset`
- `LegacyCobolEnvironment.step`
- terminal no-op logic after done/max steps
- task-family generator pattern
- visible/hidden/fresh split
- copybook layout metadata
- business rule metadata
- eval provider abstractions
- trajectory logging
- evidence report pattern
- root Docker packaging pattern
- training dataset generation pattern

## Components To Replace First

### 1. Python candidate sandbox

Legacy Python path:

```text
write_python_solution
run_visible_tests
submit_final
legacy_cobol_env/server/sandbox.py
```

Primary Java path:

```text
generate_java_skeleton
read_java_file
edit_java_file
run_junit_tests
inspect_test_failure
submit_final
legacy_cobol_env/server/java_runner.py
```

### 2. Oracle solution format

Legacy Python path:

```text
one Python source string per family
```

Primary Java path:

```text
one Java file map per family:
{
  "src/main/java/com/example/migration/MigrationService.java": "...",
  "src/main/java/com/example/migration/RecordParser.java": "..."
}
```

### 3. Prompt contract

Legacy Python prompt contract:

One JSON object containing a Python source string.

Primary Java prompt contract:

```json
{
  "files": {
    "src/main/java/com/example/migration/MigrationService.java": "...java source..."
  }
}
```

Keep JSON-only completions. It makes SFT and inference gates simpler.

## New Java Tool Set

Minimum tool set:

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

Map from current tools:

```text
read_cobol_file            -> keep or fold into scan/get_expanded_source
read_copybook              -> keep or fold into get_expanded_source
parse_copybook_layout      -> keep; also feed source-to-Java metadata
inspect_business_rules     -> keep; add richer metadata
write_python_solution      -> replace with edit_java_file / write_java_files
run_visible_tests          -> replace with run_junit_tests
inspect_diff               -> extend into inspect_test_failure
submit_final               -> keep name, switch to hidden/fresh JUnit
```

## Java Runner Design

Add:

```text
legacy_cobol_env/server/java_runner.py
```

Responsibilities:

- create temporary Maven project,
- copy skeleton files,
- apply agent file edits,
- inject visible or hidden JUnit tests,
- run `mvn test`,
- parse test result,
- enforce timeout,
- return compile/test diagnostics,
- delete temporary project.

Recommended dataclasses:

```python
@dataclass
class JavaCaseResult:
    case_id: str
    passed: bool
    expected: str | None
    actual: str | None
    error: str | None
    failure_type: str | None

@dataclass
class JavaEvaluationResult:
    compile_ok: bool
    safety_ok: bool
    timed_out: bool
    passed: int
    total: int
    case_results: list[JavaCaseResult]
    error: str | None
```

## Java Project Skeleton

Add:

```text
legacy_cobol_env/java_templates/
  pom.xml
  src/main/java/com/example/migration/MigrationService.java
  src/main/java/com/example/migration/RecordParser.java
  src/main/java/com/example/migration/RecordFormatter.java
  src/test/java/com/example/migration/VisibleMigrationTest.java
```

Initial required interface:

```java
package com.example.migration;

public final class MigrationService {
    public String migrate(String inputRecord) {
        return inputRecord;
    }
}
```

## Docker Changes

Root `Dockerfile` currently uses:

```text
python:3.12-slim
```

For Java validation, install:

```text
openjdk-17-jdk-headless
maven
```

or switch to a base image that includes both Python and JDK.

Expected root Dockerfile change:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk-headless \
    maven \
    && rm -rf /var/lib/apt/lists/*
```

Also cache Maven dependencies by copying a template `pom.xml` and running `mvn test -DskipTests` during image build if practical.

## Reward Changes

Legacy Python reward names have been replaced in the Java path.

Primary Java reward:

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
final_reward = (
    0.12 * java_compile
    + 0.45 * hidden_junit_pass_rate
    + 0.15 * fresh_junit_pass_rate
    + 0.10 * type_and_decimal_fidelity
    + 0.08 * layout_fidelity
    + 0.05 * anti_hardcoding
    + 0.05 * safety
)
```

## Fastest Implementation Path

### Phase 1: Add Java runner without changing the environment tools

Goal:

- prove Maven/JUnit execution works in isolation.

Tasks:

- add Java templates,
- add `java_runner.py`,
- add one payroll Java oracle solution,
- add tests that run visible Java JUnit and pass.

Verification:

```bash
pytest legacy_cobol_env/tests/test_java_runner.py -q
```

### Phase 2: Add Java tools alongside Python tools

Goal:

- avoid breaking current Python submission while introducing Java path.

Add tools:

- `get_source_to_java_metadata`
- `generate_java_skeleton`
- `read_java_file`
- `edit_java_file`
- `run_junit_tests`
- `inspect_test_failure`

Keep old tools temporarily.

Verification:

```bash
pytest legacy_cobol_env/tests/test_environment.py -q
```

### Phase 3: Switch oracle trajectories and model rollouts to Java

Goal:

- make baseline/oracle flow use Java file edits.

Tasks:

- add Java oracle file maps,
- update `model_rollout.py` prompt schema,
- update SFT dataset generation.

Verification:

```bash
PYTHONPATH=. python -m legacy_cobol_env.eval.run_oracles
PYTHONPATH=. python -m legacy_cobol_env.training.build_sft_dataset
```

### Phase 4: Make Java the primary public environment

Goal:

- rename README/tool story to mainframe modernization workbench.

Tasks:

- update README,
- update root inference contract,
- update reward names,
- update evidence report,
- update Dockerfile.

Verification:

```bash
pytest -q
python inference.py --mode static --max-repairs 0 --output /tmp/java-smoke.json
docker build -t cobol-java-openenv .
```

## Recommended First Java Family

Use the existing `decimal_copybook_payroll` task first.

Reasons:

- copybook already exists,
- layout metadata already exists,
- visible/hidden/fresh tests already exist,
- decimal behavior maps naturally to `BigDecimal`,
- fixed-width output is easy to validate,
- demo story is strong.

Baseline failure:

- generated Java uses `double`,
- emits decimal point instead of zero-padded cents,
- ignores level-88 bonus flag.

Trained/oracle success:

- uses `BigDecimal`,
- parses implied decimals,
- handles signed deductions,
- preserves fixed-width output.

## Files Most Likely To Change First

```text
Dockerfile
legacy_cobol_env/models.py
legacy_cobol_env/server/legacy_cobol_env_environment.py
legacy_cobol_env/server/task_bank.py
legacy_cobol_env/server/java_runner.py
legacy_cobol_env/eval/oracle_solutions.py
legacy_cobol_env/eval/model_rollout.py
legacy_cobol_env/training/sft_dataset.py
legacy_cobol_env/tests/test_java_runner.py
legacy_cobol_env/tests/test_environment.py
README.md
legacy_cobol_env/README.md
inference.py
```

## Main Risk

The current Python environment evaluates one source string quickly. Java evaluation will be slower because it compiles and runs Maven/JUnit.

Mitigations:

- keep Java skeleton small,
- cache Maven dependencies in Docker,
- run one Maven invocation per visible/final eval,
- use timeouts,
- start with 3 task families before converting all 6,
- keep Python references for expected outputs.

## Recommendation

Do not throw away the existing repo.

Reuse the current OpenEnv infrastructure and task families. Replace the candidate execution layer and model prompt contract with Java/Maven/JUnit. The first concrete implementation should be a Java runner for the payroll task, because that proves the hardest new primitive: Java compile plus JUnit semantic validation.

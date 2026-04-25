# Agent Handoff Prompts

Use these prompts with the coding agent that will implement the COBOL-to-Java OpenEnv work. Run them in order. Do not ask one agent to do every phase at once unless you have a lot of time to review a large diff.

## Prompt 1: Phase 1 Java Runner Prototype

Copy this prompt first.

```text
You are working in this repo:

/Users/niranjannaiks/cobol-modernization-openenv

Goal:
Implement Phase 1 of the COBOL-to-Java plan. Add a Java/Maven/JUnit runner prototype without changing the existing OpenEnv tool loop or deleting the Python path.

Context files to read first:
- AGENTS.md
- docs/cobol_to_java_reuse_audit.md
- docs/cobol_to_java_implementation_plan.md
- legacy_cobol_env/server/task_bank.py
- legacy_cobol_env/server/sandbox.py
- legacy_cobol_env/tests/test_environment.py

Strict scope:
- Do not rename the package.
- Do not delete Python files.
- Do not change public OpenEnv tools yet.
- Do not rewrite README yet.
- Do not touch Azure or Hugging Face config.
- Do not commit secrets.
- Keep this phase focused on Java runner plus tests.

Implement:
- Add `legacy_cobol_env/java_templates/pom.xml`.
- Add `legacy_cobol_env/java_templates/src/main/java/com/example/migration/MigrationService.java`.
- Add `legacy_cobol_env/java_templates/src/main/java/com/example/migration/RecordParser.java`.
- Add `legacy_cobol_env/java_templates/src/main/java/com/example/migration/RecordFormatter.java`.
- Add `legacy_cobol_env/server/java_runner.py`.
- Add `legacy_cobol_env/tests/test_java_runner.py`.

Java runner requirements:
- Provide dataclasses similar to:
  - `JavaCaseResult`
  - `JavaEvaluationResult`
- Validate allowed editable paths:
  - `src/main/java/com/example/migration/MigrationService.java`
  - `src/main/java/com/example/migration/RecordParser.java`
  - `src/main/java/com/example/migration/RecordFormatter.java`
- Reject absolute paths and `..` path traversal.
- Reject unsafe Java source patterns:
  - `System.exit`
  - `Runtime.getRuntime`
  - `ProcessBuilder`
  - `java.nio.file`
  - `java.io.File`
  - socket/network imports
- Enforce source size limits.
- Create a temporary Maven project.
- Copy Java templates into the project.
- Apply agent-provided Java file edits.
- Generate JUnit 5 tests from existing `TestCase` objects.
- Run Maven test with timeout.
- Return compile/test status and structured case results.
- Clean up temp directories.
- If Maven is missing, return a clear structured failure or skip only the Maven-dependent tests with a clear pytest skip. Do not fail with an unhelpful traceback.

Test requirements:
- Test allowed path validation.
- Test path traversal rejection.
- Test unsafe Java source rejection.
- Test JUnit generation includes input and expected output.
- Test a correct payroll Java solution passes visible payroll cases when Maven is available.
- Test an incorrect payroll Java solution fails and returns useful diagnostics when Maven is available.
- Use the existing `decimal_copybook_payroll` task from `task_bank.py`.

Correct payroll Java behavior:
- Parse fixed-width input fields using exact offsets.
- Use `BigDecimal` for money and tax.
- Parse implied decimals.
- Handle signed leading separate deductions.
- Round tax half-up to cents.
- Add 50.00 for bonus flag `Y`.
- Floor negative net pay to zero.
- Return exact fixed-width output:
  - employee id,
  - employee name padded/truncated to 12,
  - 9-digit zero-padded cents,
  - pay category `H`, `M`, or `L`.

Verification to run:
```bash
pytest legacy_cobol_env/tests/test_java_runner.py -q
```

If that passes, also run:
```bash
pytest legacy_cobol_env/tests/test_environment.py -q
```

Final response format:
- Summarize files changed.
- Show tests run and results.
- Mention if Maven was missing or any tests were skipped.
- Mention any unresolved risks.
```

## Prompt 2: Phase 2 OpenEnv Java Tools

Use this only after Prompt 1 passes.

```text
You are working in this repo:

/Users/niranjannaiks/cobol-modernization-openenv

Goal:
Wire the Java runner into the OpenEnv environment as a new Java tool path while keeping the existing Python tool path working.

Context files to read first:
- docs/cobol_to_java_implementation_plan.md
- legacy_cobol_env/server/java_runner.py
- legacy_cobol_env/server/legacy_cobol_env_environment.py
- legacy_cobol_env/models.py
- legacy_cobol_env/server/task_bank.py
- legacy_cobol_env/tests/test_api_contract.py
- legacy_cobol_env/tests/test_environment.py

Strict scope:
- Do not remove `write_python_solution` or `run_visible_tests` yet.
- Do not break existing Python tests unless the test is explicitly updated to cover a new dual-mode contract.
- Do not rename the package.
- Do not rewrite README yet.

Add Java state:
- Track whether Java skeleton was generated.
- Track editable Java files.
- Track last Java visible test result.
- Track last Java failure diagnostics.
- Track Java draft id/version.

Add tools:
- `get_source_to_java_metadata`
- `generate_java_skeleton`
- `read_java_file`
- `edit_java_file`
- `run_junit_tests`
- `inspect_test_failure`

Tool behavior:
- `get_source_to_java_metadata` returns package name, class name, allowed file paths, required interface, copybook field mappings, output layout, and Java type hints.
- `generate_java_skeleton` initializes editable files from templates.
- `read_java_file` returns an editable Java file.
- `edit_java_file` updates one allowed Java file and records a draft.
- `run_junit_tests` runs visible tests through `java_runner.py`.
- `inspect_test_failure` returns structured visible failure details.
- Existing `submit_final` may remain Python-only in this phase unless you can safely add Java final submission without breaking tests. If you add Java final submission, keep backward compatibility.

Tests to add or update:
- Java skeleton generation through environment step.
- Read Java file through environment step.
- Edit Java file through environment step.
- Visible JUnit run through environment step.
- Bad tool ordering is rejected cleanly.
- Path traversal edit is rejected.
- Existing Python API contract still passes.

Verification to run:
```bash
pytest legacy_cobol_env/tests/test_java_runner.py -q
pytest legacy_cobol_env/tests/test_environment.py -q
pytest legacy_cobol_env/tests/test_api_contract.py -q
```

Final response format:
- Summarize files changed.
- Show tests run and results.
- Explain whether `submit_final` is still Python-only or supports Java.
- Mention unresolved risks.
```

## Prompt 3: Phase 3 Java Final Submit and Rewards

Use this after Prompt 2 passes.

```text
You are working in this repo:

/Users/niranjannaiks/cobol-modernization-openenv

Goal:
Make Java final submission and Java reward components work through the environment.

Context files to read first:
- docs/cobol_to_java_implementation_plan.md
- legacy_cobol_env/server/java_runner.py
- legacy_cobol_env/server/legacy_cobol_env_environment.py
- legacy_cobol_env/models.py
- legacy_cobol_env/server/task_bank.py
- legacy_cobol_env/tests/test_api_contract.py
- legacy_cobol_env/tests/test_environment.py

Strict scope:
- Keep Python path working unless explicitly impossible.
- Do not rewrite model rollout prompts yet.
- Do not delete old eval outputs.

Implement:
- Add Java-aware final submission path.
- Hidden tests and fresh tests should run through JUnit.
- Fresh tests should use existing `generate_fresh_tests(task)`.
- Return Java reward components:
  - `java_compile`
  - `hidden_junit_pass_rate`
  - `fresh_junit_pass_rate`
  - `type_and_decimal_fidelity`
  - `layout_fidelity`
  - `anti_hardcoding`
  - `safety`
- Preserve a typed result model or add a Java-specific typed result model.
- Avoid exposing hidden/fresh expected outputs directly in final responses.

Suggested reward:
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

Tests:
- Correct payroll Java solution gets high/perfect final reward.
- Incorrect Java solution gets lower final reward.
- Unsafe Java solution gets safety penalty.
- Hardcoded visible outputs do not get full score because fresh tests fail.
- Hidden/fresh details are summarized safely.

Verification:
```bash
pytest legacy_cobol_env/tests/test_java_runner.py -q
pytest legacy_cobol_env/tests/test_environment.py -q
pytest legacy_cobol_env/tests/test_api_contract.py -q
```

Final response format:
- Summarize reward logic.
- Show tests run and results.
- Mention reward hacking protections.
- Mention unresolved risks.
```

## Prompt 4: Phase 4 Java Model Rollouts and Inference

Use this after Java final submit and rewards pass.

```text
You are working in this repo:

/Users/niranjannaiks/cobol-modernization-openenv

Goal:
Switch model rollout and inference prompts from Python source generation to Java file edits.

Context files to read first:
- docs/cobol_to_java_implementation_plan.md
- legacy_cobol_env/eval/model_rollout.py
- legacy_cobol_env/eval/trajectory.py
- legacy_cobol_env/eval/providers.py
- inference.py
- legacy_cobol_env/tests/test_model_rollout.py
- legacy_cobol_env/tests/test_inference_contract.py

Strict scope:
- Keep provider adapters intact.
- Keep Azure OpenAI env var names intact.
- Do not add secrets.
- Do not require live Azure calls in unit tests.

Target model completion schema:
```json
{
  "files": {
    "src/main/java/com/example/migration/MigrationService.java": "...java source..."
  }
}
```

Implement:
- Update zero-shot prompt to ask for Java file edits.
- Update repair prompt to include visible JUnit diagnostics.
- Update static provider/oracle flow if needed.
- Update trajectory recording to call Java tools.
- Update `inference.py` so static mode emits Java edit output.
- Keep Azure OpenAI, HF endpoint, and local providers reusable.

Tests:
- Static rollout calls Java tools in the right order.
- Missing Azure config test still passes.
- Inference contract still emits `[START]`, `[STEP]`, `[END]`.
- Inference output contains Java file edit JSON.

Verification:
```bash
pytest legacy_cobol_env/tests/test_model_rollout.py -q
pytest legacy_cobol_env/tests/test_inference_contract.py -q
python inference.py --mode static --max-repairs 0 --output /tmp/java-static.json
```

Final response format:
- Summarize prompt/schema changes.
- Show tests run and results.
- Mention whether live Azure was not run.
```

## Prompt 5: Phase 5 SFT Dataset and Training Plumbing

Use this after Java model rollout works.

```text
You are working in this repo:

/Users/niranjannaiks/cobol-modernization-openenv

Goal:
Update the SFT/training data path so it creates Java modernization examples instead of Python migration examples.

Context files to read first:
- docs/cobol_to_java_implementation_plan.md
- legacy_cobol_env/training/sft_dataset.py
- legacy_cobol_env/training/build_sft_dataset.py
- legacy_cobol_env/training/train_sft.py
- legacy_cobol_env/eval/oracle_solutions.py
- legacy_cobol_env/tests/test_sft_dataset.py
- legacy_cobol_env/tests/test_training_workflow.py

Strict scope:
- Do not run expensive training.
- Do not require GPU for tests.
- Do not add secrets.
- Keep scripts runnable in dry-run/small mode.

Implement:
- Java oracle examples as file maps.
- SFT examples using Java file edit JSON.
- Optional repair examples using visible JUnit diagnostics.
- Update tests for JSONL validity and Java schema.
- Keep the script names unless a rename is necessary.

Verification:
```bash
PYTHONPATH=. python -m legacy_cobol_env.training.build_sft_dataset
pytest legacy_cobol_env/tests/test_sft_dataset.py -q
pytest legacy_cobol_env/tests/test_training_workflow.py -q
```

Final response format:
- Summarize dataset schema.
- Show generated output path.
- Show tests run and results.
- Mention that no expensive training was run.
```

## Prompt 6: Phase 6 Docker, README, and Submission Polish

Use this only after Java environment and Java rollout tests pass.

```text
You are working in this repo:

/Users/niranjannaiks/cobol-modernization-openenv

Goal:
Polish the repo for OpenEnv hackathon submission with Java as the primary story.

Context files to read first:
- docs/cobol_to_java_implementation_plan.md
- README.md
- legacy_cobol_env/README.md
- Dockerfile
- legacy_cobol_env/server/Dockerfile
- openenv.yaml
- legacy_cobol_env/openenv.yaml

Strict scope:
- Do not delete old evidence unless it is clearly replaced.
- Do not add large video files.
- Do not commit secrets.
- Ask before removing Python mode entirely.

Implement:
- Add Java 17 and Maven to Dockerfiles.
- Cache Maven dependencies where practical.
- Update README to explain:
  - problem,
  - environment,
  - tools,
  - reward logic,
  - training pipeline,
  - results,
  - HF Space link placeholder,
  - mini-blog/video/slides placeholder.
- Update old Python wording to Java modernization wording.
- Keep commands reproducible.

Verification:
```bash
pytest -q
python inference.py --mode static --max-repairs 0 --output /tmp/java-static.json
```

If Docker is available:
```bash
docker build -t cobol-java-openenv .
```

Final response format:
- Summarize docs/Docker changes.
- Show tests run and results.
- Mention Docker result or why Docker was not run.
- List exact remaining submission gaps.
```

## Review Prompt For Me After Agent Finishes

After the coding agent finishes, paste this prompt back to the reviewer agent.

```text
Review the implementation done by the other coding agent in:

/Users/niranjannaiks/cobol-modernization-openenv

Review mode:
- Identify bugs, regressions, reward-hacking holes, test gaps, and over-scoped changes.
- Prioritize findings by severity.
- Include file and line references.
- Do not rewrite code unless I explicitly ask.

Focus areas:
- Did it preserve the existing Python/OpenEnv path unless the phase required changing it?
- Does Java path validation block absolute paths, `..`, and unsafe APIs?
- Does Maven/JUnit execution return structured errors instead of crashing?
- Are hidden/fresh outputs protected?
- Are tests meaningful or just snapshotting implementation?
- Does reward logic actually teach COBOL-to-Java behavior?
- Are Azure/HF secrets avoided?
- Are docs accurate to the code?

Also run the relevant tests if possible and summarize results.
```

import json

from legacy_cobol_env.eval.model_rollout import extract_java_files_from_response, run_model_repair_rollout, run_model_rollout
from legacy_cobol_env.eval.oracle_solutions import MIGRATION_SERVICE_PATH, java_response_for_task
from legacy_cobol_env.eval.providers import SequenceResponseProvider, StaticResponseProvider, create_provider
from legacy_cobol_env.server.java_runner import JavaCaseResult, JavaEvaluationResult
from legacy_cobol_env.server.task_bank import all_tasks


def java_eval_for(tests, *, pass_all: bool):
    return JavaEvaluationResult(
        compile_ok=True,
        safety_ok=True,
        timed_out=False,
        passed=len(tests) if pass_all else 0,
        total=len(tests),
        case_results=[
            JavaCaseResult(
                case_id=case.case_id,
                passed=pass_all,
                expected=case.expected_output,
                actual=case.expected_output if pass_all else "bad-output",
                error=None if pass_all else "simulated mismatch",
                failure_type=None if pass_all else "test_failure",
            )
            for case in tests
        ],
    )


def test_extract_java_files_from_fenced_json_response():
    response = '```json\n{"files": {"src/main/java/com/example/migration/MigrationService.java": "package com.example.migration;\\npublic final class MigrationService { public String migrate(String inputRecord) { return inputRecord; } }\\n"}}\n```'

    files = extract_java_files_from_response(response)

    assert set(files) == {MIGRATION_SERVICE_PATH}
    assert "MigrationService" in files[MIGRATION_SERVICE_PATH]


def test_extract_java_files_rejects_python_code_schema():
    response = '{"code": "def migrate(input_record: str) -> str:\\n    return input_record\\n"}'

    try:
        extract_java_files_from_response(response)
    except ValueError as exc:
        assert "files object" in str(exc)
    else:
        raise AssertionError("expected Python code schema to be rejected")


def test_model_rollout_uses_java_tools_and_records_prompt(monkeypatch):
    task = all_tasks()[0]
    provider = StaticResponseProvider(
        name="fixture",
        response=json.dumps(java_response_for_task(task)),
    )

    monkeypatch.setattr(
        "legacy_cobol_env.server.legacy_cobol_env_environment.evaluate_java_files",
        lambda files, tests: java_eval_for(tests, pass_all=True),
    )

    trajectory = run_model_rollout(task=task, provider=provider)

    assert trajectory["policy"] == "fixture"
    assert trajectory["final"]["public_score"] == 1.0
    assert trajectory["final"]["components"]["hidden_junit_pass_rate"] == 1.0
    assert trajectory["model_turns"][0]["provider"] == "fixture"
    assert "COBOL-to-Java modernization" in trajectory["model_turns"][0]["prompt"]
    assert "PAYROLL.cbl" in trajectory["model_turns"][0]["prompt"]
    assert [step["tool_name"] for step in trajectory["steps"]] == [
        "read_cobol_file",
        "read_copybook",
        "parse_copybook_layout",
        "inspect_business_rules",
        "get_source_to_java_metadata",
        "generate_java_skeleton",
        "edit_java_file",
        "run_junit_tests",
        "submit_final",
    ]


def test_model_rollout_rejects_missing_files_json_cleanly():
    task = all_tasks()[0]
    provider = StaticResponseProvider(name="bad-schema", response=json.dumps({"code": "def migrate(input_record): return input_record"}))

    trajectory = run_model_rollout(task=task, provider=provider)

    assert trajectory["final"]["public_score"] == 0.0
    assert trajectory["final"]["accepted"] is False
    assert "files object" in trajectory["error"]
    assert "edit_java_file" not in [step["tool_name"] for step in trajectory["steps"]]


def test_provider_factory_requires_azure_environment():
    try:
        create_provider("azure-openai", {})
    except ValueError as exc:
        assert "AZURE_OPENAI_ENDPOINT" in str(exc)
    else:
        raise AssertionError("expected missing Azure configuration to fail")


def test_repair_rollout_uses_visible_junit_diagnostics_before_second_draft(monkeypatch):
    task = all_tasks()[0]
    initial = {
        "files": {
            MIGRATION_SERVICE_PATH: "package com.example.migration;\npublic final class MigrationService { public String migrate(String inputRecord) { return inputRecord; } }\n"
        }
    }
    repaired = java_response_for_task(task)
    provider = SequenceResponseProvider(
        name="fixture-repair",
        responses=[json.dumps(initial), json.dumps(repaired)],
    )

    def fake_java_eval(files, tests):
        source = files[MIGRATION_SERVICE_PATH]
        return java_eval_for(tests, pass_all="BigDecimal" in source)

    monkeypatch.setattr("legacy_cobol_env.server.legacy_cobol_env_environment.evaluate_java_files", fake_java_eval)

    trajectory = run_model_repair_rollout(task=task, provider=provider, max_repairs=1)

    assert trajectory["final"]["public_score"] == 1.0
    assert len(trajectory["model_turns"]) == 2
    assert "Visible JUnit diagnostics" in trajectory["model_turns"][1]["prompt"]
    assert "simulated mismatch" in trajectory["model_turns"][1]["prompt"]
    assert "inspect_test_failure" in [step["tool_name"] for step in trajectory["steps"]]

import shutil

import pytest
from openenv.core.env_server.mcp_types import CallToolAction, ListToolsAction

from legacy_cobol_env.server.java_runner import JavaCaseResult, JavaEvaluationResult
from legacy_cobol_env.server.legacy_cobol_env_environment import LegacyCobolEnvironment
from legacy_cobol_env.server.task_bank import all_tasks, generate_fresh_tests
from legacy_cobol_env.tests.test_java_runner import PAYROLL_SERVICE


GOOD_SOLUTION = r"""
from decimal import Decimal, ROUND_HALF_UP


def migrate(input_record: str) -> str:
    emp_id = input_record[0:6]
    emp_name = input_record[6:18]
    gross = Decimal(int(input_record[18:27])) / Decimal("100")
    tax_rate = Decimal(int(input_record[27:31])) / Decimal("1000")
    raw_deductions = input_record[31:39]
    sign = -1 if raw_deductions[0] == "-" else 1
    deductions = Decimal(sign * int(raw_deductions[1:])) / Decimal("100")
    bonus_flag = input_record[39:40]

    tax = (gross * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = gross - tax - deductions
    if bonus_flag == "Y":
        net += Decimal("50.00")
    if net < 0:
        net = Decimal("0.00")

    if net >= Decimal("5000.00"):
        category = "H"
    elif net >= Decimal("2500.00"):
        category = "M"
    else:
        category = "L"

    cents = int((net * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{emp_id}{emp_name[:12].ljust(12)}{cents:09d}{category}"
"""


def call(env: LegacyCobolEnvironment, tool_name: str, **arguments):
    obs = env.step(CallToolAction(tool_name=tool_name, arguments=arguments))
    return obs.result.data


def reset_ticket(env: LegacyCobolEnvironment, **kwargs):
    obs = env.reset(**kwargs)
    return obs.result["ticket"]


def test_lists_workbench_tools():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    obs = env.step(ListToolsAction())
    names = {tool.name for tool in obs.tools}

    assert "read_cobol_file" in names
    assert "get_source_to_java_metadata" in names
    assert "generate_java_skeleton" in names
    assert "read_java_file" in names
    assert "edit_java_file" in names
    assert "run_junit_tests" in names
    assert "inspect_test_failure" in names
    assert "submit_final" in names
    assert "reset" not in names


def test_java_metadata_tool_returns_interface_and_field_mappings():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    metadata = call(env, "get_source_to_java_metadata")

    assert metadata["package_name"] == "com.example.migration"
    assert metadata["required_class"] == "MigrationService"
    assert metadata["required_method"] == "public String migrate(String inputRecord)"
    assert "src/main/java/com/example/migration/MigrationService.java" in metadata["allowed_editable_paths"]
    assert metadata["input_width"] == 42
    assert metadata["output_width"] == 28
    assert any(field["name"] == "GROSS-PAY" and field["java_type"] == "BigDecimal" for field in metadata["copybook_field_mappings"])
    assert metadata["java_type_hints"]["copybook_fields"]["DEDUCTIONS"]["java_type"] == "BigDecimal"
    assert metadata["output_layout"][0]["name"] == "OUT-EMP-ID"


def test_java_skeleton_generation_read_and_edit_through_environment_step():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    skeleton = call(env, "generate_java_skeleton")
    read = call(env, "read_java_file", path="src/main/java/com/example/migration/MigrationService.java")
    edited = call(
        env,
        "edit_java_file",
        path="src/main/java/com/example/migration/MigrationService.java",
        content=PAYROLL_SERVICE,
    )

    assert skeleton["ok"] is True
    assert env.state.java_skeleton_generated is True
    assert "public final class MigrationService" in read["content"]
    assert edited["ok"] is True
    assert edited["draft_id"] == 1
    assert env.state.java_draft_id == 1
    assert env.state.java_draft_count == 1
    assert env.state.java_files["src/main/java/com/example/migration/MigrationService.java"] == PAYROLL_SERVICE


def test_java_edit_rejects_path_traversal():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    call(env, "generate_java_skeleton")
    edited = call(env, "edit_java_file", path="../MigrationService.java", content=PAYROLL_SERVICE)

    assert edited["ok"] is False
    assert "path traversal" in edited["error"]
    assert env.state.java_draft_count == 0


def test_java_tools_reject_bad_ordering_cleanly():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    read = call(env, "read_java_file", path="src/main/java/com/example/migration/MigrationService.java")
    visible = call(env, "run_junit_tests")

    assert read["ok"] is False
    assert "generate_java_skeleton" in read["error"]
    assert visible["ok"] is False
    assert "generate_java_skeleton" in visible["error"]


def test_run_junit_tests_missing_maven_returns_structured_failure(monkeypatch):
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")
    call(env, "generate_java_skeleton")

    def missing_maven(files, tests):
        return JavaEvaluationResult(
            compile_ok=False,
            safety_ok=True,
            timed_out=False,
            passed=0,
            total=len(tests),
            error="maven executable not found; install Maven to run Java tests",
        )

    monkeypatch.setattr("legacy_cobol_env.server.legacy_cobol_env_environment.evaluate_java_files", missing_maven)

    result = call(env, "run_junit_tests")

    assert result["ok"] is False
    assert result["compile_ok"] is False
    assert result["safety_ok"] is True
    assert "maven executable not found" in result["error"]
    assert env.state.last_java_visible_result["error"] == result["error"]
    assert env.state.last_java_failure_diagnostics[0]["failure_type"] == "runner_error"


def test_inspect_test_failure_returns_details_after_failed_java_visible_run(monkeypatch):
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")
    call(env, "generate_java_skeleton")
    case = env._task.visible_tests[0]

    def failed_visible(files, tests):
        return JavaEvaluationResult(
            compile_ok=True,
            safety_ok=True,
            timed_out=False,
            passed=0,
            total=len(tests),
            case_results=[
                JavaCaseResult(
                    case_id=case.case_id,
                    passed=False,
                    expected=case.expected_output,
                    actual=case.input_record,
                    error="case_id=visible_1 expected output mismatch",
                    failure_type="test_failure",
                )
            ],
        )

    monkeypatch.setattr("legacy_cobol_env.server.legacy_cobol_env_environment.evaluate_java_files", failed_visible)

    visible = call(env, "run_junit_tests")
    failure = call(env, "inspect_test_failure")

    assert visible["ok"] is True
    assert visible["passed"] == 0
    assert failure["ok"] is True
    assert failure["case_id"] == case.case_id
    assert failure["failure_type"] == "test_failure"
    assert failure["expected"] == case.expected_output
    assert failure["actual"] == case.input_record
    assert failure["field_diffs"]


def test_visible_junit_run_through_environment_step_when_maven_is_available():
    if shutil.which("mvn") is None:
        pytest.skip("Maven is not installed; skipping Maven-dependent Java environment test")

    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    call(env, "generate_java_skeleton")
    edited = call(
        env,
        "edit_java_file",
        path="src/main/java/com/example/migration/MigrationService.java",
        content=PAYROLL_SERVICE,
    )
    visible = call(env, "run_junit_tests", draft_id=edited["draft_id"])

    assert visible["ok"] is True
    assert visible["passed"] == visible["total"]
    assert visible["compile_ok"] is True
    assert visible["java_final_eligible"] is True


def test_good_solution_passes_visible_hidden_and_fresh_tests():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    written = call(env, "write_python_solution", code=GOOD_SOLUTION)
    visible = call(env, "run_visible_tests")
    final = call(env, "submit_final", draft_id=written["draft_id"])

    assert visible["passed"] == visible["total"]
    assert final["public_score"] == 1.0
    assert final["accepted"] is True
    assert env.state.done is True


def test_bad_solution_gets_actionable_visible_diff():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    call(env, "write_python_solution", code="def migrate(input_record: str) -> str:\n    return input_record.strip()\n")
    visible = call(env, "run_visible_tests")
    diff = call(env, "inspect_diff", case_id=visible["failures"][0]["case_id"])

    assert visible["passed"] == 0
    assert any(item["field"] == "OUT-NET-PAY" for item in diff["field_diffs"])


def test_forbidden_import_is_blocked():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    code = "import os\ndef migrate(input_record: str) -> str:\n    return os.getcwd()\n"
    written = call(env, "write_python_solution", code=code)
    visible = call(env, "run_visible_tests", draft_id=written["draft_id"])

    assert written["safety_ok"] is False
    assert visible["safety_ok"] is False
    assert "forbidden import" in visible["error"]


def test_task_bank_has_six_distinct_families_with_fresh_tests():
    tasks = all_tasks()

    assert len(tasks) == 6
    assert len({task.family_id for task in tasks}) == 6
    for task in tasks:
        assert task.visible_tests
        assert task.hidden_tests
        assert generate_fresh_tests(task)
        assert task.metadata["output_width"] == task.metadata["output_layout"][-1]["end"]


def test_reset_can_select_each_family_and_parse_its_copybook_layout():
    for task in all_tasks():
        env = LegacyCobolEnvironment()
        ticket = reset_ticket(env, task_id=task.task_id)
        copybook = ticket["available_copybooks"][0]

        layout = call(env, "parse_copybook_layout", filename=copybook)

        assert ticket["task_id"] == task.task_id
        assert layout["record_name"] == task.metadata["record_name"]
        assert layout["total_width"] == task.metadata["input_width"]


def test_task_metadata_includes_difficulty_and_rule_visibility_split():
    expected = {
        "customer_format_001": "easy",
        "payroll_net_pay_001": "medium",
        "claims_eligibility_001": "medium",
        "account_status_001": "medium",
        "date_normalization_001": "medium",
        "invoice_occurs_001": "hard",
    }

    for task in all_tasks():
        assert task.metadata["difficulty"] == expected[task.task_id]
        assert task.metadata["reference_rules"]
        assert task.metadata["agent_hints"]
        assert task.metadata["business_rules"] == task.metadata["agent_hints"]


def test_invoice_task_uses_multiple_source_and_copybook_artifacts():
    invoice = next(task for task in all_tasks() if task.task_id == "invoice_occurs_001")

    assert sorted(invoice.cobol_files) == ["INVTOTAL.cbl", "TAXRATE.cbl"]
    assert sorted(invoice.copybooks) == ["INVOICE_REC.cpy", "TAX_CODE.cpy"]


def test_invoice_visible_hints_do_not_expose_exact_tax_rates_or_formula():
    invoice = next(task for task in all_tasks() if task.task_id == "invoice_occurs_001")
    visible_hint_text = " ".join(invoice.metadata["agent_hints"])

    assert "1.075" not in visible_hint_text
    assert "7.5" not in visible_hint_text
    assert "multiply" not in visible_hint_text.lower()
    assert "ROUND" not in visible_hint_text.upper()


def test_visible_literal_hardcoding_penalizes_final_component():
    env = LegacyCobolEnvironment()
    env.reset(task_id="customer_format_001")
    task = env._task
    visible = task.visible_tests[0]
    code = f"""
def migrate(input_record: str) -> str:
    if input_record.startswith({visible.input_record[:5]!r}):
        return {visible.expected_output!r}
    return ' ' * {task.metadata["output_width"]}
"""

    written = call(env, "write_python_solution", code=code)
    final = call(env, "submit_final", draft_id=written["draft_id"])

    assert final["components"]["anti_hardcoding"] == 0.0

import shutil

import pytest

from legacy_cobol_env.server.java_runner import (
    ALLOWED_JAVA_PATHS,
    _method_name,
    _parse_surefire_reports,
    evaluate_java_files,
    generate_junit_test_source,
    validate_java_edits,
)
from legacy_cobol_env.server.task_bank import load_task


PAYROLL_SERVICE = r"""
package com.example.migration;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class MigrationService {
    public String migrate(String inputRecord) {
        String empId = inputRecord.substring(0, 6);
        String empName = inputRecord.substring(6, 18);
        BigDecimal gross = cents(inputRecord.substring(18, 27));
        BigDecimal taxRate = new BigDecimal(Integer.parseInt(inputRecord.substring(27, 31))).movePointLeft(3);
        BigDecimal deductions = signedCents(inputRecord.substring(31, 39));
        String bonusFlag = inputRecord.substring(39, 40);

        BigDecimal tax = gross.multiply(taxRate).setScale(2, RoundingMode.HALF_UP);
        BigDecimal net = gross.subtract(tax).subtract(deductions);
        if ("Y".equals(bonusFlag)) {
            net = net.add(new BigDecimal("50.00"));
        }
        if (net.compareTo(BigDecimal.ZERO) < 0) {
            net = BigDecimal.ZERO.setScale(2);
        }

        String category;
        if (net.compareTo(new BigDecimal("5000.00")) >= 0) {
            category = "H";
        } else if (net.compareTo(new BigDecimal("2500.00")) >= 0) {
            category = "M";
        } else {
            category = "L";
        }

        long netCents = net.movePointRight(2).setScale(0, RoundingMode.HALF_UP).longValueExact();
        return empId + padRight(empName, 12) + String.format("%09d", netCents) + category;
    }

    private static BigDecimal cents(String raw) {
        return new BigDecimal(Integer.parseInt(raw)).movePointLeft(2);
    }

    private static BigDecimal signedCents(String raw) {
        int sign = raw.charAt(0) == '-' ? -1 : 1;
        return new BigDecimal(sign * Long.parseLong(raw.substring(1))).movePointLeft(2);
    }

    private static String padRight(String value, int width) {
        String clipped = value.length() > width ? value.substring(0, width) : value;
        return String.format("%-" + width + "s", clipped);
    }
}
""".strip()


BAD_PAYROLL_SERVICE = r"""
package com.example.migration;

public final class MigrationService {
    public String migrate(String inputRecord) {
        return inputRecord;
    }
}
""".strip()


def payroll_task():
    return load_task(task_id="decimal_copybook_payroll")


def service_edit(source: str) -> dict[str, str]:
    return {"src/main/java/com/example/migration/MigrationService.java": source}


def require_maven():
    if shutil.which("mvn") is None:
        pytest.skip("Maven is not installed; skipping Maven-dependent Java runner test")


def test_allowed_path_validation_accepts_template_sources():
    edits = {path: "package com.example.migration;\n" for path in ALLOWED_JAVA_PATHS}

    ok, error = validate_java_edits(edits)

    assert ok is True
    assert error is None


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/MigrationService.java",
        "../MigrationService.java",
        "src/main/java/com/example/migration/../MigrationService.java",
        "src/test/java/com/example/migration/GeneratedMigrationTest.java",
    ],
)
def test_path_validation_rejects_absolute_traversal_and_non_editable_paths(path):
    ok, error = validate_java_edits({path: "package com.example.migration;\n"})

    assert ok is False
    assert error


@pytest.mark.parametrize(
    "source",
    [
        "package com.example.migration; class X { void x() { System.exit(1); } }",
        "package com.example.migration; class X { void x() { System . exit(1); } }",
        "package com.example.migration; class X { void x() { Runtime.getRuntime(); } }",
        "package com.example.migration; class X { void x() { Runtime . getRuntime(); } }",
        "package com.example.migration; class X { ProcessBuilder builder; }",
        "package com.example.migration; import java.nio.file.Path; class X {}",
        "package com.example.migration; import java.io.File; class X {}",
        "package com.example.migration; import java.net.Socket; class X {}",
    ],
)
def test_unsafe_java_source_is_rejected(source):
    result = evaluate_java_files(service_edit(source), payroll_task().visible_tests)

    assert result.safety_ok is False
    assert result.compile_ok is False
    assert result.error


def test_junit_generation_includes_input_and_expected_output():
    case = payroll_task().visible_tests[0]
    source = generate_junit_test_source([case])

    assert case.input_record in source
    assert case.expected_output in source
    assert "MigrationService" in source
    assert "assertEquals" in source


def test_missing_surefire_case_results_are_synthesized(tmp_path):
    tests = payroll_task().visible_tests
    reports_dir = tmp_path / "target/surefire-reports"
    reports_dir.mkdir(parents=True)
    first_method = _method_name(tests[0].case_id, 1)
    (reports_dir / "TEST-GeneratedMigrationTest.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><testsuite><testcase name="{first_method}"/></testsuite>',
        encoding="utf-8",
    )

    results = _parse_surefire_reports(tmp_path, tests)

    assert len(results) == len(tests)
    assert results[0].case_id == tests[0].case_id
    assert results[0].passed is True
    assert [result.failure_type for result in results[1:]] == ["missing_result", "missing_result"]
    assert all(result.passed is False for result in results[1:])


def test_missing_maven_returns_structured_failure(tmp_path):
    missing_mvn = tmp_path / "missing-mvn"

    result = evaluate_java_files(service_edit(BAD_PAYROLL_SERVICE), payroll_task().visible_tests, mvn_executable=str(missing_mvn))

    assert result.safety_ok is True
    assert result.compile_ok is False
    assert result.error is not None
    assert "maven" in result.error.lower()


def test_correct_payroll_java_solution_passes_visible_cases_when_maven_is_available():
    require_maven()

    task = payroll_task()
    result = evaluate_java_files(service_edit(PAYROLL_SERVICE), task.visible_tests)

    assert result.safety_ok is True
    assert result.compile_ok is True
    assert result.timed_out is False
    assert result.passed == result.total == len(task.visible_tests)
    assert all(case.passed for case in result.case_results)


def test_incorrect_payroll_java_solution_fails_with_useful_diagnostics_when_maven_is_available():
    require_maven()

    result = evaluate_java_files(service_edit(BAD_PAYROLL_SERVICE), payroll_task().visible_tests)

    assert result.safety_ok is True
    assert result.compile_ok is True
    assert result.passed < result.total
    assert any(case.failure_type == "test_failure" for case in result.case_results)
    assert any(case.expected and case.actual for case in result.case_results if not case.passed)

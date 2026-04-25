"""Maven/JUnit runner for Java COBOL migration candidates."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .task_bank import TestCase


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "java_templates"

ALLOWED_JAVA_PATHS = frozenset(
    {
        "src/main/java/com/example/migration/MigrationService.java",
        "src/main/java/com/example/migration/RecordParser.java",
        "src/main/java/com/example/migration/RecordFormatter.java",
    }
)

MAX_SOURCE_BYTES = 64_000
MAX_TOTAL_SOURCE_BYTES = 192_000

UNSAFE_SOURCE_PATTERNS = (
    ("ProcessBuilder", "forbidden source pattern: ProcessBuilder"),
    ("java.nio.file", "forbidden package: java.nio.file"),
    ("java.io.File", "forbidden type: java.io.File"),
    ("java.net.", "forbidden network import"),
    ("javax.net.", "forbidden network import"),
)

UNSAFE_SOURCE_REGEXES = (
    (re.compile(r"\bSystem\s*\.\s*exit\b"), "forbidden source pattern: System.exit"),
    (re.compile(r"\bRuntime\s*\.\s*getRuntime\b"), "forbidden source pattern: Runtime.getRuntime"),
)
NETWORK_IMPORT_RE = re.compile(r"(?m)^\s*import\s+(?:static\s+)?(?:java|javax)\.net(?:\.|;)")
SOCKET_IMPORT_RE = re.compile(r"(?m)^\s*import\s+(?:static\s+)?[\w.]*Socket\w*\s*;")
EXPECTED_ACTUAL_RE = re.compile(r"expected:\s*<(.*?)>\s*but was:\s*<(.*?)>", re.DOTALL)


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
    case_results: list[JavaCaseResult] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total


def validate_edit_path(raw_path: str) -> tuple[bool, str | None]:
    path = PurePosixPath(raw_path)
    if not raw_path:
        return False, "path must not be empty"
    if path.is_absolute():
        return False, f"absolute paths are not allowed: {raw_path}"
    if ".." in path.parts:
        return False, f"path traversal is not allowed: {raw_path}"
    if raw_path not in ALLOWED_JAVA_PATHS:
        return False, f"path is not editable: {raw_path}"
    return True, None


def validate_java_edits(file_edits: dict[str, str]) -> tuple[bool, str | None]:
    total_size = 0
    for raw_path, source in file_edits.items():
        path_ok, path_error = validate_edit_path(raw_path)
        if not path_ok:
            return False, path_error
        if not isinstance(source, str):
            return False, f"source must be a string for {raw_path}"

        source_size = len(source.encode("utf-8"))
        if source_size > MAX_SOURCE_BYTES:
            return False, f"source exceeds {MAX_SOURCE_BYTES} bytes: {raw_path}"
        total_size += source_size

        for needle, message in UNSAFE_SOURCE_PATTERNS:
            if needle in source:
                return False, message
        for pattern, message in UNSAFE_SOURCE_REGEXES:
            if pattern.search(source):
                return False, message
        if NETWORK_IMPORT_RE.search(source):
            return False, "forbidden network import"
        if SOCKET_IMPORT_RE.search(source):
            return False, "forbidden socket import"

    if total_size > MAX_TOTAL_SOURCE_BYTES:
        return False, f"total source exceeds {MAX_TOTAL_SOURCE_BYTES} bytes"
    return True, None


def generate_junit_test_source(tests: list[TestCase], class_name: str = "GeneratedMigrationTest") -> str:
    lines = [
        "package com.example.migration;",
        "",
        "import org.junit.jupiter.api.Test;",
        "",
        "import static org.junit.jupiter.api.Assertions.assertEquals;",
        "",
        f"public final class {class_name} {{",
        "    private final MigrationService service = new MigrationService();",
        "",
    ]
    for index, case in enumerate(tests, start=1):
        method_name = _method_name(case.case_id, index)
        lines.extend(
            [
                "    @Test",
                f"    void {method_name}() {{",
                f"        String input = {_java_string(case.input_record)};",
                f"        String expected = {_java_string(case.expected_output)};",
                "        String actual = service.migrate(input);",
                f"        assertEquals(expected, actual, {_java_string('case_id=' + case.case_id)});",
                "    }",
                "",
            ]
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def evaluate_java_files(
    file_edits: dict[str, str],
    tests: list[TestCase],
    timeout_s: float = 60.0,
    mvn_executable: str | None = None,
) -> JavaEvaluationResult:
    safety_ok, safety_error = validate_java_edits(file_edits)
    if not safety_ok:
        return JavaEvaluationResult(
            compile_ok=False,
            safety_ok=False,
            timed_out=False,
            passed=0,
            total=len(tests),
            error=safety_error,
        )

    mvn = mvn_executable or shutil.which("mvn")
    if not mvn:
        return JavaEvaluationResult(
            compile_ok=False,
            safety_ok=True,
            timed_out=False,
            passed=0,
            total=len(tests),
            error="maven executable not found; install Maven to run Java tests",
        )

    with tempfile.TemporaryDirectory(prefix="legacy-cobol-java-") as tmp:
        project_dir = Path(tmp)
        shutil.copytree(TEMPLATE_DIR, project_dir, dirs_exist_ok=True)
        for raw_path, source in file_edits.items():
            target = project_dir.joinpath(*PurePosixPath(raw_path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")

        test_dir = project_dir / "src/test/java/com/example/migration"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "GeneratedMigrationTest.java").write_text(generate_junit_test_source(tests), encoding="utf-8")

        try:
            completed = subprocess.run(
                [mvn, "test", "-q"],
                cwd=project_dir,
                text=True,
                capture_output=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            return JavaEvaluationResult(
                compile_ok=False,
                safety_ok=True,
                timed_out=True,
                passed=0,
                total=len(tests),
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                error="maven test timed out",
            )
        except OSError as exc:
            return JavaEvaluationResult(
                compile_ok=False,
                safety_ok=True,
                timed_out=False,
                passed=0,
                total=len(tests),
                error=f"maven execution failed: {exc}",
            )

        return _result_from_maven(project_dir, tests, completed)


def _result_from_maven(
    project_dir: Path,
    tests: list[TestCase],
    completed: subprocess.CompletedProcess[str],
) -> JavaEvaluationResult:
    diagnostics = _trim_diagnostics(completed.stdout, completed.stderr)
    report_results = _parse_surefire_reports(project_dir, tests)
    compile_ok = bool(report_results) or completed.returncode == 0

    if completed.returncode != 0 and not report_results:
        case_results = [
            JavaCaseResult(
                case_id=case.case_id,
                passed=False,
                expected=case.expected_output,
                error=diagnostics or "maven test failed before executing generated cases",
                failure_type="compile_error",
            )
            for case in tests
        ]
        return JavaEvaluationResult(
            compile_ok=False,
            safety_ok=True,
            timed_out=False,
            passed=0,
            total=len(tests),
            case_results=case_results,
            stdout=completed.stdout,
            stderr=completed.stderr,
            error=diagnostics or "maven test failed",
        )

    passed = sum(1 for result in report_results if result.passed)
    return JavaEvaluationResult(
        compile_ok=compile_ok,
        safety_ok=True,
        timed_out=False,
        passed=passed,
        total=len(tests),
        case_results=report_results,
        stdout=completed.stdout,
        stderr=completed.stderr,
        error=None if completed.returncode == 0 else diagnostics,
    )


def _parse_surefire_reports(project_dir: Path, tests: list[TestCase]) -> list[JavaCaseResult]:
    method_to_case = {_method_name(case.case_id, index): case for index, case in enumerate(tests, start=1)}
    reports_dir = project_dir / "target/surefire-reports"
    results: dict[str, JavaCaseResult] = {}
    parsed_report = False

    for report in sorted(reports_dir.glob("TEST-*.xml")):
        try:
            root = ET.parse(report).getroot()
        except ET.ParseError:
            continue
        parsed_report = True

        for testcase in root.iter():
            if _local_name(testcase.tag) != "testcase":
                continue
            method_name = testcase.attrib.get("name", "")
            case = method_to_case.get(method_name)
            if case is None:
                continue

            failure = _first_failure(testcase)
            if failure is None:
                results[case.case_id] = JavaCaseResult(
                    case_id=case.case_id,
                    passed=True,
                    expected=case.expected_output,
                    actual=case.expected_output,
                )
                continue

            message = failure.attrib.get("message") or (failure.text or "").strip()
            expected, actual = _extract_expected_actual(message)
            results[case.case_id] = JavaCaseResult(
                case_id=case.case_id,
                passed=False,
                expected=expected or case.expected_output,
                actual=actual,
                error=message or "generated JUnit case failed",
                failure_type="test_failure" if _local_name(failure.tag) == "failure" else "test_error",
            )

    if not parsed_report:
        return []

    return [
        results.get(
            case.case_id,
            JavaCaseResult(
                case_id=case.case_id,
                passed=False,
                expected=case.expected_output,
                error="generated JUnit case did not produce a Surefire result",
                failure_type="missing_result",
            ),
        )
        for case in tests
    ]


def _first_failure(testcase: ET.Element) -> ET.Element | None:
    for child in testcase:
        if _local_name(child.tag) in {"failure", "error"}:
            return child
    return None


def _extract_expected_actual(message: str) -> tuple[str | None, str | None]:
    match = EXPECTED_ACTUAL_RE.search(message)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _method_name(case_id: str, index: int) -> str:
    safe_case_id = re.sub(r"\W", "_", case_id)
    if not safe_case_id or safe_case_id[0].isdigit():
        safe_case_id = f"case_{safe_case_id}"
    return f"case_{index}_{safe_case_id}"


def _java_string(value: str) -> str:
    return json.dumps(value)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _trim_diagnostics(stdout: str, stderr: str, limit: int = 4000) -> str:
    text = "\n".join(part.strip() for part in (stdout, stderr) if part and part.strip())
    if len(text) <= limit:
        return text
    return text[-limit:]


__all__ = [
    "ALLOWED_JAVA_PATHS",
    "JavaCaseResult",
    "JavaEvaluationResult",
    "evaluate_java_files",
    "generate_junit_test_source",
    "validate_edit_path",
    "validate_java_edits",
]

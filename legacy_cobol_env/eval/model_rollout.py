"""Run provider-backed Java file-edit rollouts against the workbench."""

from __future__ import annotations

import json
from typing import Any, Callable

from legacy_cobol_env.eval.providers import TextProvider
from legacy_cobol_env.eval.trajectory import call_tool
from legacy_cobol_env.server.java_runner import validate_java_edits
from legacy_cobol_env.server.legacy_cobol_env_environment import LegacyCobolEnvironment
from legacy_cobol_env.server.task_bank import TaskInstance


JAVA_JSON_SCHEMA_TEXT = (
    '{"files": {"src/main/java/com/example/migration/MigrationService.java": "...java source...", '
    '"src/main/java/com/example/migration/RecordParser.java": "...optional java source...", '
    '"src/main/java/com/example/migration/RecordFormatter.java": "...optional java source..."}}'
)


def extract_java_files_from_response(response: str) -> dict[str, str]:
    candidates = [response.strip(), _strip_fence(response.strip())]
    start = response.find("{")
    end = response.rfind("}")
    if 0 <= start < end:
        candidates.append(response[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
            continue
        files = data["files"]
        if not files:
            raise ValueError("model response files object must not be empty")
        if not all(isinstance(path, str) and isinstance(source, str) for path, source in files.items()):
            raise ValueError("model response files entries must map paths to Java source strings")
        safety_ok, safety_error = validate_java_edits(files)
        if not safety_ok:
            raise ValueError(safety_error or "model response Java files failed validation")
        return dict(files)

    raise ValueError("model response did not contain JSON with a files object")


def run_model_rollout(
    task: TaskInstance,
    provider: TextProvider,
) -> dict[str, Any]:
    env, ticket, context, steps, record = _prepare_java_rollout(task)

    prompt = build_migration_prompt(ticket, context)
    response = provider.generate(prompt)
    model_turns = [{"provider": provider.name, "prompt": prompt, "response": response}]
    try:
        files = extract_java_files_from_response(response)
    except ValueError as exc:
        return _failed_rollout(provider.name, task, ticket, steps, model_turns, str(exc))

    edit_error = _apply_java_files(record, files)
    if edit_error is not None:
        return _failed_rollout(provider.name, task, ticket, steps, model_turns, edit_error)

    model_turns[-1]["file_chars"] = _file_chars(files)
    visible = record("run_junit_tests", {})
    final = record("submit_final", {})

    return _rollout_payload(provider.name, task, ticket, model_turns, visible, final, steps)


def run_model_repair_rollout(
    task: TaskInstance,
    provider: TextProvider,
    max_repairs: int = 1,
) -> dict[str, Any]:
    env, ticket, context, steps, record = _prepare_java_rollout(task)
    model_turns: list[dict[str, Any]] = []

    prompt = build_migration_prompt(ticket, context)
    response = provider.generate(prompt)
    try:
        files = extract_java_files_from_response(response)
    except ValueError as exc:
        model_turns.append({"provider": provider.name, "prompt": prompt, "response": response})
        return _failed_rollout(provider.name, task, ticket, steps, model_turns, str(exc))

    model_turns.append({"provider": provider.name, "prompt": prompt, "response": response, "file_chars": _file_chars(files)})
    edit_error = _apply_java_files(record, files)
    if edit_error is not None:
        return _failed_rollout(provider.name, task, ticket, steps, model_turns, edit_error)
    visible = record("run_junit_tests", {})

    for _ in range(max_repairs):
        if visible.get("pass_rate") == 1.0:
            break
        diagnostics = _inspect_java_failures(record, visible)
        repair_prompt = build_repair_prompt(ticket, context, files, visible, diagnostics)
        response = provider.generate(repair_prompt)
        try:
            files = extract_java_files_from_response(response)
        except ValueError as exc:
            model_turns.append({"provider": provider.name, "prompt": repair_prompt, "response": response})
            return _failed_rollout(provider.name, task, ticket, steps, model_turns, str(exc))

        model_turns.append({"provider": provider.name, "prompt": repair_prompt, "response": response, "file_chars": _file_chars(files)})
        edit_error = _apply_java_files(record, files)
        if edit_error is not None:
            return _failed_rollout(provider.name, task, ticket, steps, model_turns, edit_error)
        visible = record("run_junit_tests", {})

    final = record("submit_final", {})
    return _rollout_payload(provider.name, task, ticket, model_turns, visible, final, steps)


def _prepare_java_rollout(
    task: TaskInstance,
) -> tuple[LegacyCobolEnvironment, dict[str, Any], dict[str, Any], list[dict[str, Any]], Callable[[str, dict[str, Any]], dict[str, Any]]]:
    env = LegacyCobolEnvironment()
    reset_observation = env.reset(task_id=task.task_id)
    ticket = reset_observation.result["ticket"]
    steps: list[dict[str, Any]] = []
    context: dict[str, Any] = {
        "cobol_files": {},
        "copybooks": {},
        "layouts": {},
        "business_rules": [],
        "java_metadata": {},
    }

    def record(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result, reward, done = call_tool(env, tool_name, **arguments)
        steps.append(
            {
                "tool_name": tool_name,
                "arguments": _safe_arguments(arguments),
                "reward": reward,
                "done": done,
                "result": result,
            }
        )
        return result

    for filename in ticket["available_files"]:
        result = record("read_cobol_file", {"filename": filename})
        context["cobol_files"][filename] = result["content"]
    for filename in ticket["available_copybooks"]:
        copybook = record("read_copybook", {"filename": filename})
        layout = record("parse_copybook_layout", {"filename": filename})
        context["copybooks"][filename] = copybook["content"]
        context["layouts"][filename] = layout
    rules = record("inspect_business_rules", {})
    context["business_rules"] = rules["rules"]
    context["java_metadata"] = record("get_source_to_java_metadata", {})
    record("generate_java_skeleton", {})

    return env, ticket, context, steps, record


def _apply_java_files(record: Callable[[str, dict[str, Any]], dict[str, Any]], files: dict[str, str]) -> str | None:
    for path, content in files.items():
        edited = record("edit_java_file", {"path": path, "content": content})
        if not edited.get("ok", False):
            return edited.get("error", f"edit_java_file failed for {path}")
    return None


def _inspect_java_failures(record: Callable[[str, dict[str, Any]], dict[str, Any]], visible: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = []
    failures = visible.get("failures") or []
    if not failures:
        diagnostics.append(record("inspect_test_failure", {}))
        return diagnostics
    for failure in failures[:2]:
        case_id = failure.get("case_id")
        arguments = {"case_id": case_id} if case_id else {}
        diagnostics.append(record("inspect_test_failure", arguments))
    return diagnostics


def _rollout_payload(
    policy_name: str,
    task: TaskInstance,
    ticket: dict[str, Any],
    model_turns: list[dict[str, Any]],
    visible: dict[str, Any],
    final: dict[str, Any],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "policy": policy_name,
        "task_id": task.task_id,
        "family_id": task.family_id,
        "ticket": ticket,
        "model_turns": model_turns,
        "visible": {
            "passed": visible.get("passed", 0),
            "total": visible.get("total", 0),
            "pass_rate": visible.get("pass_rate", 0.0),
            "failures": visible.get("failures", []),
        },
        "final": {
            "public_score": final.get("public_score", 0.0),
            "accepted": final.get("accepted", False),
            "components": final.get("components", {}),
            "hidden_passed": final.get("hidden_passed"),
            "hidden_total": final.get("hidden_total"),
            "fresh_passed": final.get("fresh_passed"),
            "fresh_total": final.get("fresh_total"),
        },
        "steps": steps,
    }


def _failed_rollout(
    policy_name: str,
    task: TaskInstance,
    ticket: dict[str, Any],
    steps: list[dict[str, Any]],
    model_turns: list[dict[str, Any]],
    error: str,
) -> dict[str, Any]:
    return {
        "policy": policy_name,
        "task_id": task.task_id,
        "family_id": task.family_id,
        "ticket": ticket,
        "model_turns": model_turns,
        "visible": {"passed": 0, "total": 0, "pass_rate": 0.0, "failures": []},
        "final": {
            "public_score": 0.0,
            "accepted": False,
            "components": {},
            "hidden_passed": None,
            "hidden_total": None,
            "fresh_passed": None,
            "fresh_total": None,
            "error": error,
        },
        "steps": steps,
        "error": error,
    }


def build_migration_prompt(ticket: dict[str, Any], context: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            "You are performing COBOL-to-Java modernization.",
            f"Return only JSON in this shape: {JAVA_JSON_SCHEMA_TEXT}",
            "The files object must only contain allowed editable Java source paths.",
            "Do not edit tests, pom.xml, generated harness files, or files outside src/main/java/com/example/migration/.",
            "Use package com.example.migration and implement public String migrate(String inputRecord) on MigrationService.",
            "Use BigDecimal for implied decimals, RoundingMode.HALF_UP when COBOL uses rounded arithmetic, and exact fixed-width output.",
            f"Ticket:\n{json.dumps(ticket, indent=2)}",
            f"COBOL files:\n{json.dumps(context['cobol_files'], indent=2)}",
            f"Copybooks:\n{json.dumps(context['copybooks'], indent=2)}",
            f"Parsed layouts:\n{json.dumps(context['layouts'], indent=2)}",
            f"Business rules:\n{json.dumps(context['business_rules'], indent=2)}",
            f"Java metadata:\n{json.dumps(context.get('java_metadata', {}), indent=2)}",
        ]
    )


def build_repair_prompt(
    ticket: dict[str, Any],
    context: dict[str, Any],
    previous_files: dict[str, str],
    visible: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> str:
    return "\n\n".join(
        [
            "Repair the COBOL-to-Java migration after visible JUnit feedback.",
            f"Return only JSON in this shape: {JAVA_JSON_SCHEMA_TEXT}",
            "Keep package com.example.migration and public String migrate(String inputRecord).",
            "Use BigDecimal for implied decimals and preserve exact fixed-width output.",
            "Do not edit tests, pom.xml, or generated harness files.",
            f"Ticket:\n{json.dumps(ticket, indent=2)}",
            f"COBOL files:\n{json.dumps(context['cobol_files'], indent=2)}",
            f"Copybooks:\n{json.dumps(context['copybooks'], indent=2)}",
            f"Parsed layouts:\n{json.dumps(context['layouts'], indent=2)}",
            f"Business rules:\n{json.dumps(context['business_rules'], indent=2)}",
            f"Java metadata:\n{json.dumps(context.get('java_metadata', {}), indent=2)}",
            f"Previous Java files:\n{json.dumps(previous_files, indent=2)}",
            f"Visible JUnit failures:\n{json.dumps(visible.get('failures', []), indent=2)}",
            f"Visible JUnit diagnostics:\n{json.dumps(diagnostics, indent=2)}",
        ]
    )


def _safe_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    saved_arguments = dict(arguments)
    if "content" in saved_arguments:
        saved_arguments["content_chars"] = len(saved_arguments.pop("content"))
    if "code" in saved_arguments:
        saved_arguments["code_chars"] = len(saved_arguments.pop("code"))
    return saved_arguments


def _file_chars(files: dict[str, str]) -> int:
    return sum(len(source) for source in files.values())


def _strip_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)

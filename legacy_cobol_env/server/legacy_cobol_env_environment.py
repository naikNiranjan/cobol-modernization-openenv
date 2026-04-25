"""Legacy COBOL Migration Workbench OpenEnv environment."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import uuid4

from fastmcp import FastMCP
from fastmcp.client.client import CallToolResult
from mcp.types import TextContent
from openenv.core.env_server.mcp_environment import MCPEnvironment
from openenv.core.env_server.mcp_types import CallToolObservation
from openenv.core.env_server.types import Action, Observation

try:
    from ..models import (
        FinalSubmissionResult,
        JavaFinalSubmissionResult,
        JavaRewardComponents,
        LegacyCobolState,
        RewardComponents,
        TerminalStepResult,
    )
    from .java_runner import (
        ALLOWED_JAVA_PATHS,
        TEMPLATE_DIR,
        JavaEvaluationResult,
        evaluate_java_files,
        validate_edit_path,
        validate_java_edits,
    )
    from .sandbox import EvaluationResult, evaluate_code
    from .task_bank import generate_fresh_tests, load_task
except ImportError:
    from models import (
        FinalSubmissionResult,
        JavaFinalSubmissionResult,
        JavaRewardComponents,
        LegacyCobolState,
        RewardComponents,
        TerminalStepResult,
    )
    from server.java_runner import (
        ALLOWED_JAVA_PATHS,
        TEMPLATE_DIR,
        JavaEvaluationResult,
        evaluate_java_files,
        validate_edit_path,
        validate_java_edits,
    )
    from server.sandbox import EvaluationResult, evaluate_code
    from server.task_bank import generate_fresh_tests, load_task


MAX_STEPS = 12


class LegacyCobolEnvironment(MCPEnvironment):
    """Tool-mediated migration environment for legacy modernization tasks."""

    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self) -> None:
        self._task = load_task()
        self._state = LegacyCobolState(episode_id=str(uuid4()))
        self._drafts: dict[int, str] = {}
        self._java_drafts: dict[int, dict[str, str]] = {}
        self._last_visible_results: dict[str, EvaluationResult] = {}
        self._last_java_visible_results: dict[str, JavaEvaluationResult] = {}
        self._last_reward = 0.0
        self._last_summary = "Environment initialized."

        mcp = FastMCP("legacy_cobol_env")

        @mcp.tool
        def read_cobol_file(filename: str) -> dict[str, Any]:
            """Read a COBOL source artifact for the current migration ticket."""
            return self._read_cobol_file(filename)

        @mcp.tool
        def read_copybook(filename: str) -> dict[str, Any]:
            """Read a COBOL copybook artifact for the current migration ticket."""
            return self._read_copybook(filename)

        @mcp.tool
        def parse_copybook_layout(filename: str) -> dict[str, Any]:
            """Return structured offsets and types for a copybook."""
            return self._parse_copybook_layout(filename)

        @mcp.tool
        def inspect_business_rules() -> dict[str, Any]:
            """Inspect business rules inferred during task authoring."""
            return self._inspect_business_rules()

        @mcp.tool
        def get_source_to_java_metadata() -> dict[str, Any]:
            """Return Java interface, file, layout, and type metadata."""
            return self._get_source_to_java_metadata()

        @mcp.tool
        def generate_java_skeleton() -> dict[str, Any]:
            """Initialize editable Java source files from templates."""
            return self._generate_java_skeleton()

        @mcp.tool
        def read_java_file(path: str) -> dict[str, Any]:
            """Read one editable Java source file from the current skeleton."""
            return self._read_java_file(path)

        @mcp.tool
        def edit_java_file(path: str, content: str) -> dict[str, Any]:
            """Edit one allowed Java source file and record a Java draft."""
            return self._edit_java_file(path, content)

        @mcp.tool
        def run_junit_tests(draft_id: int | None = None) -> dict[str, Any]:
            """Run visible JUnit tests for the current or specified Java draft."""
            return self._run_junit_tests(draft_id=draft_id)

        @mcp.tool
        def inspect_test_failure(case_id: str | None = None) -> dict[str, Any]:
            """Inspect the latest failed visible Java test case."""
            return self._inspect_test_failure(case_id=case_id)

        @mcp.tool
        def write_python_solution(code: str) -> dict[str, Any]:
            """Store a candidate Python migration solution."""
            return self._write_python_solution(code)

        @mcp.tool
        def run_visible_tests(draft_id: int | None = None) -> dict[str, Any]:
            """Run visible tests against the current or specified draft."""
            return self._run_visible_tests(draft_id=draft_id)

        @mcp.tool
        def inspect_diff(case_id: str) -> dict[str, Any]:
            """Inspect a structured diff for a failed visible test case."""
            return self._inspect_diff(case_id)

        @mcp.tool
        def submit_final(draft_id: int | None = None) -> dict[str, Any]:
            """Submit the current or specified draft for hidden and fresh scoring."""
            return self._submit_final(draft_id=draft_id)

        super().__init__(mcp)

    def reset(
        self,
        seed: int | None = None,
        episode_id: str | None = None,
        **kwargs: Any,
    ) -> Observation:
        self._task = load_task(seed=seed, task_id=kwargs.get("task_id"))
        self._drafts = {}
        self._java_drafts = {}
        self._last_visible_results = {}
        self._last_java_visible_results = {}
        self._last_reward = 0.0
        self._last_summary = "Ready for migration."
        self._state = LegacyCobolState(
            episode_id=episode_id or str(uuid4()),
            step_count=0,
            task_id=self._task.task_id,
            done=False,
            last_result_summary=self._last_summary,
        )
        return CallToolObservation(
            tool_name="episode_start",
            result={"ticket": self._initial_ticket()},
            done=False,
            reward=0.0,
        )

    def step(
        self,
        action: Action,
        timeout_s: float | None = None,
        **kwargs: Any,
    ) -> Observation:
        blocked = self._blocked_step_observation(action)
        if blocked is not None:
            return blocked
        self._state.step_count += 1
        observation = super().step(action, timeout_s=timeout_s, **kwargs)
        observation.reward = self._last_reward
        observation.done = self._state.done
        return observation

    async def step_async(
        self,
        action: Action,
        timeout_s: float | None = None,
        **kwargs: Any,
    ) -> Observation:
        blocked = self._blocked_step_observation(action)
        if blocked is not None:
            return blocked
        self._state.step_count += 1
        observation = await super().step_async(action, timeout_s=timeout_s, **kwargs)
        observation.reward = self._last_reward
        observation.done = self._state.done
        return observation

    def _step_impl(
        self,
        action: Action,
        timeout_s: float | None = None,
        **kwargs: Any,
    ) -> Observation:
        self._set_outcome("unsupported_action", 0.0, "Use MCP CallToolAction.")
        return Observation(
            done=self._state.done,
            reward=0.0,
            metadata={"error": f"Unsupported action type: {type(action).__name__}"},
        )

    @property
    def state(self) -> LegacyCobolState:
        return self._state

    def _initial_ticket(self) -> dict[str, Any]:
        return {
            "task_id": self._task.task_id,
            "family_id": self._task.family_id,
            "domain": self._task.domain,
            "ticket": self._task.ticket,
            "available_files": sorted(self._task.cobol_files),
            "available_copybooks": sorted(self._task.copybooks),
            "expected_callable": self._task.expected_callable,
            "visible_tests": len(self._task.visible_tests),
            "hidden_tests": len(self._task.hidden_tests),
            "input_width": self._task.metadata["input_width"],
            "output_width": self._task.metadata["output_width"],
            "max_steps": MAX_STEPS,
            "allowed_tools": [
                "read_cobol_file",
                "read_copybook",
                "parse_copybook_layout",
                "inspect_business_rules",
                "get_source_to_java_metadata",
                "generate_java_skeleton",
                "read_java_file",
                "edit_java_file",
                "run_junit_tests",
                "inspect_test_failure",
                "write_python_solution",
                "run_visible_tests",
                "inspect_diff",
                "submit_final",
            ],
        }

    def _set_outcome(
        self,
        tool_name: str,
        reward: float,
        summary: str,
        done: bool | None = None,
    ) -> None:
        self._last_reward = reward
        self._last_summary = summary
        self._state.last_tool = tool_name
        self._state.last_result_summary = summary
        if done is not None:
            self._state.done = done

    def _blocked_step_observation(self, action: Action) -> CallToolObservation | None:
        if self._state.done:
            return self._terminal_noop_observation(
                action,
                "episode is terminal; action was not executed",
            )

        if self._state.step_count >= MAX_STEPS:
            self._state.done = True
            self._last_reward = 0.0
            self._last_summary = "Max steps exceeded."
            self._state.last_result_summary = self._last_summary
            return self._terminal_noop_observation(
                action,
                f"max_steps={MAX_STEPS} exceeded; action was not executed",
            )

        return None

    def _terminal_noop_observation(self, action: Action, error: str) -> CallToolObservation:
        tool_name = getattr(action, "tool_name", type(action).__name__)
        return CallToolObservation(
            tool_name=tool_name,
            result=self._tool_result(TerminalStepResult(error=error).model_dump()),
            done=True,
            reward=0.0,
        )

    def _tool_result(self, data: dict[str, Any]) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text=str(data))],
            structured_content={"result": data},
            meta=None,
            data=data,
            is_error=not data.get("ok", True),
        )

    def _read_cobol_file(self, filename: str) -> dict[str, Any]:
        content = self._task.cobol_files.get(filename)
        if content is None:
            self._set_outcome("read_cobol_file", 0.0, "Unknown COBOL file.")
            return {"ok": False, "error": f"unknown COBOL file: {filename}"}

        if filename not in self._state.files_read:
            self._state.files_read.append(filename)
        self._set_outcome("read_cobol_file", 0.02, f"Read {filename}.")
        return {"ok": True, "filename": filename, "content": content, "truncated": False}

    def _read_copybook(self, filename: str) -> dict[str, Any]:
        content = self._task.copybooks.get(filename)
        if content is None:
            self._set_outcome("read_copybook", 0.0, "Unknown copybook.")
            return {"ok": False, "error": f"unknown copybook: {filename}"}

        if filename not in self._state.copybooks_read:
            self._state.copybooks_read.append(filename)
        self._set_outcome("read_copybook", 0.02, f"Read {filename}.")
        return {"ok": True, "filename": filename, "content": content}

    def _parse_copybook_layout(self, filename: str) -> dict[str, Any]:
        if filename not in self._task.copybooks:
            self._set_outcome("parse_copybook_layout", 0.0, "Unknown copybook.")
            return {"ok": False, "error": f"unknown copybook: {filename}"}

        if filename not in self._state.layouts_parsed:
            self._state.layouts_parsed.append(filename)
        self._set_outcome(
            "parse_copybook_layout",
            0.03,
            f"Parsed layout for {filename}.",
        )
        return {
            "ok": True,
            "filename": filename,
            "record_name": self._task.metadata["record_name"],
            "total_width": self._task.metadata["input_width"],
            "fields": self._task.metadata["copybook_layout"],
        }

    def _inspect_business_rules(self) -> dict[str, Any]:
        self._set_outcome("inspect_business_rules", 0.01, "Inspected business rules.")
        return {"ok": True, "rules": self._task.metadata["business_rules"]}

    def _get_source_to_java_metadata(self) -> dict[str, Any]:
        self._set_outcome("get_source_to_java_metadata", 0.02, "Returned Java metadata.")
        return {
            "ok": True,
            "package_name": "com.example.migration",
            "required_class": "MigrationService",
            "required_method": "public String migrate(String inputRecord)",
            "allowed_editable_paths": sorted(ALLOWED_JAVA_PATHS),
            "input_width": self._task.metadata["input_width"],
            "output_width": self._task.metadata["output_width"],
            "copybook_field_mappings": self._java_field_mappings(self._task.metadata["copybook_layout"]),
            "output_layout": self._task.metadata["output_layout"],
            "java_type_hints": self._java_type_hints(),
            "fixed_width_contract": {
                "input_record_name": self._task.metadata["record_name"],
                "output_layout": self._task.metadata["output_layout"],
            },
        }

    def _generate_java_skeleton(self) -> dict[str, Any]:
        java_files = {
            path: (TEMPLATE_DIR / path).read_text(encoding="utf-8")
            for path in sorted(ALLOWED_JAVA_PATHS)
        }
        self._state.java_skeleton_generated = True
        self._state.java_files = java_files
        self._state.java_draft_id = None
        self._state.java_draft_count = 0
        self._state.java_visible_runs = 0
        self._state.last_java_visible_result = None
        self._state.last_java_failure_diagnostics = []
        self._state.java_final_eligible = False
        self._java_drafts = {}
        self._last_java_visible_results = {}
        self._set_outcome("generate_java_skeleton", 0.03, "Generated Java skeleton.")
        return {
            "ok": True,
            "package_name": "com.example.migration",
            "required_class": "MigrationService",
            "editable_files": sorted(java_files),
            "submit_final": "After edit_java_file, submit_final with no draft_id scores the latest Java draft; explicit Python draft_id preserves Python scoring.",
        }

    def _read_java_file(self, path: str) -> dict[str, Any]:
        if not self._state.java_skeleton_generated:
            self._set_outcome("read_java_file", 0.0, "Java skeleton has not been generated.")
            return {"ok": False, "error": "generate_java_skeleton must be called before read_java_file"}

        path_ok, path_error = validate_edit_path(path)
        if not path_ok:
            self._set_outcome("read_java_file", 0.0, "Invalid Java file path.")
            return {"ok": False, "error": path_error}

        content = self._state.java_files.get(path)
        if content is None:
            self._set_outcome("read_java_file", 0.0, "Java file is not initialized.")
            return {"ok": False, "error": f"java file is not initialized: {path}"}

        self._set_outcome("read_java_file", 0.01, f"Read Java file {path}.")
        return {"ok": True, "path": path, "content": content}

    def _edit_java_file(self, path: str, content: str) -> dict[str, Any]:
        if not self._state.java_skeleton_generated:
            self._set_outcome("edit_java_file", 0.0, "Java skeleton has not been generated.")
            return {"ok": False, "error": "generate_java_skeleton must be called before edit_java_file"}

        path_ok, path_error = validate_edit_path(path)
        if not path_ok:
            self._set_outcome("edit_java_file", 0.0, "Invalid Java file path.")
            return {"ok": False, "error": path_error}

        candidate_files = dict(self._state.java_files)
        candidate_files[path] = content
        safety_ok, safety_error = validate_java_edits(candidate_files)
        if not safety_ok:
            self._set_outcome("edit_java_file", 0.0, "Java edit failed validation.")
            return {"ok": False, "path": path, "safety_ok": False, "error": safety_error}

        draft_id = self._state.java_draft_count + 1
        self._state.java_files = candidate_files
        self._state.java_draft_id = draft_id
        self._state.java_draft_count = draft_id
        self._state.last_java_visible_result = None
        self._state.last_java_failure_diagnostics = []
        self._state.java_final_eligible = False
        self._java_drafts[draft_id] = dict(candidate_files)

        self._set_outcome("edit_java_file", 0.03, f"Stored Java draft {draft_id}.")
        return {
            "ok": True,
            "path": path,
            "draft_id": draft_id,
            "version": draft_id,
            "safety_ok": True,
            "editable_files": sorted(candidate_files),
            "submit_final": "submit_final with no draft_id scores the latest Java draft; explicit Python draft_id preserves Python scoring.",
        }

    def _run_junit_tests(self, draft_id: int | None = None) -> dict[str, Any]:
        selected_id, files_or_error = self._select_java_files(draft_id)
        if selected_id is None:
            self._set_outcome("run_junit_tests", 0.0, "No Java draft available.")
            return {"ok": False, "error": files_or_error}

        result = evaluate_java_files(files_or_error, self._task.visible_tests)
        self._last_java_visible_results[str(selected_id)] = result
        self._state.java_visible_runs += 1
        self._state.last_java_visible_result = self._java_result_payload(result)
        self._state.last_java_failure_diagnostics = self._java_failure_diagnostics(result)
        self._state.java_final_eligible = (
            result.safety_ok
            and result.compile_ok
            and not result.timed_out
            and result.total > 0
            and result.passed == result.total
        )

        reward = 0.05 * result.pass_rate if result.compile_ok and result.safety_ok else 0.0
        self._set_outcome(
            "run_junit_tests",
            reward,
            f"Visible JUnit tests: {result.passed}/{result.total}.",
        )
        return {
            "ok": result.safety_ok and result.compile_ok and not result.timed_out,
            "draft_id": selected_id,
            "passed": result.passed,
            "total": result.total,
            "pass_rate": result.pass_rate,
            "compile_ok": result.compile_ok,
            "safety_ok": result.safety_ok,
            "timed_out": result.timed_out,
            "error": result.error,
            "failures": self._java_visible_failures(result),
            "java_final_eligible": self._state.java_final_eligible,
            "submit_final": "submit_final with no draft_id scores the latest Java draft; explicit Python draft_id preserves Python scoring.",
        }

    def _inspect_test_failure(self, case_id: str | None = None) -> dict[str, Any]:
        latest = self._latest_java_visible_result()
        if latest is None:
            self._set_outcome("inspect_test_failure", 0.0, "No Java visible test run to inspect.")
            return {"ok": False, "error": "run_junit_tests before inspecting Java test failures"}

        failed_cases = [item for item in latest.case_results if not item.passed]
        if not failed_cases:
            diagnostics = self._state.last_java_failure_diagnostics
            if diagnostics and case_id is None:
                self._set_outcome("inspect_test_failure", 0.01, "Inspected Java runner failure.")
                return {"ok": True, "diagnostic": diagnostics[0], "field_diffs": []}
            self._set_outcome("inspect_test_failure", 0.0, "No failed Java visible case.")
            return {"ok": False, "error": "no failed visible Java test case is available"}

        case = failed_cases[0] if case_id is None else next((item for item in failed_cases if item.case_id == case_id), None)
        if case is None:
            self._set_outcome("inspect_test_failure", 0.0, "Unknown failed Java case.")
            return {"ok": False, "error": f"unknown failed Java case: {case_id}"}

        field_diffs = self._field_diffs(case)
        self._set_outcome("inspect_test_failure", 0.02, f"Inspected Java test failure for {case.case_id}.")
        return {
            "ok": True,
            "case_id": case.case_id,
            "passed": False,
            "failure_type": case.failure_type,
            "expected": case.expected,
            "actual": case.actual,
            "expected_summary": self._summarize_output(case.expected),
            "actual_summary": self._summarize_output(case.actual),
            "error": case.error,
            "field_diffs": field_diffs,
        }

    def _write_python_solution(self, code: str) -> dict[str, Any]:
        draft_id = len(self._drafts) + 1
        self._drafts[draft_id] = code
        self._state.draft_count = len(self._drafts)

        syntax_ok = True
        safety_ok = True
        safety_error = None
        try:
            from .sandbox import check_candidate_safety
        except ImportError:
            from server.sandbox import check_candidate_safety

        safety_ok, safety_error = check_candidate_safety(code)
        if safety_error and safety_error.startswith("syntax error"):
            syntax_ok = False

        reward = 0.02 if syntax_ok and safety_ok else 0.0
        summary = f"Stored draft {draft_id}."
        if not syntax_ok or not safety_ok:
            summary = f"Stored draft {draft_id}, but safety check failed."
        self._set_outcome("write_python_solution", reward, summary)
        return {
            "ok": True,
            "draft_id": draft_id,
            "syntax_ok": syntax_ok,
            "safety_ok": safety_ok,
            "error": safety_error,
        }

    def _run_visible_tests(self, draft_id: int | None = None) -> dict[str, Any]:
        selected_id, code_or_error = self._select_draft(draft_id)
        if selected_id is None:
            self._set_outcome("run_visible_tests", 0.0, "No draft available.")
            return {"ok": False, "error": code_or_error}

        result = evaluate_code(code_or_error, self._task.visible_tests)
        self._last_visible_results[str(selected_id)] = result
        self._state.visible_runs += 1
        self._state.best_visible_pass_rate = max(
            self._state.best_visible_pass_rate,
            result.pass_rate,
        )
        reward = 0.05 * result.pass_rate
        self._set_outcome(
            "run_visible_tests",
            reward,
            f"Visible tests: {result.passed}/{result.total}.",
        )
        return {
            "ok": result.safety_ok and result.interface_ok and not result.timed_out,
            "draft_id": selected_id,
            "passed": result.passed,
            "total": result.total,
            "pass_rate": result.pass_rate,
            "syntax_ok": result.syntax_ok,
            "safety_ok": result.safety_ok,
            "interface_ok": result.interface_ok,
            "timed_out": result.timed_out,
            "error": result.error,
            "failures": self._visible_failures(result),
        }

    def _inspect_diff(self, case_id: str) -> dict[str, Any]:
        latest = self._latest_visible_result()
        if latest is None:
            self._set_outcome("inspect_diff", 0.0, "No visible test run to inspect.")
            return {"ok": False, "error": "run visible tests before inspecting diffs"}

        case = next((item for item in latest.case_results if item.case_id == case_id), None)
        if case is None:
            self._set_outcome("inspect_diff", 0.0, "Unknown visible case.")
            return {"ok": False, "error": f"unknown visible case: {case_id}"}
        if case.passed:
            self._set_outcome("inspect_diff", 0.0, "Case already passed.")
            return {"ok": True, "case_id": case_id, "passed": True, "field_diffs": []}

        field_diffs = self._field_diffs(case)
        self._set_outcome("inspect_diff", 0.02, f"Inspected diff for {case_id}.")
        return {
            "ok": True,
            "case_id": case_id,
            "passed": False,
            "input_summary": case.input_summary,
            "error": case.error,
            "field_diffs": field_diffs,
        }

    def _submit_final(self, draft_id: int | None = None) -> dict[str, Any]:
        if draft_id is None and self._state.java_draft_id is not None:
            return self._submit_java_final()
        return self._submit_python_final(draft_id=draft_id)

    def _submit_python_final(self, draft_id: int | None = None) -> dict[str, Any]:
        selected_id, code_or_error = self._select_draft(draft_id)
        if selected_id is None:
            self._set_outcome("submit_final", 0.0, "No draft available.", done=True)
            return {"ok": False, "accepted": False, "error": code_or_error}

        hidden = evaluate_code(code_or_error, self._task.hidden_tests)
        fresh_tests = generate_fresh_tests(self._task)
        fresh = evaluate_code(code_or_error, fresh_tests)

        components = self._reward_components(hidden, fresh)
        components["anti_hardcoding"] = min(
            float(components.get("anti_hardcoding", 0.0)),
            self._anti_hardcoding_score(code_or_error, fresh),
        )
        components = RewardComponents.model_validate(
            {key: self._clamp_score(value) for key, value in components.items()}
        ).model_dump()
        final_reward = round(
            0.55 * components["hidden_correctness"]
            + 0.15 * components["fresh_correctness"]
            + 0.10 * components["interface_contract"]
            + 0.08 * components["type_and_layout_fidelity"]
            + 0.07 * components["anti_hardcoding"]
            + 0.05 * components["safety"],
            4,
        )
        final_reward = self._clamp_score(final_reward)

        self._state.final_score = final_reward
        self._state.reward_components = components
        self._set_outcome(
            "submit_final",
            final_reward,
            f"Final score {final_reward:.3f}.",
            done=True,
        )
        return FinalSubmissionResult(
            ok=True,
            accepted=final_reward >= 0.80,
            episode_done=True,
            public_score=final_reward,
            components=RewardComponents.model_validate(components),
            hidden_passed=hidden.passed,
            hidden_total=hidden.total,
            fresh_passed=fresh.passed,
            fresh_total=fresh.total,
            notes="Hidden and fresh case details are not revealed to the agent.",
        ).model_dump()

    def _submit_java_final(self) -> dict[str, Any]:
        selected_id, files_or_error = self._select_java_files(self._state.java_draft_id)
        if selected_id is None:
            self._set_outcome("submit_final", 0.0, "No Java draft available.", done=True)
            return {"ok": False, "accepted": False, "error": files_or_error}

        hidden = evaluate_java_files(files_or_error, self._task.hidden_tests)
        fresh_tests = generate_fresh_tests(self._task)
        fresh = evaluate_java_files(files_or_error, fresh_tests)

        components = self._java_reward_components(hidden, fresh, files_or_error)
        components = JavaRewardComponents.model_validate(
            {key: self._clamp_score(value) for key, value in components.items()}
        ).model_dump()
        final_reward = round(
            0.12 * components["java_compile"]
            + 0.45 * components["hidden_junit_pass_rate"]
            + 0.15 * components["fresh_junit_pass_rate"]
            + 0.10 * components["type_and_decimal_fidelity"]
            + 0.08 * components["layout_fidelity"]
            + 0.05 * components["anti_hardcoding"]
            + 0.05 * components["safety"],
            4,
        )
        final_reward = self._clamp_score(final_reward)

        self._state.final_score = final_reward
        self._state.reward_components = components
        self._state.java_final_eligible = final_reward >= 0.80
        self._set_outcome(
            "submit_final",
            final_reward,
            f"Java final score {final_reward:.3f}.",
            done=True,
        )
        return JavaFinalSubmissionResult(
            ok=True,
            accepted=final_reward >= 0.80,
            episode_done=True,
            public_score=final_reward,
            components=JavaRewardComponents.model_validate(components),
            draft_id=selected_id,
            hidden_passed=hidden.passed,
            hidden_total=hidden.total,
            fresh_passed=fresh.passed,
            fresh_total=fresh.total,
            notes="Java final scoring used hidden and fresh JUnit tests; hidden and fresh case details are not revealed.",
        ).model_dump()

    def _select_draft(self, draft_id: int | None) -> tuple[int | None, str]:
        if not self._drafts:
            return None, "write_python_solution must be called before evaluation"
        selected = draft_id or max(self._drafts)
        code = self._drafts.get(selected)
        if code is None:
            return None, f"unknown draft_id: {selected}"
        return selected, code

    def _select_java_files(self, draft_id: int | None) -> tuple[int | None, dict[str, str] | str]:
        if not self._state.java_skeleton_generated:
            return None, "generate_java_skeleton must be called before run_junit_tests"
        if draft_id is not None:
            files = self._java_drafts.get(draft_id)
            if files is None:
                return None, f"unknown Java draft_id: {draft_id}"
            return draft_id, files
        if self._state.java_draft_id is not None:
            files = self._java_drafts.get(self._state.java_draft_id)
            if files is not None:
                return self._state.java_draft_id, files
        return 0, dict(self._state.java_files)

    def _latest_visible_result(self) -> EvaluationResult | None:
        if not self._last_visible_results:
            return None
        latest_key = sorted(self._last_visible_results, key=int)[-1]
        return self._last_visible_results[latest_key]

    def _latest_java_visible_result(self) -> JavaEvaluationResult | None:
        if not self._last_java_visible_results:
            return None
        latest_key = sorted(self._last_java_visible_results, key=int)[-1]
        return self._last_java_visible_results[latest_key]

    def _java_result_payload(self, result: JavaEvaluationResult) -> dict[str, Any]:
        payload = asdict(result)
        payload["pass_rate"] = result.pass_rate
        return payload

    def _visible_failures(self, result: EvaluationResult) -> list[dict[str, Any]]:
        failures = []
        for item in result.case_results:
            if item.passed:
                continue
            failures.append(
                {
                    "case_id": item.case_id,
                    "input_summary": item.input_summary,
                    "expected_summary": self._summarize_output(item.expected),
                    "actual_summary": self._summarize_output(item.actual),
                    "error": item.error,
                }
            )
        return failures

    def _java_visible_failures(self, result: JavaEvaluationResult) -> list[dict[str, Any]]:
        failures = []
        for item in result.case_results:
            if item.passed:
                continue
            failures.append(
                {
                    "case_id": item.case_id,
                    "failure_type": item.failure_type,
                    "expected_summary": self._summarize_output(item.expected),
                    "actual_summary": self._summarize_output(item.actual),
                    "error": item.error,
                }
            )
        if not failures and result.error:
            failures.append(
                {
                    "case_id": None,
                    "failure_type": "runner_error",
                    "expected_summary": "visible JUnit execution",
                    "actual_summary": result.error,
                    "error": result.error,
                }
            )
        return failures

    def _java_failure_diagnostics(self, result: JavaEvaluationResult) -> list[dict[str, Any]]:
        return self._java_visible_failures(result)

    def _field_diffs(self, case: Any) -> list[dict[str, Any]]:
        if case.expected is None or case.actual is None:
            return [{"field": "runtime", "expected": case.expected, "actual": case.actual}]

        diffs = []
        for field in self._task.metadata["output_layout"]:
            expected = case.expected[field["start"] : field["end"]]
            actual = case.actual[field["start"] : field["end"]]
            if expected != actual:
                diffs.append(
                    {
                        "field": field["name"],
                        "expected": expected,
                        "actual": actual,
                        "hint": self._field_hint(field["name"]),
                    }
                )
        output_width = self._task.metadata["output_width"]
        if len(case.actual) != output_width:
            diffs.append(
                {
                    "field": "OUTPUT-RECORD",
                    "expected": f"{output_width} characters",
                    "actual": f"{len(case.actual)} characters",
                    "hint": "output must preserve the fixed-width record contract",
                }
            )
        return diffs

    def _reward_components(
        self,
        hidden: EvaluationResult,
        fresh: EvaluationResult,
    ) -> dict[str, float]:
        interface = 1.0 if hidden.interface_ok and fresh.interface_ok else 0.0
        safety = (
            1.0
            if hidden.safety_ok
            and fresh.safety_ok
            and not hidden.timed_out
            and not fresh.timed_out
            else 0.0
        )
        layout = self._layout_pass_rate(hidden)
        return {
            "hidden_correctness": round(hidden.pass_rate, 4),
            "fresh_correctness": round(fresh.pass_rate, 4),
            "interface_contract": interface,
            "type_and_layout_fidelity": round(layout, 4),
            "anti_hardcoding": round(fresh.pass_rate, 4),
            "safety": safety,
        }

    def _java_reward_components(
        self,
        hidden: JavaEvaluationResult,
        fresh: JavaEvaluationResult,
        files: dict[str, str],
    ) -> dict[str, float]:
        safety = (
            1.0
            if hidden.safety_ok
            and fresh.safety_ok
            and not hidden.timed_out
            and not fresh.timed_out
            else 0.0
        )
        layout = (self._layout_pass_rate(hidden) + self._layout_pass_rate(fresh)) / 2
        return {
            "java_compile": 1.0 if hidden.compile_ok and fresh.compile_ok else 0.0,
            "hidden_junit_pass_rate": round(hidden.pass_rate, 4),
            "fresh_junit_pass_rate": round(fresh.pass_rate, 4),
            "type_and_decimal_fidelity": self._java_type_and_decimal_fidelity(files),
            "layout_fidelity": round(layout, 4),
            "anti_hardcoding": self._java_anti_hardcoding_score(files, fresh),
            "safety": safety,
        }

    def _java_type_and_decimal_fidelity(self, files: dict[str, str]) -> float:
        decimal_fields = [
            field
            for field in self._task.metadata["copybook_layout"]
            if field.get("python_type") == "Decimal" or "V" in field.get("pic", "")
        ]
        if not decimal_fields:
            return 1.0

        source = self._java_source(files)
        if "BigDecimal" not in source:
            return 0.0

        rules_text = " ".join(self._task.metadata.get("reference_rules", [])).lower()
        if "round" in rules_text and "RoundingMode.HALF_UP" not in source:
            return 0.5
        return 1.0

    def _java_anti_hardcoding_score(self, files: dict[str, str], fresh: JavaEvaluationResult) -> float:
        if self._visible_literal_leaks(self._java_source(files)):
            return 0.0
        return round(fresh.pass_rate, 4)

    def _java_source(self, files: dict[str, str]) -> str:
        return "\n".join(files.get(path, "") for path in sorted(files))

    def _anti_hardcoding_score(self, code: str, fresh: EvaluationResult) -> float:
        if self._visible_literal_leaks(code):
            return 0.0
        return round(fresh.pass_rate, 4)

    def _visible_literal_leaks(self, code: str) -> list[str]:
        literals: set[str] = set()
        input_id_field = self._task.metadata["copybook_layout"][0]
        output_id_field = self._task.metadata["output_layout"][0]
        for case in self._task.visible_tests:
            literals.add(case.input_record)
            literals.add(case.expected_output)
            literals.add(case.input_record[input_id_field["start"] : input_id_field["end"]].strip())
            literals.add(case.expected_output[output_id_field["start"] : output_id_field["end"]].strip())

        return sorted(literal for literal in literals if len(literal) >= 5 and literal in code)

    def _clamp_score(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _layout_pass_rate(self, result: EvaluationResult) -> float:
        if result.total == 0:
            return 0.0
        ok = 0
        layout = self._task.metadata["output_layout"]
        numeric_names = set(self._task.metadata.get("numeric_output_fields", []))
        output_width = self._task.metadata["output_width"]
        fields_by_name = {item["name"]: item for item in layout}
        for item in result.case_results:
            if item.actual is None or len(item.actual) != output_width:
                continue
            numeric_ok = True
            for name in numeric_names:
                spec = fields_by_name[name]
                if not item.actual[spec["start"] : spec["end"]].isdigit():
                    numeric_ok = False
                    break
            if numeric_ok:
                ok += 1
        return ok / result.total

    def _summarize_output(self, output: str | None) -> str:
        if output is None:
            return "no output"
        output_width = self._task.metadata["output_width"]
        if len(output) != output_width:
            return f"length {len(output)} output: {output!r}"
        parts = []
        for spec in self._task.metadata["output_layout"][:4]:
            parts.append(f"{spec['name']}={output[spec['start']:spec['end']]}")
        return ", ".join(parts)

    def _field_hint(self, field_name: str) -> str:
        hints = dict(self._task.metadata.get("field_hints", {}))
        hints.update({
            "OUT-EMP-ID": "preserve the first 6 input bytes exactly",
            "OUT-EMP-NAME": "preserve/pad the 12-byte name field",
            "OUT-PAY-CATEGORY": "H >= 5000.00, M >= 2500.00, otherwise L",
        })
        return hints.get(field_name, "check fixed-width COBOL layout")

    def _java_field_mappings(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mappings = []
        for item in fields:
            mapped = dict(item)
            mapped["java_type"] = self._java_type_for_field(item)
            if item.get("scale") is not None:
                mapped["parse_hint"] = f"parse as implied decimal with scale {item['scale']} using BigDecimal"
            elif item.get("python_type") == "group":
                mapped["parse_hint"] = "parse nested OCCURS/group fields by fixed-width offsets"
            else:
                mapped["parse_hint"] = "parse by fixed-width substring offsets"
            mappings.append(mapped)
        return mappings

    def _java_type_hints(self) -> dict[str, Any]:
        copybook_hints = {
            item["name"]: {
                "java_type": self._java_type_for_field(item),
                "pic": item["pic"],
                "scale": item.get("scale"),
            }
            for item in self._task.metadata["copybook_layout"]
        }
        output_hints = {
            item["name"]: {
                "java_type": self._java_type_for_field(item),
                "pic": item["pic"],
                "fixed_width": item["length"],
            }
            for item in self._task.metadata["output_layout"]
        }
        return {
            "copybook_fields": copybook_hints,
            "output_fields": output_hints,
            "money_and_implied_decimals": "Use java.math.BigDecimal and RoundingMode.HALF_UP for PIC fields with implied decimals.",
            "fixed_width_strings": "Use substring offsets from copybook_field_mappings and pad/truncate output fields exactly.",
        }

    def _java_type_for_field(self, field: dict[str, Any]) -> str:
        if field.get("python_type") == "Decimal" or "V" in field.get("pic", ""):
            return "BigDecimal"
        if field.get("python_type") == "int":
            return "int"
        if field.get("python_type") == "group":
            return "List or fixed-offset helper"
        return "String"

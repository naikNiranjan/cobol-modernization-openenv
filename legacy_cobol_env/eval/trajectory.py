"""Reusable tool-call trajectory runner for local and model-driven policies."""

from __future__ import annotations

from typing import Any

from openenv.core.env_server.mcp_types import CallToolAction

from legacy_cobol_env.server.legacy_cobol_env_environment import LegacyCobolEnvironment
from legacy_cobol_env.server.task_bank import TaskInstance


def call_tool(env: LegacyCobolEnvironment, tool_name: str, **arguments: Any) -> tuple[dict[str, Any], float, bool]:
    observation = env.step(CallToolAction(tool_name=tool_name, arguments=arguments))
    return observation.result.data, observation.reward, observation.done


def run_solution_trajectory(
    policy_name: str,
    task: TaskInstance,
    files: dict[str, str],
) -> dict[str, Any]:
    env = LegacyCobolEnvironment()
    reset_observation = env.reset(task_id=task.task_id)
    ticket = reset_observation.result["ticket"]
    steps: list[dict[str, Any]] = []

    def record(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result, reward, done = call_tool(env, tool_name, **arguments)
        saved_arguments = dict(arguments)
        if "content" in saved_arguments:
            saved_arguments["content_chars"] = len(saved_arguments.pop("content"))
        steps.append(
            {
                "tool_name": tool_name,
                "arguments": saved_arguments,
                "reward": reward,
                "done": done,
                "result": result,
            }
        )
        return result

    for filename in ticket["available_files"]:
        record("read_cobol_file", {"filename": filename})
    for filename in ticket["available_copybooks"]:
        record("read_copybook", {"filename": filename})
        record("parse_copybook_layout", {"filename": filename})
    record("inspect_business_rules", {})
    record("get_source_to_java_metadata", {})
    record("generate_java_skeleton", {})
    for path, content in files.items():
        record("edit_java_file", {"path": path, "content": content})
    visible = record("run_junit_tests", {})
    final = record("submit_final", {})

    return {
        "policy": policy_name,
        "task_id": task.task_id,
        "family_id": task.family_id,
        "ticket": ticket,
        "visible": {
            "passed": visible["passed"],
            "total": visible["total"],
            "pass_rate": visible["pass_rate"],
            "failures": visible["failures"],
        },
        "final": {
            "public_score": final["public_score"],
            "accepted": final["accepted"],
            "components": final["components"],
            "hidden_passed": final["hidden_passed"],
            "hidden_total": final["hidden_total"],
            "fresh_passed": final["fresh_passed"],
            "fresh_total": final["fresh_total"],
        },
        "steps": steps,
    }

import asyncio

from fastapi.testclient import TestClient
from openenv.core.env_server.mcp_types import CallToolAction

from legacy_cobol_env.models import FinalSubmissionResult, RewardComponents
from legacy_cobol_env.server.app import app
from legacy_cobol_env.server.legacy_cobol_env_environment import (
    MAX_STEPS,
    LegacyCobolEnvironment,
)
from legacy_cobol_env.server.sandbox import CaseResult, EvaluationResult
from legacy_cobol_env.tests.test_environment import GOOD_SOLUTION


def call_obs(env: LegacyCobolEnvironment, tool_name: str, **arguments):
    return env.step(CallToolAction(tool_name=tool_name, arguments=arguments))


async def call_obs_async(env: LegacyCobolEnvironment, tool_name: str, **arguments):
    return await env.step_async(CallToolAction(tool_name=tool_name, arguments=arguments))


def result_data(observation):
    if hasattr(observation.result, "data"):
        return observation.result.data
    return observation.result


def test_thirteenth_action_exceeds_max_steps_without_executing_tool():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    for _ in range(MAX_STEPS):
        obs = call_obs(env, "read_cobol_file", filename="PAYROLL.cbl")
        assert obs.done is False

    blocked = call_obs(env, "write_python_solution", code=GOOD_SOLUTION)
    blocked_result = result_data(blocked)

    assert blocked.done is True
    assert blocked.reward == 0.0
    assert blocked_result["ok"] is False
    assert "max_steps" in blocked_result["error"]
    assert env.state.done is True
    assert env.state.step_count == MAX_STEPS
    assert env.state.draft_count == 0
    assert env.state.last_tool != "write_python_solution"


def test_post_done_steps_are_terminal_noops_without_state_mutation():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")

    written = result_data(call_obs(env, "write_python_solution", code=GOOD_SOLUTION))
    final_obs = call_obs(env, "submit_final", draft_id=written["draft_id"])
    assert final_obs.done is True

    state_before = env.state.model_dump()
    blocked = call_obs(env, "write_python_solution", code="def migrate(input_record):\n    return ''\n")
    blocked_result = result_data(blocked)

    assert blocked.done is True
    assert blocked.reward == 0.0
    assert blocked_result["ok"] is False
    assert "terminal" in blocked_result["error"]
    assert env.state.model_dump() == state_before


def test_final_reward_response_is_typed_and_clamped(monkeypatch):
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")
    written = result_data(call_obs(env, "write_python_solution", code=GOOD_SOLUTION))

    def out_of_bounds_components(hidden, fresh):
        return {
            "hidden_correctness": -0.25,
            "fresh_correctness": 1.25,
            "interface_contract": 2.0,
            "type_and_layout_fidelity": -1.0,
            "anti_hardcoding": 0.5,
            "safety": 9.0,
        }

    monkeypatch.setattr(env, "_reward_components", out_of_bounds_components)

    final = result_data(call_obs(env, "submit_final", draft_id=written["draft_id"]))

    typed_final = FinalSubmissionResult.model_validate(final)
    typed_components = RewardComponents.model_validate(final["components"])
    component_values = typed_components.model_dump().values()

    assert isinstance(typed_final.public_score, float)
    assert all(isinstance(value, float) for value in component_values)
    assert all(0.0 <= value <= 1.0 for value in component_values)
    assert 0.0 <= typed_final.public_score <= 1.0


def test_fresh_timeout_counts_against_safety_component():
    env = LegacyCobolEnvironment()
    env.reset(task_id="payroll_net_pay_001")
    case = CaseResult(case_id="case", passed=True, input_summary="case", actual="x", expected="x")
    hidden = EvaluationResult(
        syntax_ok=True,
        safety_ok=True,
        interface_ok=True,
        timed_out=False,
        passed=1,
        total=1,
        case_results=[case],
    )
    fresh = EvaluationResult(
        syntax_ok=True,
        safety_ok=True,
        interface_ok=True,
        timed_out=True,
        passed=1,
        total=1,
        case_results=[case],
    )

    components = RewardComponents.model_validate(env._reward_components(hidden, fresh))

    assert components.safety == 0.0


def test_async_max_step_guard_matches_sync_behavior():
    async def scenario():
        env = LegacyCobolEnvironment()
        env.reset(task_id="payroll_net_pay_001")

        for _ in range(MAX_STEPS):
            obs = await call_obs_async(env, "read_cobol_file", filename="PAYROLL.cbl")
            assert obs.done is False

        blocked = await call_obs_async(env, "write_python_solution", code=GOOD_SOLUTION)
        return env, blocked, result_data(blocked)

    env, blocked, blocked_result = asyncio.run(scenario())

    assert blocked.done is True
    assert blocked.reward == 0.0
    assert blocked_result["ok"] is False
    assert "max_steps" in blocked_result["error"]
    assert env.state.step_count == MAX_STEPS
    assert env.state.draft_count == 0


def test_schema_exposes_project_typed_state_fields():
    schema = TestClient(app).get("/schema").json()

    state_properties = schema["state"]["properties"]
    action_properties = schema["action"]["properties"]
    observation_properties = schema["observation"]["properties"]

    assert schema["action"]["title"] == "ToolActionWrapper"
    assert schema["observation"]["title"] == "ToolObservationWrapper"
    assert "tool_name" in action_properties
    assert "result" in observation_properties
    for field_name in [
        "task_id",
        "draft_count",
        "visible_runs",
        "final_score",
        "reward_components",
        "java_skeleton_generated",
        "java_files",
        "java_draft_id",
        "java_draft_count",
        "java_visible_runs",
        "last_java_visible_result",
        "last_java_failure_diagnostics",
        "java_final_eligible",
    ]:
        assert field_name in state_properties

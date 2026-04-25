import json
import shutil

import pytest

from legacy_cobol_env.eval.oracle_solutions import java_files_for_task
from legacy_cobol_env.eval.trajectory import run_solution_trajectory
from legacy_cobol_env.server.task_bank import all_tasks


def require_maven():
    if shutil.which("mvn") is None:
        pytest.skip("Maven is not installed; skipping Maven-dependent Java eval harness test")


def test_oracle_java_solution_scores_every_task_at_one():
    require_maven()

    for task in all_tasks():
        trajectory = run_solution_trajectory(
            policy_name="oracle",
            task=task,
            files=java_files_for_task(task),
        )

        assert trajectory["final"]["public_score"] == 1.0
        assert trajectory["final"]["accepted"] is True
        assert trajectory["visible"]["pass_rate"] == 1.0


def test_trajectory_records_serializable_java_tool_sequence():
    require_maven()

    task = all_tasks()[0]
    trajectory = run_solution_trajectory(
        policy_name="oracle",
        task=task,
        files=java_files_for_task(task),
    )

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
    assert trajectory["steps"][0]["reward"] == 0.02
    assert trajectory["steps"][-1]["done"] is True
    assert "hidden_junit_pass_rate" in trajectory["final"]["components"]
    json.dumps(trajectory)

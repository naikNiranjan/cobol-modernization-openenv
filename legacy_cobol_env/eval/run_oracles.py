"""Generate oracle trajectories for all task families."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from legacy_cobol_env.eval.oracle_solutions import java_files_for_task
from legacy_cobol_env.eval.trajectory import run_solution_trajectory
from legacy_cobol_env.server.task_bank import all_tasks


ENV_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ENV_ROOT / "outputs" / "evals"


def run_oracle_evaluation() -> dict:
    trajectories = [
        run_solution_trajectory(
            policy_name="oracle",
            task=task,
            files=java_files_for_task(task),
        )
        for task in all_tasks()
    ]
    return {
        "policy": "oracle",
        "task_count": len(trajectories),
        "mean_public_score": mean(item["final"]["public_score"] for item in trajectories),
        "accepted_count": sum(1 for item in trajectories if item["final"]["accepted"]),
        "trajectories": trajectories,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = run_oracle_evaluation()
    output_path = OUTPUT_DIR / "oracle_trajectories.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ["task_count", "mean_public_score", "accepted_count"]}, indent=2))


if __name__ == "__main__":
    main()

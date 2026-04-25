"""Run provider-backed model rollouts and write evaluation artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import mean

from legacy_cobol_env.eval.model_rollout import run_model_repair_rollout, run_model_rollout
from legacy_cobol_env.eval.oracle_solutions import java_response_for_task
from legacy_cobol_env.eval.providers import StaticResponseProvider, create_provider
from legacy_cobol_env.server.task_bank import all_tasks, load_task


ENV_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ENV_ROOT / "outputs" / "evals"


def run_rollouts(provider_name: str, task_id: str | None = None, max_repairs: int = 0) -> dict:
    tasks = [load_task(task_id=task_id)] if task_id else all_tasks()
    trajectories = []
    for task in tasks:
        provider = (
            StaticResponseProvider("oracle-model", json.dumps(java_response_for_task(task)))
            if provider_name == "oracle-model"
            else create_provider(provider_name, os.environ)
        )
        trajectory = (
            run_model_repair_rollout(task=task, provider=provider, max_repairs=max_repairs)
            if max_repairs > 0
            else run_model_rollout(task=task, provider=provider)
        )
        trajectories.append(trajectory)

    return {
        "provider": provider_name,
        "max_repairs": max_repairs,
        "task_count": len(trajectories),
        "mean_public_score": mean(item["final"]["public_score"] for item in trajectories),
        "accepted_count": sum(1 for item in trajectories if item["final"]["accepted"]),
        "trajectories": trajectories,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="oracle-model", choices=["oracle-model", "static", "azure-openai", "hf-endpoint", "local-transformers"])
    parser.add_argument("--task-id")
    parser.add_argument("--max-repairs", type=int, default=0)
    parser.add_argument("--output", default=str(OUTPUT_DIR / "model_rollouts.json"))
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = run_rollouts(provider_name=args.provider, task_id=args.task_id, max_repairs=args.max_repairs)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ["provider", "task_count", "mean_public_score", "accepted_count"]}, indent=2))


if __name__ == "__main__":
    main()

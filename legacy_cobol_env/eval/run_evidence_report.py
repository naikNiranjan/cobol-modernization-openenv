"""Generate score summary and plot artifacts for the submission."""

from __future__ import annotations

import json
from pathlib import Path

from legacy_cobol_env.eval.evidence_report import build_score_summary, load_json, write_score_plot
from legacy_cobol_env.server.task_bank import all_tasks


ENV_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ENV_ROOT / "outputs" / "evals"
PLOT_DIR = ENV_ROOT / "plots"


def main() -> None:
    baseline = load_json(OUTPUT_DIR / "baseline_results.json")
    evidence_notes = []
    oracle_model = _load_current_rollout(OUTPUT_DIR / "oracle_model_rollouts.json", evidence_notes)
    zeroshot = _load_current_rollout(OUTPUT_DIR / "azure_java_zeroshot_rollouts.json", evidence_notes)
    repair = _load_current_rollout(OUTPUT_DIR / "azure_java_repair1_rollouts.json", evidence_notes)
    summary = build_score_summary(
        baseline,
        zeroshot=zeroshot,
        repair=repair,
        oracle_model=oracle_model,
        evidence_notes=evidence_notes,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "score_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_score_plot(summary, PLOT_DIR / "model_scores.svg")
    print(json.dumps(summary["policies"], indent=2))


def _load_current_rollout(path: Path, evidence_notes: list[str]) -> dict | None:
    if not path.exists():
        evidence_notes.append(f"missing rollout artifact: {path.name}")
        return None
    artifact = load_json(path)
    if _matches_current_task_artifacts(artifact):
        return artifact
    evidence_notes.append(f"stale rollout artifact skipped after task hardening: {path.name}")
    return None


def _matches_current_task_artifacts(artifact: dict) -> bool:
    current = {
        task.task_id: {
            "files": sorted(task.cobol_files),
            "copybooks": sorted(task.copybooks),
        }
        for task in all_tasks()
    }
    trajectories = artifact.get("trajectories", [])
    if len(trajectories) != len(current):
        return False
    for trajectory in trajectories:
        task_id = trajectory.get("task_id")
        ticket = trajectory.get("ticket") or {}
        expected = current.get(task_id)
        if expected is None:
            return False
        if sorted(ticket.get("available_files", [])) != expected["files"]:
            return False
        if sorted(ticket.get("available_copybooks", [])) != expected["copybooks"]:
            return False
    return True


if __name__ == "__main__":
    main()

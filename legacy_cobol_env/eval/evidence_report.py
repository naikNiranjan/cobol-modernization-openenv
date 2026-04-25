"""Build judge-facing score summaries from evaluation artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_score_summary(
    baseline: dict[str, Any],
    zeroshot: dict[str, Any] | None = None,
    repair: dict[str, Any] | None = None,
    oracle_model: dict[str, Any] | None = None,
    evidence_notes: list[str] | None = None,
) -> dict[str, Any]:
    baseline_task_count = baseline.get("task_count") or len({row["task_id"] for row in baseline["results"]})
    policies = {
        name: {
            "mean_public_score": score,
            "accepted_count": sum(
                1 for row in baseline["results"] if row["policy"] == name and row.get("accepted")
            ),
            "task_count": baseline_task_count,
        }
        for name, score in baseline["mean_public_score"].items()
    }
    if oracle_model is not None:
        policies["oracle-model"] = {
            "mean_public_score": oracle_model["mean_public_score"],
            "accepted_count": oracle_model["accepted_count"],
            "task_count": oracle_model["task_count"],
        }
    if zeroshot is not None:
        policies["Azure Java zero-shot"] = {
            "mean_public_score": zeroshot["mean_public_score"],
            "accepted_count": zeroshot["accepted_count"],
            "task_count": zeroshot["task_count"],
        }
    if repair is not None:
        policies["Azure Java repair-1"] = {
            "mean_public_score": repair["mean_public_score"],
            "accepted_count": repair["accepted_count"],
            "task_count": repair["task_count"],
        }

    task_scores: dict[str, dict[str, Any]] = {}
    if oracle_model is not None:
        for trajectory in oracle_model["trajectories"]:
            task_scores.setdefault(trajectory["task_id"], {})["oracle_model"] = trajectory["final"]["public_score"]
    if zeroshot is not None:
        for trajectory in zeroshot["trajectories"]:
            task_scores.setdefault(trajectory["task_id"], {})["zeroshot"] = trajectory["final"]["public_score"]
            task_scores[trajectory["task_id"]]["zeroshot_accepted"] = trajectory["final"]["accepted"]
    if repair is not None:
        for trajectory in repair["trajectories"]:
            task_scores.setdefault(trajectory["task_id"], {})["repair1"] = trajectory["final"]["public_score"]
            task_scores[trajectory["task_id"]]["repair1_accepted"] = trajectory["final"]["accepted"]

    training_targets = []
    if repair is not None:
        zeroshot_by_task = {
            trajectory["task_id"]: trajectory["final"]
            for trajectory in (zeroshot or {}).get("trajectories", [])
        }
        for trajectory in repair["trajectories"]:
            final = trajectory["final"]
            visible = trajectory["visible"]
            zeroshot_final = zeroshot_by_task.get(trajectory["task_id"], {})
            zeroshot_score = zeroshot_final.get("public_score")
            repair_score = final["public_score"]
            reason = None
            if visible["pass_rate"] == 1.0 and not final["accepted"]:
                reason = "visible-pass-hidden-fresh-gap"
            elif isinstance(zeroshot_score, int | float) and repair_score > zeroshot_score and not final["accepted"]:
                reason = "repair-improved-but-unsolved"
            if reason is not None:
                training_targets.append(
                    {
                        "task_id": trajectory["task_id"],
                        "family_id": trajectory.get("family_id"),
                        "reason": reason,
                        "zeroshot_public_score": zeroshot_score,
                        "repair_public_score": repair_score,
                        "visible_pass_rate": visible["pass_rate"],
                        "weak_components": {
                            key: value
                            for key, value in final["components"].items()
                            if isinstance(value, int | float) and value < 1.0
                        },
                    }
                )

    return {
        "policies": policies,
        "task_scores": task_scores,
        "training_targets": training_targets,
        "evidence_notes": evidence_notes or [],
    }


def write_score_plot(summary: dict[str, Any], path: Path) -> None:
    policies = list(summary["policies"].items())
    width = 760
    height = 320
    margin = 48
    plot_height = height - margin * 2
    bar_width = 86
    gap = 32
    colors = ["#64748b", "#22c55e", "#2563eb", "#f97316"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="40" y="30" font-family="Arial" font-size="18" font-weight="700">Legacy COBOL OpenEnv evaluation</text>',
        f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#1f2937"/>',
        f'<line x1="{margin}" y1="{height - margin}" x2="{margin}" y2="{margin}" stroke="#1f2937"/>',
    ]
    x = margin + 20
    for index, (name, data) in enumerate(policies):
        score = float(data["mean_public_score"])
        bar_height = score * plot_height
        y = height - margin - bar_height
        color = colors[index % len(colors)]
        parts.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_width}" height="{bar_height:.1f}" rx="4" fill="{color}"/>')
        parts.append(f'<text x="{x + 8}" y="{y - 8:.1f}" font-family="Arial" font-size="12">{score:.3f}</text>')
        accepted = f'{data["accepted_count"]}/{data["task_count"]} accepted'
        parts.append(f'<text x="{x}" y="{height - 28}" font-family="Arial" font-size="10">{accepted}</text>')
        for line_index, line in enumerate(_wrap_label(name)):
            parts.append(f'<text x="{x}" y="{height - 14 + line_index * 11}" font-family="Arial" font-size="10">{line}</text>')
        x += bar_width + gap
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _wrap_label(label: str) -> list[str]:
    words = label.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > 18 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:2]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

from pathlib import Path

from legacy_cobol_env.eval.evidence_report import build_score_summary, write_score_plot


def test_score_summary_identifies_visible_pass_hidden_failures():
    baseline = {
        "mean_public_score": {"identity": 0.15},
        "results": [{"task_id": "invoice_occurs_001", "policy": "identity", "public_score": 0.15}],
    }
    zeroshot = {
        "mean_public_score": 0.305,
        "accepted_count": 1,
        "task_count": 1,
        "trajectories": [{"task_id": "invoice_occurs_001", "final": {"public_score": 0.23, "accepted": False}}],
    }
    repair = {
        "mean_public_score": 0.92055,
        "accepted_count": 5,
        "task_count": 1,
        "trajectories": [
            {
                "task_id": "invoice_occurs_001",
                "visible": {"pass_rate": 1.0},
                "final": {
                    "public_score": 0.5233,
                    "accepted": False,
                    "components": {"hidden_correctness": 0.3333, "fresh_correctness": 0.5},
                },
            }
        ],
    }

    summary = build_score_summary(baseline, zeroshot, repair)

    assert summary["policies"]["Azure Java repair-1"]["mean_public_score"] == 0.92055
    assert summary["task_scores"]["invoice_occurs_001"]["repair1"] == 0.5233
    assert summary["training_targets"][0]["task_id"] == "invoice_occurs_001"
    assert summary["training_targets"][0]["reason"] == "visible-pass-hidden-fresh-gap"


def test_score_plot_writes_svg(tmp_path: Path):
    summary = {
        "policies": {
            "identity": {"mean_public_score": 0.15, "accepted_count": 0, "task_count": 6},
            "Azure Java repair-1": {"mean_public_score": 0.92055, "accepted_count": 5, "task_count": 6},
        }
    }
    output = tmp_path / "scores.svg"

    write_score_plot(summary, output)

    assert output.read_text(encoding="utf-8").startswith("<svg")

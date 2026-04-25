import json
from pathlib import Path

from legacy_cobol_env.eval.providers import create_provider
from legacy_cobol_env.training.train_sft import DEFAULT_DATASET, DEFAULT_OUTPUT_DIR, SFTArgs, build_sft_plan, load_jsonl_rows, write_dry_run_artifacts


def test_default_sft_args_target_java_dataset():
    args = SFTArgs()

    assert args.dataset == DEFAULT_DATASET
    assert args.dataset.endswith("java_oracle_sft.jsonl")
    assert args.output_dir == DEFAULT_OUTPUT_DIR
    assert "java-sft" in args.output_dir


def test_build_sft_plan_reads_dataset_without_gpu_dependencies(tmp_path: Path):
    dataset = tmp_path / "tiny.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "task_id": "invoice_occurs_001",
                "family_id": "invoice_occurs_totals",
                "messages": [
                    {"role": "user", "content": "prompt"},
                    {"role": "assistant", "content": "{\"code\": \"def migrate(input_record: str) -> str:\\n    return input_record\\n\"}"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    plan = build_sft_plan(SFTArgs(dataset=str(dataset), output_dir=str(tmp_path / "out")))

    assert plan["dataset_examples"] == 1
    assert plan["model_name"]
    assert plan["uses_lora"] is True
    assert plan["output_dir"] == str(tmp_path / "out")
    assert plan["completion_schemas"] == ["python_code"]


def test_build_sft_plan_reads_java_dataset_metadata(tmp_path: Path):
    dataset = tmp_path / "java.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "task_id": "invoice_occurs_001",
                "family_id": "invoice_occurs_totals",
                "primary_training_target": True,
                "messages": [
                    {"role": "user", "content": "prompt"},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "files": {
                                    "src/main/java/com/example/migration/MigrationService.java": "package com.example.migration;\n"
                                }
                            }
                        ),
                    },
                ],
                "completion": json.dumps(
                    {
                        "files": {
                            "src/main/java/com/example/migration/MigrationService.java": "package com.example.migration;\n"
                        }
                    }
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    plan = build_sft_plan(SFTArgs(dataset=str(dataset), output_dir=str(tmp_path / "out")))

    assert plan["completion_schemas"] == ["java_files"]
    assert plan["primary_training_targets"] == ["invoice_occurs_001"]
    assert plan["task_ids"] == ["invoice_occurs_001"]


def test_load_jsonl_rows_rejects_missing_messages(tmp_path: Path):
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text(json.dumps({"task_id": "x"}) + "\n", encoding="utf-8")

    try:
        load_jsonl_rows(dataset)
    except ValueError as exc:
        assert "messages" in str(exc)
    else:
        raise AssertionError("expected invalid dataset row to fail")


def test_load_jsonl_rows_rejects_invalid_message_content(tmp_path: Path):
    dataset = tmp_path / "bad-message.jsonl"
    dataset.write_text(
        json.dumps({"task_id": "x", "messages": [{"role": "user", "content": "prompt"}, {"role": "assistant"}]}) + "\n",
        encoding="utf-8",
    )

    try:
        load_jsonl_rows(dataset)
    except ValueError as exc:
        assert "invalid message" in str(exc)
    else:
        raise AssertionError("expected invalid message row to fail")


def test_local_transformers_provider_requires_model_path():
    try:
        create_provider("local-transformers", {})
    except ValueError as exc:
        assert "LOCAL_MODEL_PATH" in str(exc)
    else:
        raise AssertionError("expected missing local model path to fail")


def test_write_dry_run_artifacts_creates_metadata_loss_and_plot(tmp_path: Path):
    plan = {
        "dataset_examples": 6,
        "model_name": "Qwen/Qwen2.5-Coder-7B-Instruct",
        "output_dir": str(tmp_path / "model"),
    }

    artifacts = write_dry_run_artifacts(plan, tmp_path)

    assert artifacts["metadata"].exists()
    metadata = json.loads(artifacts["metadata"].read_text(encoding="utf-8"))
    assert metadata["plan"]["dataset_examples"] == 6
    assert artifacts["loss_csv"].read_text(encoding="utf-8").splitlines()[0] == "step,loss"
    assert artifacts["loss_plot"].read_text(encoding="utf-8").startswith("<svg")

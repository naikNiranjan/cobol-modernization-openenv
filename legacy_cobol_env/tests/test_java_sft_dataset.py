import json
from pathlib import Path

from legacy_cobol_env.eval.oracle_solutions import MIGRATION_SERVICE_PATH
from legacy_cobol_env.server.java_runner import ALLOWED_JAVA_PATHS
from legacy_cobol_env.training.build_java_sft_dataset import write_java_oracle_sft_dataset


def test_java_sft_dataset_writes_java_files_schema(tmp_path: Path):
    output = tmp_path / "java_oracle_sft.jsonl"

    write_java_oracle_sft_dataset(output)

    assert output.exists()
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 6

    target_rows = [row for row in rows if row["task_id"] == "invoice_occurs_001"]
    assert len(target_rows) == 1

    for row in rows:
        assert row["task_id"]
        assert row["family_id"]
        if row["task_id"] == "invoice_occurs_001":
            assert row["primary_training_target"] is True
        else:
            assert row["primary_training_target"] is False
        assert row["messages"][0]["role"] == "user"
        assert row["messages"][1]["role"] == "assistant"
        assert row["messages"][1]["content"] == row["completion"]

        completion = json.loads(row["completion"])
        assert "files" in completion
        assert "code" not in completion
        assert isinstance(completion["files"], dict)
        assert MIGRATION_SERVICE_PATH in completion["files"]
        assert set(completion["files"]) <= set(ALLOWED_JAVA_PATHS)
        assert "package com.example.migration" in completion["files"][MIGRATION_SERVICE_PATH]


def test_compact_java_sft_dataset_uses_java_schema_and_shorter_prompts(tmp_path: Path):
    full_output = tmp_path / "java_oracle_sft.jsonl"
    compact_output = tmp_path / "java_oracle_sft_compact.jsonl"

    write_java_oracle_sft_dataset(full_output)
    write_java_oracle_sft_dataset(compact_output, compact=True)

    full_rows = [json.loads(line) for line in full_output.read_text(encoding="utf-8").splitlines()]
    compact_rows = [json.loads(line) for line in compact_output.read_text(encoding="utf-8").splitlines()]
    assert len(compact_rows) == 6

    full_by_task = {row["task_id"]: row for row in full_rows}
    for row in compact_rows:
        assert len(row["prompt"]) <= len(full_by_task[row["task_id"]]["prompt"])
        assert "COBOL-to-Java modernization" in row["prompt"]
        assert "Allowed Java/editing metadata" in row["prompt"]
        completion = json.loads(row["completion"])
        assert "files" in completion
        assert "code" not in completion

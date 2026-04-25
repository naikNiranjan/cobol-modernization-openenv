import io
import json

import pytest

from inference import format_event, load_runtime_config, main
from legacy_cobol_env.server.task_bank import all_tasks


def test_live_config_requires_openai_compatible_environment():
    with pytest.raises(ValueError) as exc_info:
        load_runtime_config({}, mode="live")

    assert str(exc_info.value) == "missing inference configuration: API_BASE_URL, MODEL_NAME, HF_TOKEN"


def test_static_config_skips_live_network_environment():
    config = load_runtime_config({}, mode="static")

    assert config.mode == "static"
    assert config.api_base_url == ""
    assert config.model_name == "static"
    assert config.hf_token == ""


def test_static_inference_response_uses_java_file_schema(tmp_path):
    stdout = io.StringIO()
    output_path = tmp_path / "java-static.json"

    exit_code = main(
        [
            "--task-id",
            "payroll_net_pay_001",
            "--max-repairs",
            "0",
            "--output",
            str(output_path),
            "--mode",
            "static",
        ],
        env={},
        stdout=stdout,
    )

    assert exit_code == 0
    summary = json.loads(output_path.read_text(encoding="utf-8"))
    response = summary["results"][0]["trajectory"]["model_turns"][0]["response"]
    parsed = json.loads(response)

    assert "files" in parsed
    assert "code" not in parsed
    assert "src/main/java/com/example/migration/MigrationService.java" in parsed["files"]
    assert "public final class MigrationService" in parsed["files"]["src/main/java/com/example/migration/MigrationService.java"]


def test_format_event_emits_strict_marker_and_stable_json_payload():
    line = format_event("STEP", {"task_id": "payroll_net_pay_001", "score": 0.0, "accepted": False})

    assert line == '[STEP] {"accepted":false,"score":0.0,"task_id":"payroll_net_pay_001"}'
    assert json.loads(line.removeprefix("[STEP] ")) == {
        "task_id": "payroll_net_pay_001",
        "score": 0.0,
        "accepted": False,
    }


def test_static_cli_with_task_id_emits_markers_and_writes_output(tmp_path):
    stdout = io.StringIO()
    output_path = tmp_path / "result.json"

    exit_code = main(
        [
            "--task-id",
            "payroll_net_pay_001",
            "--max-repairs",
            "1",
            "--output",
            str(output_path),
            "--mode",
            "static",
        ],
        env={},
        stdout=stdout,
    )

    assert exit_code == 0
    lines = stdout.getvalue().splitlines()
    assert [line.split(" ", 1)[0] for line in lines] == ["[START]", "[STEP]", "[END]"]
    payloads = [json.loads(line.split(" ", 1)[1]) for line in lines]
    assert payloads[0]["task_id"] == "payroll_net_pay_001"
    assert payloads[1]["task_id"] == "payroll_net_pay_001"
    assert payloads[2]["task_count"] == 1

    summary = json.loads(output_path.read_text(encoding="utf-8"))
    assert summary["mode"] == "static"
    assert summary["task_count"] == 1
    assert summary["results"][0]["task_id"] == "payroll_net_pay_001"


def test_static_cli_without_task_id_runs_all_tasks(tmp_path):
    stdout = io.StringIO()
    output_path = tmp_path / "all-tasks.json"

    exit_code = main(["--mode", "static", "--output", str(output_path)], env={}, stdout=stdout)

    assert exit_code == 0
    lines = stdout.getvalue().splitlines()
    expected_task_count = len(all_tasks())
    assert [line.split(" ", 1)[0] for line in lines] == ["[START]"] + ["[STEP]"] * expected_task_count + ["[END]"]
    assert json.loads(lines[0].split(" ", 1)[1])["task_id"] == "all"
    assert json.loads(lines[-1].split(" ", 1)[1])["task_count"] == expected_task_count

    summary = json.loads(output_path.read_text(encoding="utf-8"))
    assert summary["task_count"] == expected_task_count
    assert len(summary["results"]) == expected_task_count

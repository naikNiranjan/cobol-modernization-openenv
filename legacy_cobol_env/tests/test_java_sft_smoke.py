import json

from legacy_cobol_env.eval.oracle_solutions import java_response_for_task
from legacy_cobol_env.server.task_bank import load_task
from legacy_cobol_env.training.smoke_generate_sft import validate_generated_response


def test_smoke_validation_accepts_oracle_java_files_json():
    response = json.dumps(java_response_for_task(load_task(task_id="invoice_occurs_001")))

    validation = validate_generated_response(response)

    assert validation["valid_schema"] is True
    assert validation["valid_edits"] is True
    assert validation["error"] is None
    assert "src/main/java/com/example/migration/MigrationService.java" in validation["files"]


def test_smoke_validation_rejects_python_code_schema():
    validation = validate_generated_response('{"code":"print(1)"}')

    assert validation["valid_schema"] is False
    assert validation["valid_edits"] is False
    assert "files object" in validation["error"]

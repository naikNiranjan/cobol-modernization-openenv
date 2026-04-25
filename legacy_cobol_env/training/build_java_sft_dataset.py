"""Write Java oracle SFT warm-start examples as JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from legacy_cobol_env.eval.model_rollout import JAVA_JSON_SCHEMA_TEXT, _prepare_java_rollout, build_migration_prompt
from legacy_cobol_env.eval.oracle_solutions import java_response_for_task
from legacy_cobol_env.server.task_bank import TaskInstance, all_tasks


ENV_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ENV_ROOT / "outputs" / "training"
PRIMARY_TRAINING_TARGET = "invoice_occurs_001"
DEFAULT_OUTPUT = OUTPUT_DIR / "java_oracle_sft.jsonl"
COMPACT_OUTPUT = OUTPUT_DIR / "java_oracle_sft_compact.jsonl"


def build_java_oracle_sft_examples(tasks: Iterable[TaskInstance], compact: bool = False) -> list[dict]:
    examples = []
    for task in tasks:
        _env, ticket, context, _steps, _record = _prepare_java_rollout(task)
        prompt = build_compact_migration_prompt(ticket, context) if compact else build_migration_prompt(ticket, context)
        completion = json.dumps(java_response_for_task(task))
        examples.append(
            {
                "task_id": task.task_id,
                "family_id": task.family_id,
                "primary_training_target": task.task_id == PRIMARY_TRAINING_TARGET,
                "prompt": prompt,
                "completion": completion,
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": completion},
                ],
            }
        )
    return examples


def dumps_jsonl(examples: list[dict]) -> str:
    return "\n".join(json.dumps(example) for example in examples) + "\n"


def write_java_oracle_sft_dataset(output_path: Path, compact: bool = False) -> list[dict]:
    examples = build_java_oracle_sft_examples(all_tasks(), compact=compact)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dumps_jsonl(examples), encoding="utf-8")
    return examples


def build_compact_migration_prompt(ticket: dict, context: dict) -> str:
    metadata = context.get("java_metadata", {})
    compact_metadata = {
        "package_name": metadata.get("package_name"),
        "required_class": metadata.get("required_class"),
        "required_method": metadata.get("required_method"),
        "allowed_editable_paths": metadata.get("allowed_editable_paths"),
        "input_width": metadata.get("input_width"),
        "output_width": metadata.get("output_width"),
        "copybook_field_mappings": metadata.get("copybook_field_mappings"),
        "output_layout": metadata.get("output_layout"),
        "java_type_hints": metadata.get("java_type_hints"),
    }
    return "\n\n".join(
        [
            "You are performing COBOL-to-Java modernization. Return JSON only.",
            f"Schema: {JAVA_JSON_SCHEMA_TEXT}",
            "Required Java API: package com.example.migration; class MigrationService; public String migrate(String inputRecord).",
            "Use BigDecimal and RoundingMode.HALF_UP for implied decimals. Preserve exact fixed-width output.",
            "Do not edit tests, pom.xml, or files outside the allowed editable Java paths.",
            f"Migration ticket:\n{ticket.get('ticket', '')}",
            f"Task files:\n{json.dumps({'cobol': ticket.get('available_files', []), 'copybooks': ticket.get('available_copybooks', [])}, indent=2)}",
            f"Allowed Java/editing metadata:\n{json.dumps(compact_metadata, indent=2)}",
            f"COBOL source:\n{json.dumps(context['cobol_files'], indent=2)}",
            f"Copybook source:\n{json.dumps(context['copybooks'], indent=2)}",
            f"Parsed field offsets:\n{json.dumps(context['layouts'], indent=2)}",
            f"Business rules:\n{json.dumps(context['business_rules'], indent=2)}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else COMPACT_OUTPUT if args.compact else DEFAULT_OUTPUT
    examples = write_java_oracle_sft_dataset(output_path, compact=args.compact)
    print(f"wrote {len(examples)} examples to {output_path}")


if __name__ == "__main__":
    main()

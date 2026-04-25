"""Write Java oracle SFT warm-start examples as JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from legacy_cobol_env.eval.model_rollout import _prepare_java_rollout, build_migration_prompt
from legacy_cobol_env.eval.oracle_solutions import java_response_for_task
from legacy_cobol_env.server.task_bank import TaskInstance, all_tasks


ENV_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ENV_ROOT / "outputs" / "training"
PRIMARY_TRAINING_TARGET = "invoice_occurs_001"


def build_java_oracle_sft_examples(tasks: Iterable[TaskInstance]) -> list[dict]:
    examples = []
    for task in tasks:
        _env, ticket, context, _steps, _record = _prepare_java_rollout(task)
        prompt = build_migration_prompt(ticket, context)
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


def write_java_oracle_sft_dataset(output_path: Path) -> list[dict]:
    examples = build_java_oracle_sft_examples(all_tasks())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dumps_jsonl(examples), encoding="utf-8")
    return examples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT_DIR / "java_oracle_sft.jsonl"))
    args = parser.parse_args()

    output_path = Path(args.output)
    examples = write_java_oracle_sft_dataset(output_path)
    print(f"wrote {len(examples)} examples to {output_path}")


if __name__ == "__main__":
    main()

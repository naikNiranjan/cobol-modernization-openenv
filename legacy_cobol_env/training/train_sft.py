"""GPU-ready SFT warm-start script for open code models.

The module is importable without GPU training dependencies. Live training imports
Transformers, Datasets, PEFT, and TRL only when `run_sft_training` is called.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
DEFAULT_DATASET = "legacy_cobol_env/outputs/training/java_oracle_sft.jsonl"
DEFAULT_OUTPUT_DIR = "legacy_cobol_env/outputs/training/java-sft-qwen-coder-7b"


@dataclass(frozen=True)
class SFTArgs:
    dataset: str = DEFAULT_DATASET
    output_dir: str = DEFAULT_OUTPUT_DIR
    model_name: str = DEFAULT_MODEL
    max_seq_length: int = 4096
    num_train_epochs: float = 3.0
    learning_rate: float = 2e-4
    per_device_train_batch_size: int = 1
    gradient_accumulation_steps: int = 8
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    load_in_4bit: bool = True
    bf16: bool = True


def load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        messages = row.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            raise ValueError(f"{path}:{line_number} missing chat-style messages")
        for message_index, message in enumerate(messages, start=1):
            if not isinstance(message, dict) or not isinstance(message.get("role"), str) or not isinstance(message.get("content"), str):
                raise ValueError(f"{path}:{line_number} invalid message at index {message_index}")
        rows.append(row)
    if not rows:
        raise ValueError(f"{path} has no training rows")
    return rows


def build_sft_plan(args: SFTArgs) -> dict[str, Any]:
    rows = load_jsonl_rows(Path(args.dataset))
    families = sorted({row.get("family_id", "unknown") for row in rows})
    task_ids = [str(row.get("task_id", "unknown")) for row in rows]
    completion_schemas = sorted({_completion_schema(row) for row in rows})
    primary_training_targets = sorted(
        str(row["task_id"])
        for row in rows
        if row.get("primary_training_target") and row.get("task_id")
    )
    return {
        **asdict(args),
        "dataset_examples": len(rows),
        "families": families,
        "task_ids": task_ids,
        "completion_schemas": completion_schemas,
        "primary_training_targets": primary_training_targets,
        "uses_lora": args.lora_rank > 0,
        "training_dependencies": ["torch", "transformers", "datasets", "peft", "trl", "accelerate"],
    }


def _completion_schema(row: dict[str, Any]) -> str:
    completion = row.get("completion")
    if not isinstance(completion, str):
        messages = row.get("messages") or []
        completion = messages[-1].get("content") if messages and isinstance(messages[-1], dict) else None
    if not isinstance(completion, str):
        return "unknown"
    try:
        parsed = json.loads(completion)
    except json.JSONDecodeError:
        return "text"
    if isinstance(parsed, dict) and isinstance(parsed.get("files"), dict):
        return "java_files"
    if isinstance(parsed, dict) and isinstance(parsed.get("code"), str):
        return "python_code"
    return "json"


def write_dry_run_artifacts(plan: dict[str, Any], output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    metadata_path = output_root / "sft_run_metadata.json"
    loss_csv_path = output_root / "sft_loss.csv"
    loss_plot_path = output_root / "sft_loss.svg"

    metadata = {
        "status": "dry_run",
        "created_at": datetime.now(UTC).isoformat(),
        "note": "Scaffolding artifact only; no GPU training has been run.",
        "plan": plan,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    loss_rows = [(0, 1.0), (1, 0.92), (2, 0.84), (3, 0.79)]
    loss_csv_path.write_text("step,loss\n" + "\n".join(f"{step},{loss}" for step, loss in loss_rows) + "\n", encoding="utf-8")
    _write_loss_svg(loss_rows, loss_plot_path)
    return {"metadata": metadata_path, "loss_csv": loss_csv_path, "loss_plot": loss_plot_path}


def _write_loss_svg(rows: list[tuple[int, float]], path: Path) -> None:
    width = 520
    height = 260
    margin = 44
    max_step = max(step for step, _ in rows) or 1
    max_loss = max(loss for _, loss in rows) or 1.0
    points = []
    for step, loss in rows:
        x = margin + (step / max_step) * (width - 2 * margin)
        y = height - margin - (loss / max_loss) * (height - 2 * margin)
        points.append(f"{x:.1f},{y:.1f}")
    svg = "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            '<text x="32" y="28" font-family="Arial" font-size="16" font-weight="700">SFT dry-run loss scaffold</text>',
            f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#1f2937"/>',
            f'<line x1="{margin}" y1="{height - margin}" x2="{margin}" y2="{margin}" stroke="#1f2937"/>',
            f'<polyline fill="none" stroke="#2563eb" stroke-width="3" points="{" ".join(points)}"/>',
            "</svg>",
        ]
    )
    path.write_text(svg, encoding="utf-8")


def run_sft_training(args: SFTArgs) -> None:
    plan = build_sft_plan(args)
    try:
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise RuntimeError(
            "SFT training dependencies are not installed. Install training/requirements-gpu.txt "
            "in a GPU environment, then rerun this command."
        ) from exc

    tokenizer = AutoTokenizer.from_pretrained(args.model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quantization_config = None
    if args.load_in_4bit:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype="bfloat16",
        )

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        device_map="auto",
        quantization_config=quantization_config,
        trust_remote_code=True,
    )

    dataset = load_dataset("json", data_files=args.dataset, split="train")

    def formatting_func(example: dict[str, Any]) -> str:
        return tokenizer.apply_chat_template(
            example["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )

    peft_config = LoraConfig(
        r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    train_config = SFTConfig(
        output_dir=args.output_dir,
        max_length=args.max_seq_length,
        num_train_epochs=args.num_train_epochs,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        logging_steps=1,
        save_strategy="epoch",
        bf16=args.bf16,
        packing=False,
    )
    trainer = SFTTrainer(
        model=model,
        args=train_config,
        train_dataset=dataset,
        processing_class=tokenizer,
        formatting_func=formatting_func,
        peft_config=peft_config,
    )
    print(json.dumps({"sft_plan": plan}, indent=2))
    trainer.train()
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-name", default=DEFAULT_MODEL)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--num-train-epochs", type=float, default=3.0)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--no-4bit", action="store_true")
    parser.add_argument("--no-bf16", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    parsed = parse_args()
    args = SFTArgs(
        dataset=parsed.dataset,
        output_dir=parsed.output_dir,
        model_name=parsed.model_name,
        max_seq_length=parsed.max_seq_length,
        num_train_epochs=parsed.num_train_epochs,
        learning_rate=parsed.learning_rate,
        per_device_train_batch_size=parsed.per_device_train_batch_size,
        gradient_accumulation_steps=parsed.gradient_accumulation_steps,
        lora_rank=parsed.lora_rank,
        lora_alpha=parsed.lora_alpha,
        lora_dropout=parsed.lora_dropout,
        load_in_4bit=not parsed.no_4bit,
        bf16=not parsed.no_bf16,
    )
    if parsed.dry_run:
        plan = build_sft_plan(args)
        print(json.dumps(plan, indent=2))
        output_root = Path(args.output_dir).parent
        write_dry_run_artifacts(plan, output_root)
        return
    run_sft_training(args)


if __name__ == "__main__":
    main()

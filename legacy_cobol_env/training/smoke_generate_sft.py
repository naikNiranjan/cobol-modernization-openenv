"""Cheap local generation smoke test for Java SFT adapters."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from legacy_cobol_env.eval.model_rollout import _prepare_java_rollout, build_migration_prompt, extract_java_files_from_response
from legacy_cobol_env.server.java_runner import validate_java_edits
from legacy_cobol_env.server.task_bank import load_task
from legacy_cobol_env.training.build_java_sft_dataset import build_compact_migration_prompt


DEFAULT_OUTPUT = "legacy_cobol_env/outputs/evals/local_java_sft3b_invoice_generation_smoke.json"
DEFAULT_TASK_ID = "invoice_occurs_001"


def validate_generated_response(response: str) -> dict[str, Any]:
    try:
        files = extract_java_files_from_response(response)
    except ValueError as exc:
        return {"valid_schema": False, "valid_edits": False, "error": str(exc), "files": {}}
    edits_ok, edits_error = validate_java_edits(files)
    return {
        "valid_schema": True,
        "valid_edits": edits_ok,
        "error": edits_error,
        "files": sorted(files),
    }


def build_smoke_prompt(task_id: str, compact: bool) -> str:
    _env, ticket, context, _steps, _record = _prepare_java_rollout(load_task(task_id=task_id))
    return build_compact_migration_prompt(ticket, context) if compact else build_migration_prompt(ticket, context)


def generate_response(
    prompt: str,
    model_path: str,
    adapter_path: str | None,
    max_new_tokens: int,
    max_input_tokens: int,
    load_in_4bit: bool,
    device_map: str,
) -> str:
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError as exc:
        raise RuntimeError("install training/requirements-gpu.txt to run smoke generation") from exc

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quantization_config = None
    if load_in_4bit:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
        )

    max_memory = None
    gpu_max = os.environ.get("LOCAL_GPU_MAX_MEMORY")
    if gpu_max and torch.cuda.is_available():
        max_memory = {index: gpu_max for index in range(torch.cuda.device_count())}
        max_memory["cpu"] = os.environ.get("LOCAL_CPU_MAX_MEMORY", "48GiB")

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        device_map=device_map,
        max_memory=max_memory,
        quantization_config=quantization_config,
        trust_remote_code=True,
    )
    if adapter_path:
        try:
            from peft import PeftModel
        except ImportError as exc:
            raise RuntimeError("install PEFT to load LOCAL_ADAPTER_PATH") from exc
        model = PeftModel.from_pretrained(model, adapter_path)

    messages = [
        {
            "role": "system",
            "content": "Return only JSON with a files object mapping allowed Java source paths to Java source strings.",
        },
        {"role": "user", "content": prompt},
    ]
    if hasattr(tokenizer, "apply_chat_template"):
        prompt_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        prompt_text = prompt

    tokenizer.truncation_side = "left"
    inputs = tokenizer(
        prompt_text,
        return_tensors="pt",
        truncation=True,
        max_length=max_input_tokens,
    )
    device = getattr(model, "device", None) or next(model.parameters()).device
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    generated = output_ids[0][inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(generated, skip_special_tokens=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default=DEFAULT_TASK_ID)
    parser.add_argument("--model-path", default=os.environ.get("LOCAL_MODEL_PATH", "Qwen/Qwen2.5-Coder-3B-Instruct"))
    parser.add_argument("--adapter-path", default=os.environ.get("LOCAL_ADAPTER_PATH"))
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--max-new-tokens", type=int, default=int(os.environ.get("LOCAL_MAX_NEW_TOKENS", "1000")))
    parser.add_argument("--max-input-tokens", type=int, default=int(os.environ.get("LOCAL_MAX_INPUT_TOKENS", "4096")))
    parser.add_argument("--device-map", default=os.environ.get("LOCAL_DEVICE_MAP", "auto"))
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--no-4bit", action="store_true")
    args = parser.parse_args()

    prompt = build_smoke_prompt(args.task_id, compact=args.compact)
    response = generate_response(
        prompt=prompt,
        model_path=args.model_path,
        adapter_path=args.adapter_path,
        max_new_tokens=args.max_new_tokens,
        max_input_tokens=args.max_input_tokens,
        load_in_4bit=not args.no_4bit,
        device_map=args.device_map,
    )
    validation = validate_generated_response(response)
    payload = {
        "task_id": args.task_id,
        "model_path": args.model_path,
        "adapter_path": args.adapter_path,
        "compact_prompt": args.compact,
        "prompt_chars": len(prompt),
        "response": response,
        "validation": validation,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_path), **validation}, indent=2))


if __name__ == "__main__":
    main()

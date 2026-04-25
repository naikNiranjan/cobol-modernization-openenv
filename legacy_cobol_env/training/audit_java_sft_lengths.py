"""Audit Java SFT row lengths for chat-token truncation risk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from legacy_cobol_env.training.train_sft import DEFAULT_DATASET, load_jsonl_rows


DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct"


def audit_rows(rows: list[dict[str, Any]], tokenizer: Any, max_seq_length: int) -> list[dict[str, Any]]:
    results = []
    for row in rows:
        prompt_messages = [row["messages"][0]]
        prompt_tokens = _count_chat_tokens(tokenizer, prompt_messages, add_generation_prompt=True)
        completion_tokens = _count_text_tokens(tokenizer, row["completion"])
        total_tokens = _count_chat_tokens(tokenizer, row["messages"], add_generation_prompt=False)
        results.append(
            {
                "task_id": row["task_id"],
                "family_id": row["family_id"],
                "primary_training_target": bool(row.get("primary_training_target")),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "max_seq_length": max_seq_length,
                "exceeds_max_seq_length": total_tokens > max_seq_length,
            }
        )
    return results


def summarize_audit(results: list[dict[str, Any]], max_seq_length: int) -> dict[str, Any]:
    max_total = max((row["total_tokens"] for row in results), default=0)
    return {
        "row_count": len(results),
        "max_seq_length": max_seq_length,
        "max_total_tokens": max_total,
        "recommended_max_seq_length": _recommended_max_seq_length(max_total),
        "exceeding_tasks": [row["task_id"] for row in results if row["exceeds_max_seq_length"]],
        "invoice_exceeds_max_seq_length": any(
            row["task_id"] == "invoice_occurs_001" and row["exceeds_max_seq_length"]
            for row in results
        ),
    }


def load_tokenizer(model_name: str) -> Any:
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("install Transformers to audit Java SFT token lengths") from exc
    return AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)


def _count_chat_tokens(tokenizer: Any, messages: list[dict[str, str]], add_generation_prompt: bool) -> int:
    if hasattr(tokenizer, "apply_chat_template"):
        tokens = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=add_generation_prompt,
        )
        return _flattened_token_count(tokens)
    rendered = "\n".join(f"{message['role']}: {message['content']}" for message in messages)
    if add_generation_prompt:
        rendered += "\nassistant:"
    return _count_text_tokens(tokenizer, rendered)


def _count_text_tokens(tokenizer: Any, text: str) -> int:
    if hasattr(tokenizer, "encode"):
        return len(tokenizer.encode(text, add_special_tokens=False))
    return len(text.split())


def _flattened_token_count(tokens: Any) -> int:
    if hasattr(tokens, "keys") and "input_ids" in tokens:
        return _flattened_token_count(tokens["input_ids"])
    if hasattr(tokens, "shape"):
        shape = tokens.shape
        return int(shape[-1]) if shape else 0
    if tokens and isinstance(tokens[0], list):
        return len(tokens[0])
    return len(tokens)


def _recommended_max_seq_length(token_count: int) -> int:
    for candidate in (2048, 4096, 8192, 16384):
        if token_count <= candidate:
            return candidate
    return token_count


def print_table(results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    print("task_id family_id prompt completion total exceeds_{}".format(summary["max_seq_length"]))
    for row in results:
        print(
            row["task_id"],
            row["family_id"],
            row["prompt_tokens"],
            row["completion_tokens"],
            row["total_tokens"],
            row["exceeds_max_seq_length"],
        )
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--model-name", default=DEFAULT_MODEL)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = load_jsonl_rows(Path(args.dataset))
    tokenizer = load_tokenizer(args.model_name)
    results = audit_rows(rows, tokenizer, args.max_seq_length)
    summary = summarize_audit(results, args.max_seq_length)
    payload = {"rows": results, "summary": summary}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print_table(results, summary)


if __name__ == "__main__":
    main()

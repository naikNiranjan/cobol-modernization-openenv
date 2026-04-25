"""Root inference entrypoint for OpenEnv submission gates."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence, TextIO
from urllib.parse import urlparse

from openai import OpenAI

from legacy_cobol_env.eval.model_rollout import run_model_repair_rollout, run_model_rollout
from legacy_cobol_env.eval.providers import StaticResponseProvider, TextProvider
from legacy_cobol_env.server.task_bank import TaskInstance, all_tasks, load_task


VALID_MARKERS = {"START", "STEP", "END"}
STATIC_RESPONSE = (
    '{"files":{"src/main/java/com/example/migration/MigrationService.java":'
    '"package com.example.migration;\\n\\npublic final class MigrationService {\\n'
    '    public String migrate(String inputRecord) {\\n'
    '        return inputRecord;\\n'
    '    }\\n}\\n"}}'
)


@dataclass(frozen=True)
class RuntimeConfig:
    api_base_url: str
    model_name: str
    hf_token: str
    mode: str
    api_version: str = "2024-12-01-preview"


def load_runtime_config(env: Mapping[str, str] | None = None, mode: str | None = None) -> RuntimeConfig:
    values = os.environ if env is None else env
    selected_mode = mode or values.get("INFERENCE_MODE") or values.get("MODE") or "live"

    if selected_mode in {"static", "mock"}:
        return RuntimeConfig(
            api_base_url=values.get("API_BASE_URL", ""),
            model_name=values.get("MODEL_NAME", "static"),
            hf_token=values.get("HF_TOKEN", ""),
            mode=selected_mode,
            api_version=values.get("API_VERSION", values.get("OPENAI_API_VERSION", values.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"))),
        )

    required = ["API_BASE_URL", "MODEL_NAME", "HF_TOKEN"]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError(f"missing inference configuration: {', '.join(missing)}")

    return RuntimeConfig(
        api_base_url=values["API_BASE_URL"],
        model_name=values["MODEL_NAME"],
        hf_token=values["HF_TOKEN"],
        mode=selected_mode,
        api_version=values.get("API_VERSION", values.get("OPENAI_API_VERSION", values.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"))),
    )


def format_event(marker: str, payload: Mapping[str, object]) -> str:
    if marker not in VALID_MARKERS:
        raise ValueError(f"invalid log marker: {marker}")
    data = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
    return f"[{marker}] {data}"


def build_openai_client(config: RuntimeConfig) -> OpenAI:
    base_url = config.api_base_url.rstrip("/")
    if _is_azure_endpoint(base_url):
        deployment_base = (
            base_url
            if "/openai/deployments/" in base_url
            else f"{base_url}/openai/deployments/{config.model_name}"
        )
        return OpenAI(
            base_url=deployment_base,
            api_key=config.hf_token,
            default_headers={"api-key": config.hf_token},
            default_query={"api-version": config.api_version},
            timeout=60.0,
        )
    return OpenAI(base_url=base_url, api_key=config.hf_token, timeout=60.0)


class OpenAITextProvider:
    name = "openai-client"

    def __init__(self, client: OpenAI, model_name: str) -> None:
        self._client = client
        self._model_name = model_name

    def generate(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model_name,
            messages=[
                {
                    "role": "system",
                    "content": "Return only JSON with a files object mapping allowed Java source paths to Java source strings.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or ""


def build_provider(config: RuntimeConfig) -> TextProvider:
    if config.mode in {"static", "mock"}:
        return StaticResponseProvider(config.mode, STATIC_RESPONSE)
    return OpenAITextProvider(build_openai_client(config), config.model_name)


def run_inference(task_id: str | None, max_repairs: int, config: RuntimeConfig) -> dict[str, object]:
    tasks = [load_task(task_id=task_id)] if task_id else all_tasks()
    provider = build_provider(config)
    results = [_run_task(task, provider, max_repairs) for task in tasks]

    return {
        "mode": config.mode,
        "model_name": config.model_name,
        "max_repairs": max_repairs,
        "task_count": len(results),
        "mean_public_score": mean(item["score"] for item in results) if results else 0.0,
        "accepted_count": sum(1 for item in results if item["accepted"]),
        "results": results,
    }


def _run_task(task: TaskInstance, provider: TextProvider, max_repairs: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        trajectory = (
            run_model_repair_rollout(task=task, provider=provider, max_repairs=max_repairs)
            if max_repairs > 0
            else run_model_rollout(task=task, provider=provider)
        )
    except Exception as exc:
        return {
            "task_id": task.task_id,
            "family_id": task.family_id,
            "difficulty": task.metadata["difficulty"],
            "score": 0.0,
            "accepted": False,
            "duration_s": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }

    final = trajectory["final"]
    return {
        "task_id": task.task_id,
        "family_id": task.family_id,
        "difficulty": task.metadata["difficulty"],
        "score": final["public_score"],
        "accepted": final["accepted"],
        "visible_pass_rate": trajectory["visible"]["pass_rate"],
        "duration_s": round(time.perf_counter() - started, 3),
        "trajectory": trajectory,
    }


def write_output(path: str | None, payload: Mapping[str, object]) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dict(payload), sort_keys=True, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenEnv root inference gate.")
    parser.add_argument("--task-id")
    parser.add_argument("--max-repairs", type=int, default=0)
    parser.add_argument("--output")
    parser.add_argument("--mode", choices=["live", "static", "mock"])
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
) -> int:
    args = parse_args(argv)
    stream = sys.stdout if stdout is None else stdout
    config = load_runtime_config(env, mode=args.mode)

    print(
        format_event(
            "START",
            {
                "mode": config.mode,
                "model_name": config.model_name,
                "task_id": args.task_id or "all",
                "max_repairs": args.max_repairs,
            },
        ),
        file=stream,
    )
    result = run_inference(args.task_id, args.max_repairs, config)
    for index, task_result in enumerate(result["results"], start=1):
        step_payload = {
            "index": index,
            "task_id": task_result["task_id"],
            "family_id": task_result["family_id"],
            "difficulty": task_result["difficulty"],
            "score": task_result["score"],
            "accepted": task_result["accepted"],
        }
        if "error" in task_result:
            step_payload["error"] = task_result["error"]
        print(format_event("STEP", step_payload), file=stream)
    write_output(args.output, result)
    print(
        format_event(
            "END",
            {
                "mode": config.mode,
                "task_count": result["task_count"],
                "mean_public_score": result["mean_public_score"],
                "accepted_count": result["accepted_count"],
            },
        ),
        file=stream,
    )
    return 0


def _is_azure_endpoint(base_url: str) -> bool:
    host = urlparse(base_url).netloc.lower()
    return "openai.azure.com" in host or "cognitiveservices.azure.com" in host


if __name__ == "__main__":
    raise SystemExit(main())

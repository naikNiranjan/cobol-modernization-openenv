"""Shared state models for the Legacy COBOL Migration Workbench."""

from typing import Any

from openenv.core.env_server.mcp_types import CallToolAction, CallToolObservation
from openenv.core.env_server.types import State
from pydantic import BaseModel, Field


Score = float


class RewardComponents(BaseModel):
    """Public final reward component contract."""

    hidden_correctness: Score = Field(ge=0.0, le=1.0)
    fresh_correctness: Score = Field(ge=0.0, le=1.0)
    interface_contract: Score = Field(ge=0.0, le=1.0)
    type_and_layout_fidelity: Score = Field(ge=0.0, le=1.0)
    anti_hardcoding: Score = Field(ge=0.0, le=1.0)
    safety: Score = Field(ge=0.0, le=1.0)


class RewardResponse(BaseModel):
    """Reward-ish response shared by terminal and scoring payloads."""

    ok: bool
    reward: Score = Field(default=0.0, ge=0.0, le=1.0)
    error: str | None = None


class FinalSubmissionResult(BaseModel):
    """Structured result returned by submit_final."""

    ok: bool
    accepted: bool
    episode_done: bool
    public_score: Score = Field(ge=0.0, le=1.0)
    components: RewardComponents
    hidden_passed: int | None = None
    hidden_total: int | None = None
    fresh_passed: int | None = None
    fresh_total: int | None = None
    notes: str | None = None


class TerminalStepResult(BaseModel):
    """Structured no-op result for blocked episode steps."""

    ok: bool = False
    error: str
    terminal: bool = True


class ToolActionWrapper(CallToolAction):
    """Project-level wrapper for MCP tool actions."""


class ToolObservationWrapper(CallToolObservation):
    """Project-level wrapper for MCP tool observations."""


class LegacyCobolState(State):
    """Inspectable episode state for the migration workbench."""

    task_id: str | None = Field(default=None, description="Selected task ID")
    done: bool = Field(default=False, description="Whether the episode is complete")
    files_read: list[str] = Field(default_factory=list)
    copybooks_read: list[str] = Field(default_factory=list)
    layouts_parsed: list[str] = Field(default_factory=list)
    draft_count: int = Field(default=0)
    visible_runs: int = Field(default=0)
    best_visible_pass_rate: float = Field(default=0.0)
    final_score: float | None = Field(default=None)
    last_tool: str | None = Field(default=None)
    last_result_summary: str | None = Field(default=None)
    reward_components: dict[str, float] = Field(default_factory=dict)
    java_skeleton_generated: bool = Field(default=False)
    java_files: dict[str, str] = Field(default_factory=dict)
    java_draft_id: int | None = Field(default=None)
    java_draft_count: int = Field(default=0)
    java_visible_runs: int = Field(default=0)
    last_java_visible_result: dict[str, Any] | None = Field(default=None)
    last_java_failure_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    java_final_eligible: bool = Field(default=False)

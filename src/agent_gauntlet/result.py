"""Data model for result.json."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Pace = Literal["human", "machine"]
StepStatus = Literal["ok", "failed", "skipped", "not_run"]
ErrorKind = Literal[
    "timeout",
    "intercepted",
    "covered",
    "assertion",
    "safety",
    "navigation",
    "challenge",
    "rate_limit",
    "error",
]


class NetworkNote(BaseModel):
    """A main-frame document response seen during a step."""

    url: str
    status: int
    cf_mitigated: str | None = None


class StepResult(BaseModel):
    index: int
    type: str
    label: str
    status: StepStatus
    duration_ms: int = 0
    url: str | None = None
    error_kind: ErrorKind | None = None
    error: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    screenshot: str | None = None
    network: list[NetworkNote] = Field(default_factory=list)


class PaceResult(BaseModel):
    pace: Pace
    status: Literal["ok", "failed"]
    failed_step: int | None = None
    duration_ms: int = 0
    steps: list[StepResult] = Field(default_factory=list)
    # Only set for early-action retries: (step index, delay in ms) applied before that step.
    extra_delay: tuple[int, int] | None = None
    # Set when a bot challenge was seen; the whole run stops at that point.
    challenge: dict[str, Any] | None = None


class CheckResult(BaseModel):
    id: str
    title: str
    status: Literal["PASS", "WARN", "FAIL", "NOT_TESTED"]
    what_happened: str
    why_agents_care: str
    what_to_try: str
    evidence: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    schema_version: int = 1
    tool: str = "agent-gauntlet"
    tool_version: str
    journey_name: str
    base_url: str
    started_at: str
    finished_at: str
    user_agent: str
    permission: Literal["local", "flag", "journey"]
    paces: list[PaceResult] = Field(default_factory=list)
    retries: list[PaceResult] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    journey_error: str | None = None
    stopped_reason: str | None = None
    notes: list[str] = Field(default_factory=list)
    exit_code: int = 0

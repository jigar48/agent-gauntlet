"""Orchestrates a run: permission gate, both paces, result.json."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from agent_gauntlet import REPO_URL, __version__, safety
from agent_gauntlet.journey import Journey
from agent_gauntlet.result import RunResult
from agent_gauntlet.runner import AttemptBudget, BrowserSession, run_pace

USER_AGENT_ENV = "AGENT_GAUNTLET_USER_AGENT"


class PermissionDenied(Exception):
    pass


def default_user_agent() -> str:
    return os.environ.get(USER_AGENT_ENV) or f"agent-gauntlet/{__version__} (+{REPO_URL})"


def check_permission(journey: Journey, flag: bool) -> str:
    """Return how permission was established, or raise PermissionDenied."""
    if safety.is_local_url(journey.base_url):
        return "local"
    if flag:
        return "flag"
    if journey.permission_confirmed:
        return "journey"
    host = safety.hostname_of(journey.base_url)
    raise PermissionDenied(
        f"{host} is not localhost. Only test sites you own or have written permission to test. "
        "If you do, re-run with --i-have-permission (or set permission_confirmed: true in the "
        "journey file)."
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def execute(
    journey: Journey, *, out_dir: Path, permission: str, headless: bool = True
) -> RunResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    user_agent = default_user_agent()
    budget = AttemptBudget()
    result = RunResult(
        tool_version=__version__,
        journey_name=journey.name,
        base_url=journey.base_url,
        started_at=_now(),
        finished_at=_now(),
        user_agent=user_agent,
        permission=permission,  # type: ignore[arg-type]
    )
    with BrowserSession(headless=headless) as session:
        for pace in ("human", "machine"):
            result.paces.append(
                run_pace(
                    session, journey, pace, out_dir=out_dir, budget=budget, user_agent=user_agent
                )
            )
    result.finished_at = _now()
    result.exit_code = 0 if all(p.status == "ok" for p in result.paces) else 1
    (out_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result

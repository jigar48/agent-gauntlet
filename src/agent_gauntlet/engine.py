"""Orchestrates a run: permission gate, both paces, early-action retries, checks, result.json."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from agent_gauntlet import REPO_URL, __version__, safety
from agent_gauntlet.checks import RETRY_DELAYS_MS, RetryOutcome, evaluate
from agent_gauntlet.journey import Click, Journey
from agent_gauntlet.result import PaceResult, RunResult
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


def _action_step(journey: Journey, failed_step: int) -> int:
    """The step whose timing is blamed: the last click/fill at or before the failing step."""
    for n in range(failed_step, 0, -1):
        if journey.steps[n - 1].type in ("click", "fill"):
            return n
    return failed_step


def _cart_steps_up_to(journey: Journey, n: int) -> int:
    return sum(1 for s in journey.steps[:n] if isinstance(s, Click) and s.tag == "add_to_cart")


def estimate_minimum_delay(
    session: BrowserSession,
    journey: Journey,
    failed_step: int,
    *,
    out_dir: Path,
    budget: AttemptBudget,
    user_agent: str,
) -> tuple[RetryOutcome, list[PaceResult]]:
    """Retry the machine-pace run with fixed delays before the acting step, smallest first."""
    action = _action_step(journey, failed_step)
    outcome = RetryOutcome(action_step=action, failed_step=failed_step)
    runs: list[PaceResult] = []
    needed = _cart_steps_up_to(journey, failed_step)
    for delay in RETRY_DELAYS_MS:
        if budget.remaining < needed:
            outcome.budget_limited = True
            break
        outcome.tried_ms.append(delay)
        run = run_pace(
            session,
            journey,
            "machine",
            out_dir=out_dir,
            budget=budget,
            user_agent=user_agent,
            tag=f"retry{delay}-",
            stop_after=failed_step,
            delay_before=(action, delay),
        )
        runs.append(run)
        if run.status == "ok":
            outcome.min_delay_ms = delay
            break
    return outcome, runs


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
    retry: RetryOutcome | None = None
    with BrowserSession(headless=headless) as session:
        kwargs = {"out_dir": out_dir, "budget": budget, "user_agent": user_agent}
        human = run_pace(session, journey, "human", **kwargs)
        result.paces.append(human)
        if human.challenge:
            result.stopped_reason = "bot challenge detected; run stopped, nothing retried"
        else:
            machine = run_pace(session, journey, "machine", **kwargs)
            result.paces.append(machine)
            if machine.challenge:
                result.stopped_reason = "bot challenge detected; run stopped, nothing retried"
            elif human.status == "ok" and machine.status == "failed":
                bad = machine.steps[(machine.failed_step or 1) - 1]
                if bad.error_kind not in ("safety", "rate_limit"):
                    retry, runs = estimate_minimum_delay(
                        session, journey, machine.failed_step or 1, **kwargs
                    )
                    result.retries.extend(runs)
                    if any(r.challenge for r in runs):
                        result.stopped_reason = "bot challenge detected during retries; run stopped"
    result.checks, result.journey_error = evaluate(journey, result.paces, retry, result.retries)
    if budget.used:
        result.notes.append(
            f"{budget.used} add-to-cart attempt(s) were made (limit {budget.limit} per run). "
            "A live run can leave abandoned carts in the store."
        )
    result.finished_at = _now()
    if result.journey_error:
        result.exit_code = 2
    elif any(c.status == "FAIL" for c in result.checks):
        result.exit_code = 1
    (out_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result

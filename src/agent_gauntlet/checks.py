"""The four checks. Pure functions over recorded paces: no browser needed here."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_gauntlet.journey import Journey
from agent_gauntlet.result import CheckResult, PaceResult, StepResult
from agent_gauntlet.runner import describe_blocker

RETRY_DELAYS_MS = (250, 500, 1000, 2000, 3000)

EARLY = "early-action"
OVERLAY = "overlay"
LOGIN = "login-wall"
BOT = "bot-challenge"


@dataclass
class RetryOutcome:
    """What the early-action delay estimate found."""

    action_step: int
    failed_step: int
    tried_ms: list[int] = field(default_factory=list)
    min_delay_ms: int | None = None
    budget_limited: bool = False
    screenshots: list[str] = field(default_factory=list)


def _failed_step(pace: PaceResult) -> StepResult | None:
    if pace.failed_step is None:
        return None
    return pace.steps[pace.failed_step - 1]


def _login_wall(step: StepResult | None) -> dict | None:
    probe = (step.detail.get("login_probe") if step else None) or None
    return probe if probe and probe.get("wall") else None


def _explained(pace: PaceResult) -> str | None:
    """A failure that another check accounts for (so it is not a broken journey)."""
    step = _failed_step(pace)
    if step is None:
        return None
    if step.error_kind in ("covered", "intercepted"):
        return "a covered click target"
    if _login_wall(step):
        return "a login wall"
    return None


def _evidence(*steps: StepResult | None) -> list[str]:
    return [s.screenshot for s in steps if s is not None and s.screenshot]


def _pace(paces: list[PaceResult], name: str) -> PaceResult | None:
    return next((p for p in paces if p.pace == name), None)


def _later_actions(journey: Journey, after: int) -> bool:
    return any(s.type in ("click", "fill", "goto") for s in journey.steps[after:])


def early_action(
    journey: Journey, paces: list[PaceResult], retry: RetryOutcome | None
) -> tuple[CheckResult, str | None]:
    """Returns the check and, when the journey itself is broken, a journey error message."""
    why = (
        "AI shopping agents act the moment a page is ready, with no human-like pause. If page "
        "scripts are still attaching handlers or tokens, the click does nothing or the server "
        "rejects it."
    )
    base = {"id": EARLY, "title": "Works without waiting", "why_agents_care": why}
    human, machine = _pace(paces, "human"), _pace(paces, "machine")
    if any(p.challenge for p in paces) or human is None or machine is None:
        return (
            CheckResult(
                **base,
                status="NOT_TESTED",
                what_happened="The run stopped at a bot challenge before both paces could finish.",
                what_to_try="Resolve the bot-challenge finding first, then run again.",
            ),
            None,
        )
    for p in paces:
        bad = _failed_step(p)
        if bad and bad.error_kind in ("safety", "rate_limit"):
            return (
                CheckResult(
                    **base,
                    status="NOT_TESTED",
                    what_happened=f"Step {bad.index} was stopped by a safety limit: {bad.error}.",
                    what_to_try="Change the journey so it stops before payment and stays "
                    "within the add-to-cart limit.",
                ),
                f"Step {bad.index} ({bad.label}) was refused: {bad.error}",
            )
    h_bad, m_bad = _failed_step(human), _failed_step(machine)
    if h_bad is None and m_bad is None:
        return (
            CheckResult(
                **base,
                status="PASS",
                what_happened="Every step worked the same whether the journey was paced like a "
                "person or run instantly.",
                what_to_try="Nothing to change.",
            ),
            None,
        )
    if h_bad is None and m_bad is not None:
        assert retry is not None
        if retry.min_delay_ms is not None:
            estimate = (
                f"It worked once the page had been given about {retry.min_delay_ms} ms "
                f"(tried {', '.join(str(d) for d in retry.tried_ms)} ms)."
            )
        elif retry.budget_limited:
            estimate = "The delay estimate was cut short by the add-to-cart attempt limit."
        else:
            estimate = (
                f"It still failed after waiting up to {max(retry.tried_ms, default=0)} ms, so "
                "the cause may not be a simple delay."
            )
        action = journey.steps[retry.action_step - 1]
        where = (
            f"Step {m_bad.index} ({m_bad.label}) failed"
            if retry.action_step == m_bad.index
            else f"Step {m_bad.index} ({m_bad.label}) failed after step {retry.action_step} "
            f"({action.type}) acted too early"
        )
        return (
            CheckResult(
                **base,
                status="FAIL",
                what_happened=f"{where} when run instantly, but works after waiting. {estimate}",
                what_to_try="Look for scripts that run after page load (form keys, tokens, "
                "handlers). Keep the button disabled until they are ready, or have the page "
                "finish setup before the button can be clicked.",
                evidence=_evidence(m_bad, human.steps[m_bad.index - 1]),
                detail={
                    "failed_step": m_bad.index,
                    "action_step": retry.action_step,
                    "tried_ms": retry.tried_ms,
                    "minimum_working_delay_ms": retry.min_delay_ms,
                },
            ),
            None,
        )
    if h_bad is not None and m_bad is None:
        return (
            CheckResult(
                **base,
                status="PASS",
                what_happened=f"The instant run completed. (The paced run failed at step "
                f"{h_bad.index} ({h_bad.label}): {h_bad.error}. See the other checks.)",
                what_to_try="Review the failing paced run; it may point to something that "
                "appears later, such as a pop-up.",
                evidence=_evidence(h_bad),
            ),
            None,
        )
    assert h_bad is not None and m_bad is not None
    reasons = (_explained(human), _explained(machine))
    if all(reasons):
        warn = _later_actions(journey, max(h_bad.index, m_bad.index))
        return (
            CheckResult(
                **base,
                status="WARN" if warn else "PASS",
                what_happened=f"Both paces stopped at step {m_bad.index} because of "
                f"{reasons[1]}; steps before it behaved the same at both speeds."
                + (" Steps after it could not be compared." if warn else ""),
                what_to_try="Fix the blocking problem (see the other checks), then run again.",
                evidence=_evidence(m_bad),
            ),
            None,
        )
    return (
        CheckResult(
            **base,
            status="NOT_TESTED",
            what_happened="The journey fails at both speeds, so timing could not be compared.",
            what_to_try="Fix the journey file (selector, expected text) and run again.",
            evidence=_evidence(m_bad),
        ),
        f"Step {m_bad.index} ({m_bad.label}) fails at both paces: {m_bad.error}. "
        "The journey itself is broken (wrong selector or text, or the page is down), "
        "not a timing problem.",
    )


def overlay(journey: Journey, paces: list[PaceResult]) -> CheckResult:
    why = (
        "A pop-up, cookie banner or modal sitting on top of a button means the click lands on "
        "the pop-up instead. Agents do not dismiss it the way a person would."
    )
    base = {"id": OVERLAY, "title": "Nothing covers the buttons", "why_agents_care": why}
    clicks = [n for n, s in enumerate(journey.steps, start=1) if s.type == "click"]
    if not clicks:
        return CheckResult(
            **base,
            status="NOT_TESTED",
            what_happened="The journey has no click steps, so there was nothing to check.",
            what_to_try="Add the clicks an agent would make (product, add to cart, checkout).",
        )
    for pace in paces:
        for step in pace.steps:
            if step.error_kind not in ("covered", "intercepted"):
                continue
            blocker = step.detail.get("blocker")
            what = (
                f"At step {step.index} ({step.label}) another element was on top of the "
                f"target at {pace.pace} pace: "
                + (describe_blocker(blocker) if blocker else step.error or "unknown element")
                + "."
            )
            return CheckResult(
                **base,
                status="FAIL",
                what_happened=what,
                what_to_try="Make the pop-up dismissible without blocking the main buttons, "
                "delay it until after the key actions, or avoid covering the page entirely.",
                evidence=_evidence(step),
                detail={"step": step.index, "pace": pace.pace, "blocker": blocker},
            )
    checked = {s.index for p in paces for s in p.steps if s.type == "click" and s.status == "ok"}
    if set(clicks) <= checked:
        return CheckResult(
            **base,
            status="PASS",
            what_happened=f"All {len(clicks)} click targets were uncovered when clicked.",
            what_to_try="Nothing to change.",
        )
    return CheckResult(
        **base,
        status="NOT_TESTED",
        what_happened=f"Only {len(checked)} of {len(clicks)} click steps were reached, and "
        "none of those was covered.",
        what_to_try="Fix the problem that stopped the run, then run again.",
    )


def login_wall(journey: Journey, paces: list[PaceResult]) -> CheckResult:
    why = (
        "Agents act for a shopper but have no account credentials or one-time codes, so a "
        "forced sign-in ends the purchase."
    )
    base = {"id": LOGIN, "title": "No login wall at checkout", "why_agents_care": why}
    checkout = journey.checkout_step
    if checkout is None:
        return CheckResult(
            **base,
            status="NOT_TESTED",
            what_happened="No step is tagged as the checkout step.",
            what_to_try="Add 'tag: checkout' to the click that goes to checkout.",
        )
    seen: list[tuple[PaceResult, StepResult, dict]] = []
    for pace in paces:
        for step in pace.steps:
            probe = step.detail.get("login_probe")
            if probe and step.index >= checkout:
                seen.append((pace, step, probe))
    for pace, step, probe in seen:
        if probe["wall"]:
            return CheckResult(
                **base,
                status="WARN",
                what_happened="After the checkout step the page looks like a login or code "
                f"wall ({'; '.join(probe['reasons'])}). An agent cannot continue without "
                "credentials.",
                what_to_try="Offer guest checkout, or tell agent-using shoppers how to "
                "proceed. If this is a false alarm, adjust login_markers in the journey.",
                evidence=_evidence(step),
                detail={"pace": pace.pace, "url": probe["url"], "reasons": probe["reasons"]},
            )
    if seen:
        return CheckResult(
            **base,
            status="PASS",
            what_happened="The checkout page opened without a login or one-time-code wall.",
            what_to_try="Nothing to change.",
        )
    return CheckResult(
        **base,
        status="NOT_TESTED",
        what_happened="The run never reached the checkout step.",
        what_to_try="Fix the problem that stopped the run, then run again.",
    )


def bot_challenge(journey: Journey, paces: list[PaceResult]) -> CheckResult:
    why = (
        "If a site shows a challenge or blocks automated visitors, an agent cannot finish. "
        "agent-gauntlet reports it and stops; it never tries to get past one."
    )
    base = {"id": BOT, "title": "No bot challenge", "why_agents_care": why}
    for pace in paces:
        if pace.challenge:
            step = _failed_step(pace)
            return CheckResult(
                **base,
                status="FAIL",
                what_happened=f"At step {step.index if step else '?'} the site showed a "
                f"challenge or block ({pace.challenge['signal']}) at {pace.pace} pace. The "
                "run stopped and nothing was retried.",
                what_to_try="If you own the site, allow-list the audit's IP or its User-Agent "
                "in your bot protection, or test a staging copy. Do not try to bypass it.",
                evidence=_evidence(step),
                detail=pace.challenge,
            )
    return CheckResult(
        **base,
        status="PASS",
        what_happened="No 403, 429 or 503 page, challenge header or challenge text was seen.",
        what_to_try="Nothing to change. Other IPs or heavier traffic may still be challenged.",
    )


def evaluate(
    journey: Journey,
    paces: list[PaceResult],
    retry: RetryOutcome | None,
    retries: list[PaceResult] | None = None,
) -> tuple[list[CheckResult], str | None]:
    early, journey_error = early_action(journey, paces, retry)
    checks = [
        early,
        overlay(journey, paces),
        login_wall(journey, paces),
        bot_challenge(journey, paces + (retries or [])),
    ]
    return checks, journey_error

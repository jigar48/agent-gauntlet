"""Plain-English scorecard: 'N of 4 checks passed' and one verdict per check. No fake score."""

from __future__ import annotations

from agent_gauntlet.result import CheckResult, RunResult

DISCLAIMER = (
    "This is not a certification and does not simulate any specific AI product. A pass is "
    "not a guarantee: results depend on the site, the IP address and bot protection."
)


def passed_count(result: RunResult) -> int:
    return sum(1 for c in result.checks if c.status == "PASS")


def headline(result: RunResult) -> str:
    total = len(result.checks)
    line = f"{passed_count(result)} of {total} checks passed"
    extras = []
    for status, word in (("FAIL", "failed"), ("WARN", "warning"), ("NOT_TESTED", "not tested")):
        n = sum(1 for c in result.checks if c.status == status)
        if n:
            extras.append(f"{n} {word}")
    return f"{line} ({', '.join(extras)})" if extras else line


def verdict(check: CheckResult) -> str:
    """One line: what happened, why agents care, what to try."""
    return f"{check.what_happened} Why it matters: {check.why_agents_care} Try: {check.what_to_try}"


def scorecard_text(result: RunResult) -> str:
    lines = [f"agent-gauntlet scorecard: {result.journey_name}", headline(result), ""]
    if result.journey_error:
        lines += [f"JOURNEY ERROR: {result.journey_error}", ""]
    for check in result.checks:
        lines.append(f"[{check.status}] {check.title}")
        lines.append(f"    {verdict(check)}")
    if result.stopped_reason:
        lines += ["", f"Run stopped: {result.stopped_reason}"]
    lines += ["", DISCLAIMER]
    return "\n".join(lines)

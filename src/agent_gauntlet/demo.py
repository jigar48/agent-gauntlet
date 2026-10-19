"""`agent-gauntlet demo`: audit every built-in fixture shop, all on localhost."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path

from agent_gauntlet import AUTHOR, REPO_URL, __version__
from agent_gauntlet.engine import execute
from agent_gauntlet.fixtures.journeys import fixture_journey
from agent_gauntlet.fixtures.shops import VARIANT_TITLES, serve_shop
from agent_gauntlet.journey import parse_journey
from agent_gauntlet.report import CSS, write_report
from agent_gauntlet.result import RunResult
from agent_gauntlet.scorecard import headline

# What each fake shop is built to show. The demo flags any shop that does not behave this way.
EXPECTED: dict[str, dict[str, str]] = {
    "clean": {
        "early-action": "PASS",
        "overlay": "PASS",
        "login-wall": "PASS",
        "bot-challenge": "PASS",
    },
    "slow-scripts": {"early-action": "FAIL"},
    "overlay": {"overlay": "FAIL"},
    "login-wall": {"login-wall": "WARN"},
    "bot-challenge": {"bot-challenge": "FAIL"},
}


@dataclass
class DemoEntry:
    variant: str
    title: str
    result: RunResult
    as_designed: bool


def _as_designed(variant: str, result: RunResult) -> bool:
    found = {c.id: c.status for c in result.checks}
    return all(found.get(cid) == want for cid, want in EXPECTED[variant].items())


def run_demo(
    out_dir: Path,
    variants: list[str] | None = None,
    log: Callable[[str], None] = lambda _msg: None,
) -> list[DemoEntry]:
    entries: list[DemoEntry] = []
    for variant in variants or list(VARIANT_TITLES):
        log(f"Auditing fixture shop: {variant}")
        with serve_shop(variant) as shop:
            journey = parse_journey(fixture_journey(shop.base_url, variant))
            variant_dir = out_dir / variant
            result = execute(journey, out_dir=variant_dir, permission="local")
        write_report(result, variant_dir)
        entries.append(
            DemoEntry(variant, VARIANT_TITLES[variant], result, _as_designed(variant, result))
        )
    (out_dir / "index.html").write_text(render_index(entries), encoding="utf-8")
    return entries


def render_index(entries: list[DemoEntry]) -> str:
    cards = ""
    for e in entries:
        cards += f"""<section class="card"><h3><a href="{escape(e.variant)}/report.html">{escape(e.variant)}</a></h3>
<p>{escape(e.title)}</p>
<p><strong>{escape(headline(e.result))}</strong></p>
<p class="small">{"Behaved as designed." if e.as_designed else "Did NOT behave as designed."}</p></section>"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>agent-gauntlet demo reports</title><style>{CSS}</style></head><body><main>
<h1>agent-gauntlet demo</h1>
<p class="err" role="note">These are five FAKE fixture shops served on localhost by
agent-gauntlet itself. No real store was tested. Each shop is built to show one finding.</p>
<p>Results below come from running <code>agent-gauntlet demo</code>. This is not a certification and
a pass is not a guarantee for a real site.</p>
{cards}
<footer><p class="small">agent-gauntlet {escape(__version__)} by {escape(AUTHOR)} &middot;
<a href="{escape(REPO_URL)}">source code</a></p></footer></main></body></html>
"""

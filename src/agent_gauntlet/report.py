"""Self-contained report.html. Standard-library templating; all dynamic text is escaped."""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

from agent_gauntlet import AUTHOR, REPO_URL
from agent_gauntlet.result import CheckResult, PaceResult, RunResult
from agent_gauntlet.scorecard import DISCLAIMER, headline

MAX_EMBED_BYTES = 1_500_000

CSS = """
:root{color-scheme:light dark;--bg:#fff;--fg:#1c1f24;--muted:#5b6470;--card:#f5f7fa;--line:#d9dee5;
--pass:#0f7b3a;--warn:#8a5a00;--fail:#b3261e;--nt:#4a5565;--link:#0b57d0}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e8ebef;--muted:#a3adba;--card:#1d222a;
--line:#2f3743;--pass:#4cc98a;--warn:#f0b957;--fail:#ff8a80;--nt:#a3adba;--link:#8ab4ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:1.5rem;margin:.2em 0}h2{font-size:1.15rem;margin:1.6em 0 .5em}
.meta,.small{color:var(--muted);font-size:.9rem}
.score{font-size:1.6rem;font-weight:700;margin:.4em 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:12px 0}
.card h3{margin:0 0 6px;font-size:1.05rem}
.badge{display:inline-block;font-size:.8rem;font-weight:700;padding:2px 8px;border-radius:999px;
border:2px solid currentColor;margin-right:8px;vertical-align:middle}
.PASS{color:var(--pass)}.WARN{color:var(--warn)}.FAIL{color:var(--fail)}.NOT_TESTED{color:var(--nt)}
dl{margin:8px 0 0}dt{font-weight:600;margin-top:8px}dd{margin:0}
img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:6px;margin-top:8px}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}
td.num{white-space:nowrap}
.wrap{overflow-x:auto}details{margin:8px 0}summary{cursor:pointer}
a{color:var(--link)}footer{margin-top:2em;border-top:1px solid var(--line);padding-top:12px}
.err{padding:10px;border:2px solid var(--fail);border-radius:8px;color:var(--fail)}
"""

STATUS_WORD = {"PASS": "Pass", "WARN": "Warning", "FAIL": "Fail", "NOT_TESTED": "Not tested"}


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _embed(base_dir: Path | None, rel: str) -> str | None:
    """Return a data: URI for an evidence screenshot, or None if it cannot be embedded."""
    if base_dir is None:
        return None
    path = (base_dir / rel).resolve()
    try:
        path.relative_to(base_dir.resolve())
    except ValueError:
        return None
    if not path.is_file() or path.stat().st_size > MAX_EMBED_BYTES:
        return None
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _check_html(check: CheckResult, base_dir: Path | None) -> str:
    imgs = ""
    for rel in check.evidence:
        uri = _embed(base_dir, rel)
        if uri:
            imgs += f'<img loading="lazy" src="{uri}" alt="Evidence screenshot: {_e(rel)}">'
        else:
            imgs += f'<p class="small">Screenshot: {_e(rel)}</p>'
    return f"""<section class="card">
<h3><span class="badge {_e(check.status)}">{_e(STATUS_WORD[check.status])}</span>{_e(check.title)}</h3>
<dl><dt>What happened</dt><dd>{_e(check.what_happened)}</dd>
<dt>Why agents care</dt><dd>{_e(check.why_agents_care)}</dd>
<dt>What to try</dt><dd>{_e(check.what_to_try)}</dd></dl>{imgs}</section>"""


def _pace_html(pace: PaceResult, title: str) -> str:
    rows = ""
    for s in pace.steps:
        note = s.error or ""
        rows += (
            f"<tr><td class='num'>{s.index}</td><td>{_e(s.label)}</td><td>{_e(s.status)}</td>"
            f"<td class='num'>{s.duration_ms} ms</td><td>{_e(note)}</td></tr>"
        )
    return f"""<details><summary>{_e(title)}: {_e(pace.status)}, {pace.duration_ms} ms</summary>
<div class="wrap"><table><thead><tr><th>#</th><th>Step</th><th>Result</th><th>Time</th>
<th>Note</th></tr></thead><tbody>{rows}</tbody></table></div></details>"""


def render_html(result: RunResult, base_dir: Path | None = None) -> str:
    """Build the full report. `base_dir` is where result.json and screenshots/ live."""
    checks = "".join(_check_html(c, base_dir) for c in result.checks)
    paces = "".join(_pace_html(p, f"{p.pace.capitalize()} pace") for p in result.paces)
    retries = "".join(
        _pace_html(p, f"Retry with {p.extra_delay[1] if p.extra_delay else '?'} ms delay")
        for p in result.retries
    )
    error = (
        f'<p class="err" role="alert"><strong>Journey error:</strong> '
        f"{_e(result.journey_error)}</p>"
        if result.journey_error
        else ""
    )
    stopped = (
        f'<p class="small">Run stopped: {_e(result.stopped_reason)}</p>'
        if result.stopped_reason
        else ""
    )
    notes = "".join(f"<li>{_e(n)}</li>" for n in result.notes)
    notes_html = f"<h2>Notes</h2><ul>{notes}</ul>" if notes else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>agent-gauntlet report: {_e(result.journey_name)}</title>
<style>{CSS}</style></head><body><main>
<h1>{_e(result.journey_name)}</h1>
<p class="meta">{_e(result.base_url)} &middot; {_e(result.started_at)} &middot;
agent-gauntlet {_e(result.tool_version)}</p>
<p class="score" role="status">{_e(headline(result))}</p>
{error}{stopped}
<h2>The four checks</h2>
{checks}
<h2>Step details</h2>
{paces}{retries}
{notes_html}
<footer><p class="small">{_e(DISCLAIMER)} Only test sites you own or have written permission
to test. agent-gauntlet stops before payment and never places an order.</p>
<p class="small">Generated by <a href="{_e(REPO_URL)}">agent-gauntlet</a>, an open-source tool
by {_e(AUTHOR)}. User-Agent used: {_e(result.user_agent)}</p></footer>
</main></body></html>
"""


def write_report(result: RunResult, out_dir: Path) -> Path:
    path = out_dir / "report.html"
    path.write_text(render_html(result, out_dir), encoding="utf-8")
    return path

import json
from pathlib import Path

from agent_gauntlet.cli import main
from agent_gauntlet.report import render_html
from agent_gauntlet.result import CheckResult, PaceResult, RunResult, StepResult
from agent_gauntlet.scorecard import headline, scorecard_text

XSS = '<script>alert("x")</script>'


def make_result(**over) -> RunResult:
    checks = [
        CheckResult(
            id="early-action",
            title="Works without waiting",
            status="FAIL",
            what_happened=f"Step 3 failed {XSS}",
            why_agents_care="agents are fast",
            what_to_try="wait for scripts",
            evidence=["screenshots/a.png"],
        ),
        CheckResult(
            id="overlay",
            title="Nothing covers the buttons",
            status="PASS",
            what_happened="ok",
            why_agents_care="w",
            what_to_try="n",
        ),
        CheckResult(
            id="login-wall",
            title="No login wall",
            status="WARN",
            what_happened="wall",
            why_agents_care="w",
            what_to_try="t",
        ),
        CheckResult(
            id="bot-challenge",
            title="No bot challenge",
            status="NOT_TESTED",
            what_happened="x",
            why_agents_care="w",
            what_to_try="t",
        ),
    ]
    step = StepResult(index=1, type="goto", label=f"go to {XSS}", status="ok", error=XSS)
    base = {
        "tool_version": "0.1.0",
        "journey_name": f"Shop {XSS}",
        "base_url": "http://localhost:1",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:01+00:00",
        "user_agent": f"ua {XSS}",
        "permission": "local",
        "paces": [PaceResult(pace="human", status="ok", steps=[step])],
        "checks": checks,
        "journey_error": f"broken {XSS}",
        "notes": [f"note {XSS}"],
    }
    return RunResult(**{**base, **over})


def test_headline_counts_and_no_numeric_score():
    result = make_result()
    assert headline(result) == "1 of 4 checks passed (1 failed, 1 warning, 1 not tested)"
    text = scorecard_text(result)
    assert "[FAIL] Works without waiting" in text and "not a certification" in text
    assert "/100" not in text and "score:" not in text.lower()


def test_report_escapes_every_dynamic_string():
    html = render_html(make_result())
    assert "<script>alert" not in html
    assert html.count("&lt;script&gt;") >= 6  # name, step, error, journey error, note, ua, check


def test_report_is_self_contained_mobile_and_dark_mode_aware():
    html = render_html(make_result())
    assert 'name="viewport"' in html
    assert "prefers-color-scheme:dark" in html
    assert 'name="robots" content="noindex' in html
    for needle in ("http://", "https://"):
        # only the project link and the (escaped) base url may appear; no CDN or external asset
        for part in html.split(needle)[1:]:
            assert part.startswith(("github.com/jigar48/agent-gauntlet", "localhost:1"))
    assert "<link" not in html and 'src="http' not in html


def test_report_embeds_evidence_screenshot_as_data_uri(tmp_path: Path):
    (tmp_path / "screenshots").mkdir()
    (tmp_path / "screenshots" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    html = render_html(make_result(), tmp_path)
    assert "data:image/png;base64," in html


def test_report_refuses_to_embed_paths_outside_output_dir(tmp_path: Path):
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()
    result = make_result()
    result.checks[0].evidence = ["../secret.png"]
    assert "data:image/png" not in render_html(result, out)


def test_report_command_reads_result_json(tmp_path: Path, capsys):
    path = tmp_path / "result.json"
    path.write_text(make_result().model_dump_json(indent=2), encoding="utf-8")
    assert main(["report", str(path)]) == 0
    assert (tmp_path / "report.html").is_file()
    assert "1 of 4 checks passed" in capsys.readouterr().out


def test_report_command_rejects_bad_file(tmp_path: Path, capsys):
    path = tmp_path / "result.json"
    path.write_text(json.dumps({"nope": 1}), encoding="utf-8")
    assert main(["report", str(path)]) == 2
    assert "Cannot read a result" in capsys.readouterr().err
    assert main(["report", str(tmp_path / "missing.json")]) == 2

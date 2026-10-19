from pathlib import Path

import yaml

from agent_gauntlet.cli import main

ROOT = Path(__file__).resolve().parent.parent


def test_demo_command_audits_every_variant_as_designed(tmp_path: Path, capsys):
    assert main(["demo", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    for variant in ("clean", "slow-scripts", "overlay", "login-wall", "bot-challenge"):
        assert (tmp_path / variant / "result.json").is_file()
        assert (tmp_path / variant / "report.html").is_file()
        assert f"ok {variant}" in out
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "FAKE fixture shops" in index and 'content="noindex' in index
    assert "4 of 4 checks passed" in (tmp_path / "clean" / "report.html").read_text("utf-8")


def test_action_metadata_is_a_safe_composite_action():
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    assert action["runs"]["using"] == "composite"
    assert action["inputs"]["journey"]["required"] is True
    assert action["inputs"]["permission-confirmed"]["default"] == "false"
    for step in action["runs"]["steps"]:
        if "run" in step:
            assert step["shell"] == "bash"
            # inputs must reach scripts through env vars, never interpolated into the script
            assert "${{" not in step["run"]


def test_example_workflow_has_no_schedule_trigger():
    wf = yaml.safe_load((ROOT / "examples" / "github-workflow.yml").read_text(encoding="utf-8"))
    triggers = wf.get("on") or wf.get(True)
    assert "schedule" not in triggers

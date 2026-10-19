import pytest

from agent_gauntlet import REPO_URL, __version__
from agent_gauntlet.cli import main
from agent_gauntlet.engine import PermissionDenied, check_permission, default_user_agent
from agent_gauntlet.journey import parse_journey


def journey(url, **extra):
    return parse_journey({"name": "t", "base_url": url, "steps": [{"goto": "/"}], **extra})


@pytest.mark.parametrize("url", ["http://localhost:1", "http://127.0.0.1:9", "http://[::1]:3"])
def test_local_hosts_need_no_flag(url):
    assert check_permission(journey(url), False) == "local"


def test_remote_host_needs_flag_or_journey_setting():
    with pytest.raises(PermissionDenied):
        check_permission(journey("https://shop.example"), False)
    assert check_permission(journey("https://shop.example"), True) == "flag"
    assert (
        check_permission(journey("https://shop.example", permission_confirmed=True), False)
        == "journey"
    )


def test_cli_exit_2_without_permission(tmp_path, capsys):
    path = tmp_path / "j.yml"
    path.write_text("name: t\nbase_url: https://shop.example\nsteps:\n  - goto: /\n")
    assert main(["run", str(path), "--out", str(tmp_path / "o")]) == 2
    assert "--i-have-permission" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()


def test_cli_exit_2_on_bad_journey(tmp_path, capsys):
    path = tmp_path / "j.yml"
    path.write_text("name: t\nbase_url: http://localhost:1\nsteps:\n  - click: {}\n")
    assert main(["run", str(path)]) == 2
    assert "step 1 > click: selector is required" in capsys.readouterr().err


def test_user_agent_default_and_override(monkeypatch):
    monkeypatch.delenv("AGENT_GAUNTLET_USER_AGENT", raising=False)
    assert default_user_agent() == f"agent-gauntlet/{__version__} (+{REPO_URL})"
    monkeypatch.setenv("AGENT_GAUNTLET_USER_AGENT", "custom/1")
    assert default_user_agent() == "custom/1"

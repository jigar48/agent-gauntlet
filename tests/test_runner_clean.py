import json

import pytest

from agent_gauntlet.engine import execute
from agent_gauntlet.fixtures.journeys import fixture_journey
from agent_gauntlet.fixtures.shops import serve_shop
from agent_gauntlet.journey import parse_journey
from agent_gauntlet.runner import AttemptBudget, BrowserSession, run_pace


@pytest.fixture(scope="module")
def session():
    with BrowserSession() as s:
        yield s


def test_clean_shop_passes_both_paces_and_writes_result(tmp_path):
    with serve_shop("clean") as shop:
        journey = parse_journey(fixture_journey(shop.base_url))
        result = execute(journey, out_dir=tmp_path, permission="local")
        state = json.loads(
            __import__("urllib.request").request.urlopen(shop.base_url + "/__state").read()
        )
    assert [p.status for p in result.paces] == ["ok", "ok"]
    assert result.exit_code == 0
    assert state["cart_items"] == 2  # one add per pace, nothing else
    data = json.loads((tmp_path / "result.json").read_text())
    assert data["tool"] == "agent-gauntlet" and data["paces"][0]["pace"] == "human"
    assert (tmp_path / "screenshots").is_dir() and any((tmp_path / "screenshots").iterdir())
    assert "agent-gauntlet/" in data["user_agent"]


def test_machine_pace_skips_wait_and_human_pace_honours_it(session, tmp_path):
    with serve_shop("clean") as shop:
        raw = fixture_journey(shop.base_url)
        raw["steps"].insert(1, {"wait": 700})
        journey = parse_journey(raw)
        human = run_pace(
            session, journey, "human", out_dir=tmp_path, budget=AttemptBudget(), user_agent="t"
        )
        machine = run_pace(
            session, journey, "machine", out_dir=tmp_path, budget=AttemptBudget(), user_agent="t"
        )
    assert human.steps[1].status == "ok" and human.steps[1].duration_ms >= 650
    assert machine.steps[1].status == "skipped"
    assert machine.duration_ms < human.duration_ms


def test_add_to_cart_attempts_are_capped(session, tmp_path):
    with serve_shop("clean") as shop:
        raw = fixture_journey(shop.base_url)
        journey = parse_journey(raw)
        budget = AttemptBudget(limit=1)
        first = run_pace(
            session, journey, "machine", out_dir=tmp_path, budget=budget, user_agent="t"
        )
        second = run_pace(
            session, journey, "machine", out_dir=tmp_path, budget=budget, user_agent="t"
        )
    assert first.status == "ok"
    assert (
        second.status == "failed"
        and second.steps[second.failed_step - 1].error_kind == "rate_limit"
    )


def test_runtime_guard_refuses_order_button_by_text(session, tmp_path):
    with serve_shop("clean") as shop:
        raw = fixture_journey(shop.base_url)
        # selector is innocent; the visible text "Place order" is what gets refused
        raw["steps"] += [{"click": "button.nonexistent, form button"}]
        journey = parse_journey(raw)
        pace = run_pace(
            session, journey, "machine", out_dir=tmp_path, budget=AttemptBudget(), user_agent="t"
        )
    last = pace.steps[-1]
    assert last.status == "failed" and last.error_kind == "safety"


def test_runtime_guard_refuses_card_field_by_attributes(session, tmp_path):
    with serve_shop("clean") as shop:
        raw = fixture_journey(shop.base_url)
        raw["steps"] += [{"fill": {"selector": "input[autocomplete]", "value": "4111"}}]
        journey = parse_journey(raw)
        pace = run_pace(
            session, journey, "machine", out_dir=tmp_path, budget=AttemptBudget(), user_agent="t"
        )
    last = pace.steps[-1]
    assert last.status == "failed" and last.error_kind == "safety"


def test_delay_before_and_stop_after(session, tmp_path):
    with serve_shop("clean") as shop:
        journey = parse_journey(fixture_journey(shop.base_url))
        pace = run_pace(
            session,
            journey,
            "machine",
            out_dir=tmp_path,
            budget=AttemptBudget(),
            user_agent="t",
            stop_after=3,
            delay_before=(3, 300),
        )
    assert pace.steps[2].status == "ok" and pace.steps[3].status == "not_run"
    assert pace.extra_delay == (3, 300)

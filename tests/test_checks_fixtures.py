"""Each check must FAIL (or WARN) on its fixture variant and PASS on the clean shop.

Everything runs against local fixture shops; no internet is used.
"""

import json
import urllib.request
from pathlib import Path

import pytest

from agent_gauntlet.engine import execute
from agent_gauntlet.fixtures.journeys import fixture_journey
from agent_gauntlet.fixtures.shops import VARIANT_TITLES, serve_shop
from agent_gauntlet.journey import parse_journey


def run_variant(variant: str, out_dir: Path, mutate=None):
    with serve_shop(variant) as shop:
        raw = fixture_journey(shop.base_url, variant)
        if mutate:
            mutate(raw)
        result = execute(parse_journey(raw), out_dir=out_dir, permission="local")
        state = json.loads(urllib.request.urlopen(shop.base_url + "/__state").read())
        hits = list(shop.state.hits)
    return result, state, hits, out_dir


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    return {v: run_variant(v, tmp_path_factory.mktemp(v)) for v in VARIANT_TITLES}


def statuses(result):
    return {c.id: c.status for c in result.checks}


def check(result, check_id):
    return next(c for c in result.checks if c.id == check_id)


def test_clean_passes_all_four(runs):
    result, state, _, _ = runs["clean"]
    assert statuses(result) == {
        "early-action": "PASS",
        "overlay": "PASS",
        "login-wall": "PASS",
        "bot-challenge": "PASS",
    }
    assert result.exit_code == 0 and result.journey_error is None
    assert state["cart_items"] == 2 and result.retries == []


def test_slow_scripts_fails_early_action_and_estimates_delay(runs):
    result, state, _, _ = runs["slow-scripts"]
    assert statuses(result) == {
        "early-action": "FAIL",
        "overlay": "PASS",
        "login-wall": "PASS",
        "bot-challenge": "PASS",
    }
    early = check(result, "early-action")
    assert early.detail["last_failing_delay_ms"] == 1000
    assert early.detail["first_passing_delay_ms"] == 2000
    assert "somewhere between 1000 and 2000 ms" in early.what_happened
    assert "about" not in early.what_happened.split("works after waiting.")[1]
    assert early.detail["tried_ms"] == [250, 500, 1000, 2000]
    assert "works after waiting" in early.what_happened
    assert result.exit_code == 1
    assert state["bad_form_key"] >= 1  # the Magento-style "Invalid Form Key" race was reproduced
    assert state["add_attempts"] <= 6  # attempt cap respected
    assert any("add-to-cart attempt" in n for n in result.notes)


def test_overlay_fails_overlay_check_with_blocker_and_screenshot(runs):
    result, _, _, out_dir = runs["overlay"]
    overlay = check(result, "overlay")
    assert overlay.status == "FAIL"
    assert overlay.detail["blocker"]["id"] == "promo-modal"
    assert overlay.detail["blocker"]["tag"] == "div"
    assert "promo-modal" in overlay.what_happened
    assert overlay.evidence and overlay.evidence[0].endswith(".png")
    assert (out_dir / overlay.evidence[0]).is_file()
    assert check(result, "early-action").status != "FAIL"
    assert result.exit_code == 1


def test_login_wall_warns_not_fails(runs):
    result, _, _, _ = runs["login-wall"]
    wall = check(result, "login-wall")
    assert wall.status == "WARN"
    assert "cannot continue without credentials" in wall.what_happened
    assert not any(c.status == "FAIL" for c in result.checks)
    assert result.exit_code == 0


def test_bot_challenge_fails_stops_and_marks_later_checks_not_tested(runs):
    result, _, hits, _ = runs["bot-challenge"]
    assert check(result, "bot-challenge").status == "FAIL"
    assert check(result, "early-action").status == "NOT_TESTED"
    assert check(result, "overlay").status == "NOT_TESTED"
    assert check(result, "login-wall").status == "NOT_TESTED"
    assert len(result.paces) == 1 and result.stopped_reason
    assert hits.count("GET /product") == 1  # never retried
    assert result.exit_code == 1


def test_broken_journey_is_exit_2_and_not_blamed_on_timing(tmp_path):
    def mutate(raw):
        raw["steps"].insert(2, {"click": {"selector": "#does-not-exist", "timeout_ms": 400}})

    result, _, _, _ = run_variant("clean", tmp_path, mutate)
    assert result.journey_error and "fails at both paces" in result.journey_error
    assert result.exit_code == 2
    assert check(result, "early-action").status == "NOT_TESTED"


def test_result_json_contains_checks(runs):
    result, _, _, _ = runs["clean"]
    assert [c.id for c in result.checks] == [
        "early-action",
        "overlay",
        "login-wall",
        "bot-challenge",
    ]


def _early(retry):
    from agent_gauntlet.checks import early_action
    from agent_gauntlet.result import PaceResult, StepResult

    journey = parse_journey(fixture_journey("http://127.0.0.1:1"))
    ok = [StepResult(index=n, type="x", label="s", status="ok") for n in range(1, 11)]
    bad = [*ok[:3], StepResult(index=4, type="x", label="s", status="failed", error="e"), *ok[4:]]
    paces = [
        PaceResult(pace="human", status="ok", steps=ok),
        PaceResult(pace="machine", status="failed", failed_step=4, steps=bad),
    ]
    return early_action(journey, paces, retry)[0]


def test_delay_range_wording_for_each_retry_outcome():
    from agent_gauntlet.checks import RetryOutcome

    first_passes = _early(RetryOutcome(3, 4, tried_ms=[250], first_passing_ms=250))
    assert "somewhere between 0 and 250 ms" in first_passes.what_happened
    assert first_passes.detail["first_passing_delay_ms"] == 250

    all_fail = _early(
        RetryOutcome(3, 4, tried_ms=[250, 500, 1000, 2000, 3000], last_failing_ms=3000)
    )
    assert "more than 3000 ms" in all_fail.what_happened
    assert all_fail.detail["first_passing_delay_ms"] is None
    assert "about" not in all_fail.what_happened.split("works after waiting.")[1]

    limited = _early(
        RetryOutcome(3, 4, tried_ms=[250, 500], last_failing_ms=500, budget_limited=True)
    )
    assert "more than 500 ms" in limited.what_happened and limited.detail["budget_limited"]

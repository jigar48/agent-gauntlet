import pytest

from agent_gauntlet.journey import JourneyError, parse_journey


def base(steps):
    return {"name": "t", "base_url": "http://localhost:8000", "steps": steps}


def problems(steps):
    with pytest.raises(JourneyError) as exc:
        parse_journey(base(steps))
    return exc.value.problems


def test_valid_shorthand_and_explicit_forms():
    j = parse_journey(
        base(
            [
                {"goto": "/"},
                {"click": "#a"},
                {"type": "click", "selector": "#b", "tag": "add_to_cart"},
                {"fill": {"selector": "#email", "value": "a@example.com"}},
                {"expect_text": "Hello"},
                {"expect_visible": ".x"},
                {"screenshot": "one"},
                {"wait": 500},
            ]
        )
    )
    assert [s.type for s in j.steps] == [
        "goto",
        "click",
        "click",
        "fill",
        "expect_text",
        "expect_visible",
        "screenshot",
        "wait",
    ]


def test_missing_selector_is_readable():
    assert "step 3 > click: selector is required" in problems(
        [{"goto": "/"}, {"click": "#a"}, {"click": {"tag": "checkout"}}]
    )


def test_wait_range_enforced():
    assert any("wait" in p for p in problems([{"wait": 50}]))
    assert any("wait" in p for p in problems([{"wait": 20000}]))


def test_unknown_step_and_unknown_field():
    assert any("unknown step type" in p for p in problems([{"type": "hover", "selector": "#a"}]))
    assert any(
        "unknown field 'colour'" in p
        for p in problems([{"click": {"selector": "#a", "colour": 1}}])
    )


@pytest.mark.parametrize(
    "selector",
    ["#card-number", "input[name=cvv]", "#password", "[autocomplete=one-time-code]", "#otp-field"],
)
def test_fill_refuses_sensitive_fields(selector):
    out = problems([{"fill": {"selector": selector, "value": "x"}}])
    assert any("step 1 > fill" in p and "refused" in p for p in out)


@pytest.mark.parametrize(
    "selector",
    ["#place-order", "text=Pay now", ".btnBuyNow", "text=Complete purchase", "#placeOrder"],
)
def test_click_refuses_order_actions(selector):
    out = problems([{"click": selector}])
    assert any("step 1 > click" in p and "refused" in p for p in out)


def test_cart_and_card_lookalikes_are_not_refused():
    parse_journey(base([{"click": "#add-to-cart"}, {"fill": {"selector": "#email", "value": "a"}}]))


def test_goto_must_stay_on_host():
    assert any("must stay on" in p for p in problems([{"goto": "http://evil.example/x"}]))


def test_bad_base_url_and_empty_steps():
    with pytest.raises(JourneyError) as exc:
        parse_journey({"name": "t", "base_url": "ftp://x", "steps": []})
    assert any("base_url" in p for p in exc.value.problems)
    assert any("steps" in p for p in exc.value.problems)

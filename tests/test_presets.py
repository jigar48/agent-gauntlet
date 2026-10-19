import pytest
import yaml

from agent_gauntlet.cli import main
from agent_gauntlet.engine import execute
from agent_gauntlet.fixtures.shops import serve_shop
from agent_gauntlet.journey import parse_journey
from agent_gauntlet.presets import PRESET_NAMES, render_preset


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_every_preset_validates_and_is_labelled_experimental(name):
    text = render_preset(name)
    assert "EXPERIMENTAL, not verified against a live store" in text
    journey = parse_journey(yaml.safe_load(text))
    tags = [getattr(s, "tag", None) for s in journey.steps]
    assert "add_to_cart" in tags and "checkout" in tags
    assert not journey.permission_confirmed  # presets never pre-grant permission


def test_init_writes_file_and_refuses_overwrite(tmp_path, capsys):
    out = tmp_path / "j.yml"
    assert (
        main(["init", "--preset", "magento2", "--out", str(out), "--base-url", "https://s.test"])
        == 0
    )
    assert "base_url: https://s.test" in out.read_text()
    assert main(["init", "--out", str(out)]) == 2
    assert main(["init", "--out", str(out), "--force"]) == 0


def test_generic_preset_shape_runs_on_the_clean_fixture(tmp_path):
    with serve_shop("clean") as shop:
        raw = yaml.safe_load(render_preset("generic", shop.base_url))
        steps = raw["steps"]
        steps[0] = {"goto": "/product"}
        steps[1]["click"]["selector"] = "#add-to-cart"
        steps[2] = {"expect_text": "Added to cart"}
        steps[4] = {"goto": "/cart"}
        steps[5]["click"]["selector"] = "#checkout-link"
        result = execute(parse_journey(raw), out_dir=tmp_path, permission="local")
    assert [c.status for c in result.checks] == ["PASS"] * 4

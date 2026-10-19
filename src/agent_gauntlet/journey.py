"""Journey file format: load, validate and return readable errors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_gauntlet import safety

PRIMARY_FIELD = {
    "goto": "url",
    "click": "selector",
    "fill": None,
    "expect_text": "text",
    "expect_visible": "selector",
    "screenshot": "name",
    "wait": "ms",
}
MAX_ADD_TO_CART_STEPS = 3
REFUSED_FILL = "target looks like a payment, card, password or one-time-code field (refused)"
REFUSED_CLICK = "target looks like a final order or payment action (refused)"


class JourneyError(Exception):
    """A journey file problem. `problems` holds one readable line each."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


class _Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_ms: int = Field(default=5000, ge=100, le=60000)


class Goto(_Step):
    type: Literal["goto"] = "goto"
    url: str


class Click(_Step):
    type: Literal["click"] = "click"
    selector: str = Field(min_length=1)
    # Marks the step for rate limiting (add_to_cart) or login-wall detection (checkout).
    tag: Literal["add_to_cart", "checkout"] | None = None


class Fill(_Step):
    type: Literal["fill"] = "fill"
    selector: str = Field(min_length=1)
    value: str


class ExpectText(_Step):
    type: Literal["expect_text"] = "expect_text"
    text: str = Field(min_length=1)
    selector: str | None = None


class ExpectVisible(_Step):
    type: Literal["expect_visible"] = "expect_visible"
    selector: str = Field(min_length=1)


class Screenshot(_Step):
    type: Literal["screenshot"] = "screenshot"
    name: str = Field(default="shot", pattern=r"^[A-Za-z0-9_-]{1,40}$")


class Wait(_Step):
    type: Literal["wait"] = "wait"
    ms: int = Field(ge=100, le=10000)


AnyStep = Goto | Click | Fill | ExpectText | ExpectVisible | Screenshot | Wait

_MODELS: dict[str, type[_Step]] = {
    "goto": Goto,
    "click": Click,
    "fill": Fill,
    "expect_text": ExpectText,
    "expect_visible": ExpectVisible,
    "screenshot": Screenshot,
    "wait": Wait,
}


class Journey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    base_url: str
    permission_confirmed: bool = False
    login_markers: list[str] = Field(default_factory=list)
    challenge_markers: list[str] = Field(default_factory=list)
    steps: list[AnyStep]

    @property
    def checkout_step(self) -> int | None:
        """1-based index of the first step tagged `checkout`, if any."""
        for n, step in enumerate(self.steps, start=1):
            if isinstance(step, Click) and step.tag == "checkout":
                return n
        return None


def _field_problem(err: dict[str, Any]) -> str:
    loc = [str(p) for p in err["loc"] if p != "type"]
    field = loc[-1] if loc else "step"
    kind = err["type"]
    if kind == "missing":
        return f"{field} is required"
    if kind == "extra_forbidden":
        return f"unknown field '{field}'"
    if kind == "string_too_short":
        return f"{field} must not be empty"
    return f"{field}: {err['msg']}"


def _normalise_step(raw: Any) -> tuple[str | None, dict[str, Any] | str]:
    """Return (type, fields) or (None, problem message)."""
    if not isinstance(raw, dict) or not raw:
        return None, "must be a mapping such as 'click: \"#buy\"'"
    if "type" in raw:
        step_type = raw["type"]
        fields = {k: v for k, v in raw.items() if k != "type"}
    else:
        keys = [k for k in raw if k in _MODELS]
        if len(keys) != 1:
            return None, f"needs exactly one step type, one of: {', '.join(_MODELS)}"
        step_type = keys[0]
        body = raw[step_type]
        fields = {k: v for k, v in raw.items() if k != step_type}
        if isinstance(body, dict):
            fields.update(body)
        elif PRIMARY_FIELD[step_type] is not None:
            fields[PRIMARY_FIELD[step_type]] = body
        elif body is not None:
            return None, "must be a mapping with selector and value"
    if step_type not in _MODELS:
        return None, f"unknown step type '{step_type}' (use one of: {', '.join(_MODELS)})"
    return step_type, fields


def _guard_problems(n: int, step: _Step) -> list[str]:
    selector = getattr(step, "selector", None)
    out: list[str] = []
    if isinstance(step, Fill) and safety.looks_sensitive_field(selector):
        out.append(f"step {n} > fill: {REFUSED_FILL}")
    if isinstance(step, Click):
        hints = [selector]
        if selector and selector.lower().startswith("text="):
            hints.append(selector[5:])
        if safety.looks_like_order_action(*hints):
            out.append(f"step {n} > click: {REFUSED_CLICK}")
    return out


def parse_journey(data: Any) -> Journey:
    if not isinstance(data, dict):
        raise JourneyError(["journey file must be a YAML mapping with name, base_url and steps"])
    problems: list[str] = []
    raw_steps = data.get("steps")
    header = {k: v for k, v in data.items() if k != "steps"}
    steps: list[_Step] = []
    if not isinstance(raw_steps, list) or not raw_steps:
        problems.append("journey > steps must be a non-empty list")
        raw_steps = []
    for n, raw in enumerate(raw_steps, start=1):
        step_type, fields = _normalise_step(raw)
        if step_type is None:
            problems.append(f"step {n}: {fields}")
            continue
        assert isinstance(fields, dict)
        try:
            step = _MODELS[step_type].model_validate(fields)
        except ValidationError as exc:
            problems.extend(f"step {n} > {step_type}: {_field_problem(e)}" for e in exc.errors())
            continue
        steps.append(step)
        problems.extend(_guard_problems(n, step))
    try:
        head = Journey.model_validate({**header, "steps": []})
    except ValidationError as exc:
        problems.extend(f"journey > {_field_problem(e)}" for e in exc.errors())
        head = None
    if head is not None:
        parsed = urlparse(head.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            problems.append("journey > base_url must be an http:// or https:// URL")
        else:
            host = parsed.hostname.lower()
            for n, step in enumerate(steps, start=1):
                if isinstance(step, Goto) and urlparse(step.url).hostname not in (None, host):
                    problems.append(f"step {n} > goto: url must stay on {host}")
    carts = sum(1 for s in steps if isinstance(s, Click) and s.tag == "add_to_cart")
    if carts > MAX_ADD_TO_CART_STEPS:
        problems.append(
            f"journey > at most {MAX_ADD_TO_CART_STEPS} steps may be tagged add_to_cart "
            "(a run is capped at 6 add-to-cart attempts: two paces plus early-action retries)"
        )
    if problems or head is None:
        raise JourneyError(problems)
    return head.model_copy(update={"steps": steps})


def load_journey(path: str | Path) -> Journey:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise JourneyError([f"cannot read {path}: {exc.strerror or exc}"]) from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise JourneyError([f"invalid YAML: {exc}"]) from exc
    return parse_journey(data)

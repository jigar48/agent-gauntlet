"""Executes a journey in a fresh browser context at a given pace."""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Browser, Page, Playwright, expect, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from agent_gauntlet import safety
from agent_gauntlet.journey import (
    AnyStep,
    Click,
    ExpectText,
    ExpectVisible,
    Fill,
    Goto,
    Journey,
    Screenshot,
    Wait,
)
from agent_gauntlet.result import ErrorKind, NetworkNote, Pace, PaceResult, StepResult

SETTLE_MS = 1500
MAX_ADD_TO_CART_ATTEMPTS = 6
VIEWPORT = {"width": 1280, "height": 800}
COVER_GRACE_MS = 300  # how long a covering element may take to clear before we call it covered

CHALLENGE_STATUSES = frozenset({403, 429, 503})
CHALLENGE_MARKERS = (
    "just a moment",
    "performing security verification",
    "checking your browser before accessing",
    "attention required! | cloudflare",
    "verify you are human",
)
LOGIN_URL_PATTERN = re.compile(
    r"/(log-?in|sign-?in|sign_in|signin|auth|authenticate|sso|oauth|account/login|"
    r"customer/account/login|wp-login\.php|my-account)(/|$)",
    re.IGNORECASE,
)

_COVER_JS = """el => {
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) return {state: 'unknown'};
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return {state: 'unknown'};
  const root = el.getRootNode();
  let hit = (root && root.elementFromPoint ? root : document).elementFromPoint(x, y);
  while (hit && hit.shadowRoot) {
    const inner = hit.shadowRoot.elementFromPoint(x, y);
    if (!inner || inner === hit) break;
    hit = inner;
  }
  if (!hit) return {state: 'unknown'};
  if (el === hit || el.contains(hit)) return {state: 'clear'};
  const label = hit.closest && hit.closest('label');
  if (label && label.control === el) return {state: 'clear'};
  const text = (hit.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 80);
  return {state: 'covered', blocker: {
    tag: hit.tagName.toLowerCase(), id: hit.id || '',
    cls: (typeof hit.className === 'string' ? hit.className : '').trim().slice(0, 80), text}};
}"""

_PROBE_JS = """() => {
  const visible = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const pw = [...document.querySelectorAll('input[type=password]')].filter(visible).length;
  const otp = [...document.querySelectorAll('input[autocomplete=one-time-code]')]
    .filter(visible).length;
  return {title: document.title || '', passwordFields: pw, otpFields: otp,
    text: ((document.body && document.body.innerText) || '').slice(0, 4000).toLowerCase()};
}"""


class StepFailure(Exception):
    def __init__(self, kind: ErrorKind, message: str, detail: dict | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail or {}


class AttemptBudget:
    """Caps add-to-cart-type attempts across the whole run (both paces and retries)."""

    def __init__(self, limit: int = MAX_ADD_TO_CART_ATTEMPTS):
        self.limit = limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def take(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


class BrowserSession:
    """One Chromium process; every pace gets a fresh context."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw: Playwright | None = None
        self.browser: Browser | None = None

    def __enter__(self) -> BrowserSession:
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=self.headless)
        return self

    def __exit__(self, *exc: object) -> None:
        if self.browser:
            self.browser.close()
        if self._pw:
            self._pw.stop()


def step_label(step: AnyStep) -> str:
    if isinstance(step, Goto):
        return f"go to {step.url}"
    if isinstance(step, Click):
        return f"click {step.selector}"
    if isinstance(step, Fill):
        return f"fill {step.selector}"
    if isinstance(step, ExpectText):
        return f"expect text {step.text!r}"
    if isinstance(step, ExpectVisible):
        return f"expect {step.selector} visible"
    if isinstance(step, Screenshot):
        return f"screenshot {step.name}"
    return f"wait {step.ms} ms"


def describe_blocker(blocker: dict) -> str:
    out = f"<{blocker['tag']}"
    if blocker.get("id"):
        out += f' id="{blocker["id"]}"'
    if blocker.get("cls"):
        out += f' class="{blocker["cls"]}"'
    out += ">"
    if blocker.get("text"):
        out += f' "{blocker["text"]}"'
    return out


def _element_hints(loc) -> dict:
    return loc.evaluate(
        """el => ({
            tag: el.tagName.toLowerCase(),
            type: el.getAttribute('type') || '',
            name: el.getAttribute('name') || '',
            id: el.id || '',
            autocomplete: el.getAttribute('autocomplete') || '',
            placeholder: el.getAttribute('placeholder') || '',
            ariaLabel: el.getAttribute('aria-label') || '',
            text: (el.innerText || el.value || '').trim().slice(0, 120),
        })"""
    )


def _first_line(exc: Exception) -> str:
    return (str(exc).strip().splitlines() or [type(exc).__name__])[0][:300]


class _Runner:
    def __init__(
        self,
        page: Page,
        journey: Journey,
        pace: Pace,
        out_dir: Path,
        budget: AttemptBudget,
        tag: str,
    ):
        self.page = page
        self.journey = journey
        self.pace = pace
        self.out_dir = out_dir
        self.budget = budget
        self.tag = tag
        self.network: list[NetworkNote] = []
        page.on("response", self._on_response)

    def _on_response(self, resp) -> None:
        try:
            if resp.request.is_navigation_request() and resp.frame == self.page.main_frame:
                self.network.append(
                    NetworkNote(
                        url=resp.url,
                        status=resp.status,
                        cf_mitigated=resp.headers.get("cf-mitigated"),
                    )
                )
        except PlaywrightError:
            pass

    def shot(self, name: str) -> str:
        shots = self.out_dir / "screenshots"
        shots.mkdir(parents=True, exist_ok=True)
        path = shots / f"{self.tag}{name}.png"
        self.page.screenshot(path=str(path))
        return f"screenshots/{path.name}"

    def settle(self) -> None:
        if self.pace == "human":
            self.page.wait_for_timeout(SETTLE_MS)

    # -- observations ------------------------------------------------------------------
    def detect_challenge(self) -> dict | None:
        """Bot-challenge signals: document status 403/429/503, cf-mitigated header, or markers.

        This only observes. It never retries or tries to get past a challenge."""
        for note in self.network:
            if note.status in CHALLENGE_STATUSES:
                return {"signal": f"HTTP {note.status}", "url": note.url, "status": note.status}
            if note.cf_mitigated:
                return {
                    "signal": f"cf-mitigated: {note.cf_mitigated}",
                    "url": note.url,
                    "status": note.status,
                }
        try:
            text = self.page.evaluate(
                "() => (document.title + ' ' + ((document.body && document.body.innerText) || ''))"
                ".slice(0, 4000).toLowerCase()"
            )
        except PlaywrightError:
            return None
        markers = CHALLENGE_MARKERS + tuple(m.lower() for m in self.journey.challenge_markers)
        for marker in markers:
            if marker in text:
                return {"signal": f"page text: {marker!r}", "url": self.page.url, "status": None}
        return None

    def probe_login_wall(self) -> dict:
        """Observe whether the page looks like a login / one-time-code wall."""
        try:
            self.page.wait_for_load_state("load", timeout=3000)
        except PlaywrightTimeout:
            pass
        info = self.page.evaluate(_PROBE_JS)
        path = urlparse(self.page.url).path
        reasons: list[str] = []
        if LOGIN_URL_PATTERN.search(path):
            reasons.append(f"URL path looks like a login page ({path})")
        if info["passwordFields"]:
            reasons.append("a password field is visible")
        if info["otpFields"]:
            reasons.append("a one-time-code field is visible")
        for marker in self.journey.login_markers:
            if marker.lower() in info["text"]:
                reasons.append(f"page contains your marker {marker!r}")
        return {"wall": bool(reasons), "reasons": reasons, "url": self.page.url}

    # -- steps -------------------------------------------------------------------------
    def run_step(self, n: int, step: AnyStep) -> str | None:
        """Execute one step. Returns a screenshot path for screenshot steps."""
        page = self.page
        timeout = step.timeout_ms
        if isinstance(step, Goto):
            url = urljoin(self.journey.base_url, step.url)
            if safety.hostname_of(url) != safety.hostname_of(self.journey.base_url):
                raise StepFailure("safety", "goto target is outside the base_url host")
            try:
                page.goto(url, timeout=max(timeout, 15000))
            except PlaywrightTimeout as exc:
                raise StepFailure("timeout", f"page did not load: {_first_line(exc)}") from exc
            except PlaywrightError as exc:
                raise StepFailure("navigation", _first_line(exc)) from exc
            self.settle()
        elif isinstance(step, Click):
            self._click(step)
        elif isinstance(step, Fill):
            loc = page.locator(step.selector).first
            try:
                loc.wait_for(state="attached", timeout=timeout)
                hints = _element_hints(loc)
                if safety.looks_sensitive_field(
                    hints["type"],
                    hints["name"],
                    hints["id"],
                    hints["autocomplete"],
                    hints["placeholder"],
                    hints["ariaLabel"],
                ):
                    raise StepFailure(
                        "safety",
                        "refused: the field looks like a payment, card, password or "
                        "one-time-code field",
                    )
                loc.fill(step.value, timeout=timeout)
            except PlaywrightTimeout as exc:
                raise StepFailure("timeout", _first_line(exc)) from exc
        elif isinstance(step, ExpectText):
            scope = page.locator(step.selector).first if step.selector else page.locator("body")
            try:
                expect(scope).to_contain_text(step.text, timeout=timeout)
            except AssertionError as exc:
                raise StepFailure("assertion", f"text {step.text!r} not found") from exc
        elif isinstance(step, ExpectVisible):
            try:
                expect(page.locator(step.selector).first).to_be_visible(timeout=timeout)
            except AssertionError as exc:
                raise StepFailure("assertion", f"{step.selector} is not visible") from exc
        elif isinstance(step, Screenshot):
            return self.shot(f"{n:02d}-{step.name}")
        return None

    def _covered(self, loc) -> dict | None:
        """Return blocker info if another element sits on top of the target's centre."""
        deadline = time.monotonic() + COVER_GRACE_MS / 1000
        while True:
            state = loc.evaluate(_COVER_JS)
            if state["state"] != "covered":
                return None
            if time.monotonic() >= deadline:
                return state["blocker"]
            self.page.wait_for_timeout(100)

    def _click(self, step: Click) -> None:
        page = self.page
        loc = page.locator(step.selector).first
        timeout = step.timeout_ms
        try:
            loc.wait_for(state="visible", timeout=timeout)
            loc.scroll_into_view_if_needed(timeout=timeout)
            hints = _element_hints(loc)
        except PlaywrightTimeout as exc:
            raise StepFailure("timeout", f"{step.selector} did not become visible") from exc
        if safety.looks_like_order_action(
            hints["text"], hints["ariaLabel"], hints["id"], hints["name"]
        ):
            raise StepFailure(
                "safety", "refused: the target looks like a final order or payment action"
            )
        blocker = self._covered(loc)
        if blocker:
            raise StepFailure(
                "covered",
                f"{step.selector} is covered by {describe_blocker(blocker)}",
                {"blocker": blocker, "target": step.selector},
            )
        if step.tag == "add_to_cart" and not self.budget.take():
            raise StepFailure(
                "rate_limit",
                f"add-to-cart attempt limit ({self.budget.limit} per run) reached",
            )
        before = page.url
        try:
            loc.click(timeout=timeout)
        except PlaywrightTimeout as exc:
            if "intercepts pointer events" in str(exc):
                raise StepFailure(
                    "intercepted",
                    "another element intercepts the click",
                    {"playwright": _first_line(exc)},
                ) from exc
            raise StepFailure("timeout", f"{step.selector} was not clickable in time") from exc
        except PlaywrightError as exc:
            raise StepFailure("error", _first_line(exc)) from exc
        if page.url != before:
            try:
                page.wait_for_load_state("load", timeout=15000)
            except PlaywrightTimeout:
                pass
            self.settle()


def run_pace(
    session: BrowserSession,
    journey: Journey,
    pace: Pace,
    *,
    out_dir: Path,
    budget: AttemptBudget,
    user_agent: str,
    tag: str = "",
    stop_after: int | None = None,
    delay_before: tuple[int, int] | None = None,
) -> PaceResult:
    """Run the journey once. `delay_before=(step, ms)` sleeps before that step and
    `stop_after=n` ends the run after step n; both are used by the early-action retries."""
    assert session.browser is not None
    context = session.browser.new_context(user_agent=user_agent, viewport=VIEWPORT)
    page = context.new_page()
    runner = _Runner(page, journey, pace, out_dir, budget, f"{tag}{pace}-")
    checkout_at = journey.checkout_step
    results: list[StepResult] = []
    failed_at: int | None = None
    challenge: dict | None = None
    started = time.monotonic()
    try:
        for n, step in enumerate(journey.steps, start=1):
            label = step_label(step)
            if failed_at is not None or (stop_after is not None and n > stop_after):
                results.append(StepResult(index=n, type=step.type, label=label, status="not_run"))
                continue
            if isinstance(step, Wait) and pace == "machine":
                results.append(StepResult(index=n, type="wait", label=label, status="skipped"))
                continue
            if delay_before and delay_before[0] == n:
                page.wait_for_timeout(delay_before[1])
            runner.network.clear()
            t0 = time.monotonic()
            res = StepResult(index=n, type=step.type, label=label, status="ok")
            try:
                if isinstance(step, Wait):
                    page.wait_for_timeout(step.ms)
                else:
                    res.screenshot = runner.run_step(n, step)
            except StepFailure as fail:
                res.status = "failed"
                res.error_kind = fail.kind
                res.error = fail.message
                res.detail = fail.detail
            if not isinstance(step, Wait | Screenshot):
                found = runner.detect_challenge()
                if found:
                    challenge = found
                    res.status = "failed"
                    res.error_kind = "challenge"
                    res.error = f"bot challenge detected ({found['signal']})"
                    res.detail = {"challenge": found}
            if checkout_at is not None and n >= checkout_at and not isinstance(step, Wait):
                if (n == checkout_at or res.status == "failed") and challenge is None:
                    try:
                        res.detail = {**res.detail, "login_probe": runner.probe_login_wall()}
                    except PlaywrightError:
                        pass
            if res.status == "failed":
                failed_at = n
                if res.screenshot is None:
                    try:
                        res.screenshot = runner.shot(f"{n:02d}-failed")
                    except PlaywrightError:
                        pass
            res.duration_ms = int((time.monotonic() - t0) * 1000)
            res.url = page.url
            res.network = list(runner.network)
            results.append(res)
            if challenge is not None:
                # Never retry or work around a challenge: stop right here.
                for later_n, later in enumerate(journey.steps[n:], start=n + 1):
                    results.append(
                        StepResult(
                            index=later_n,
                            type=later.type,
                            label=step_label(later),
                            status="not_run",
                        )
                    )
                break
    finally:
        context.close()
    return PaceResult(
        pace=pace,
        status="failed" if failed_at is not None else "ok",
        failed_step=failed_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        steps=results,
        extra_delay=delay_before,
        challenge=challenge,
    )

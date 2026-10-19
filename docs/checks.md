# The four checks

Each check ends in one of `PASS`, `WARN`, `FAIL` or `NOT_TESTED`. The scorecard says
"N of 4 checks passed" (only `PASS` counts) and gives a plain-English verdict per check.

Every run executes the journey twice in fresh browser contexts:

- **human pace**: as written, `wait` steps honoured, 1500 ms settle after navigations.
- **machine pace**: `wait` steps removed, no settle. Steps run as soon as Playwright considers
  the element actionable (visible, stable, enabled, receiving events; see the
  [Playwright actionability docs](https://playwright.dev/python/docs/actionability)).

## 1. early-action ("Works without waiting")

**Detects.** Human pace passes, machine pace fails at step N.

- Result `FAIL`: "works only after waiting". The tool then retries the machine-pace run in fresh
  contexts, inserting a fixed delay before the acting step (the last `click`/`fill` at or before
  the failing step): 250, 500, 1000, 2000, 3000 ms, smallest first, stopping at the first success.
  The result is a **range**, never a single number: "somewhere between <last failing delay> and
  <first passing delay> ms" (the instant run counts as a failing delay of 0 ms). If every retry
  fails it says "more than 3000 ms" (the largest delay tried), or the largest delay it got to if
  the add-to-cart limit stopped it early. `result.json` holds `last_failing_delay_ms`,
  `first_passing_delay_ms` (null if none passed), `tried_ms` and `budget_limited` in the check's
  `detail`.
- Both paces pass: `PASS`.
- Machine passes but human fails (for example a pop-up that only appears later): `PASS`, with the
  paced failure noted.
- Both fail for a reason another check explains (covered target, login wall): `PASS` or `WARN`,
  with a note. Both fail for any other reason: the journey itself is broken. This is reported as
  a journey error and the exit code is 2.
- Run stopped by a bot challenge: `NOT_TESTED`.

**Limits.**

- The range is only as narrow as the retry grid (250, 500, 1000, 2000, 3000 ms) and stops at 3000 ms.
- Every retry that includes an `add_to_cart` step uses part of the 6-attempt budget, so the
  range can be cut short ("limited by the add-to-cart attempt limit").
- The failing step is blamed on the nearest earlier click or fill. A slow server response is not
  distinguishable from a slow script.
- One run per pace: a race that only sometimes loses can pass.

## 2. overlay ("Nothing covers the buttons")

**Detects.** Before every click, once the target is visible, the tool asks the browser which
element is on top at the target's centre (`elementFromPoint`, including open shadow roots). If it
is not the target or one of its descendants, the click is reported as covered, with the blocker's
tag, id, class and short text, plus a screenshot. Playwright's own "intercepts pointer events"
errors are mapped to the same result. A blocker gets 300 ms to clear before it is reported.

**Limits.**

- Only the click's centre point is tested; a target partly covered elsewhere passes.
- Content inside iframes and closed shadow roots is not inspected.
- A pop-up that appears after your click is not seen.
- A pop-up that Playwright could click through (`pointer-events: none`) is correctly ignored.

## 3. login-wall ("No login wall at checkout")

**Detects.** After the step tagged `tag: checkout` (or at a later failing step), the page is
inspected for: a login-like URL path (`/login`, `/signin`, `/auth`, `/customer/account/login`,
`/wp-login.php`, `/my-account`, ...), a visible password field, a visible one-time-code field, or
any text you list in `login_markers` in the journey file. Found: `WARN`, never `FAIL`, because an
agent cannot continue without credentials but the store may be doing this on purpose.

**Limits.**

- A checkout page that shows an optional "log in" form for returning customers contains a
  visible password field and will produce a false `WARN`. Check the screenshot.
- Without a `tag: checkout` step the check is `NOT_TESTED`.
- Walls that appear later in the flow (for example at payment) are out of scope: the tool stops
  before payment.

## 4. bot-challenge ("No bot challenge")

**Detects.** On every page navigation: HTTP status 403, 429 or 503; a `cf-mitigated` response
header; or known challenge text ("Just a moment", "Performing security verification", "Checking
your browser before accessing", "Attention Required! | Cloudflare", "Verify you are human", plus
your `challenge_markers`). Found: `FAIL`, the run **stops immediately**, nothing is retried and
nothing is done to get past it. Checks that could not be completed become `NOT_TESTED`.

**Limits.**

- Only top-level page navigations are examined, not background requests.
- A 503 from an ordinary outage or maintenance page is reported as a challenge.
- Challenges that only trigger on repeated or higher-volume traffic will not appear in a short
  two-pace run.
- A pass says nothing about other IP addresses or user agents.

## Exit codes

`0` no `FAIL`; `1` at least one `FAIL`; `2` usage, config or journey error (including a refused
permission gate and a journey that fails at both paces without another check explaining it).

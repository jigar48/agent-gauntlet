# agent-gauntlet

A free, open-source, **deterministic** command-line tool (no LLM, no API cost) that walks a
store's checkout journey the way an AI shopping agent does: instantly, with no human-like pauses.
It tells you in plain English where that breaks, with screenshots as evidence.

It **stops before payment and never places an order.**

```text
agent-gauntlet scorecard: Fixture shop: slow-scripts
3 of 4 checks passed (1 failed)

[FAIL] Works without waiting
    Step 4 (expect text 'Added to cart') failed after step 3 (click) acted too early when run
    instantly, but works after waiting. The page needed somewhere between 1000 and 2000 ms ...
[PASS] Nothing covers the buttons
[PASS] No login wall at checkout
[PASS] No bot challenge
```

> **Status: v0.1.0, early.** Everything described here works today against the built-in fixture
> shops. It has **not** been verified against any live store.

## What it is not

- **Not a certification.** There is no score to display or badge to earn.
- It **does not simulate any specific AI product** (ChatGPT, Gemini, browser agents). It runs a
  scripted browser journey two ways and compares them.
- **A pass is not a guarantee.** Results depend on the site, your IP address and bot protection.
- **Only test sites you own or have written permission to test.** Never place orders.

## Why it exists

Shopping agents are starting to buy from stores. Existing "AI-readiness" scanners read static
signals (`llms.txt`, structured data, `robots.txt`) but do not test real tasks. LLM-driven
checkout testers exist, but a model-driven run is non-deterministic and costs money per run.
Practitioner guidance says agents tend to fail on timing and hydration races (acting before page
scripts attach handlers), overlays that intercept clicks, login walls and bot challenges.

agent-gauntlet audits those four patterns deterministically, with no model in the loop. I have not
proven that no other tool does this, so this README does not claim to be the first.

The origin: on a live Magento store, clicking "Add to cart" within about 2 seconds of page load
returned "Invalid Form Key", because page scripts were still setting up the form key. A person
never notices that. A fast agent does.

## Quickstart

Requires Python 3.12 or newer. Chromium (about 150 MB) is downloaded by Playwright.

```bash
git clone https://github.com/jigar48/agent-gauntlet
cd agent-gauntlet
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium        # on Linux CI use: playwright install --with-deps chromium
```

See it work on the built-in fake shops (everything stays on localhost):

```bash
agent-gauntlet demo
```

Open `gauntlet-demo/index.html` in a browser to see five sample reports.

Audit your own store (one you own or have written permission to test):

```bash
agent-gauntlet init --preset generic --base-url https://your-store.example
# edit journey.yml: product URL, selectors, expected text
agent-gauntlet run journey.yml --i-have-permission
```

Output goes to `gauntlet-out/`: `result.json`, `report.html` (self-contained, mobile friendly,
dark-mode aware) and `screenshots/`. Re-render a report any time:

```bash
agent-gauntlet report gauntlet-out/result.json
```

### Commands

| Command | What it does |
| --- | --- |
| `agent-gauntlet run <journey.yml>` | Run the journey at two paces, apply the four checks, write results. |
| `agent-gauntlet init --preset generic\|magento2\|woocommerce` | Write a starter journey file. |
| `agent-gauntlet report <result.json>` | Print the scorecard and write `report.html`. |
| `agent-gauntlet demo` | Start the built-in fixture shops on localhost and audit every variant. |
| `agent-gauntlet --version` | Print the version. |

Exit codes: `0` no FAIL, `1` at least one FAIL, `2` usage, config or journey error.

## How it works

The journey runs twice, each in a fresh browser context:

- **human pace:** as written, honouring `wait` steps, with a 1500 ms settle after navigations.
- **machine pace:** `wait` steps removed, no settle, acting as soon as Playwright considers the
  element actionable.

Then four checks (details and limits in [docs/checks.md](docs/checks.md)):

1. **early-action:** works at human pace but fails at machine pace? Reports a delay range (between the last failing and first passing delay of a few fixed retries).
2. **overlay:** is the click target covered by another element (modal, banner)?
3. **login-wall:** does checkout land on a login or one-time-code wall? (WARN, not FAIL.)
4. **bot-challenge:** 403/429/503 or known challenge markers? FAIL, stop, never retry or evade.

The scorecard reads "N of 4 checks passed" with a one-line verdict per check. There is no numeric score.

### Journey file

```yaml
name: My store checkout
base_url: https://your-store.example
steps:
  - goto: /products/example
  - click: { selector: "#add-to-cart", tag: add_to_cart }
  - expect_text: "Added to cart"
  - goto: /cart
  - click: { selector: "a.checkout", tag: checkout }
  - screenshot: checkout
```

Step types: `goto`, `click`, `fill`, `expect_text`, `expect_visible`, `screenshot`,
`wait` (100 to 10000 ms). Mark the add-to-cart click `tag: add_to_cart` and the checkout click
`tag: checkout`; the rate limit and login-wall check use those tags.

## Safety

Short version (full detail in [docs/safety.md](docs/safety.md)):

- Any host other than `localhost` / `127.0.0.1` needs `--i-have-permission` (or
  `permission_confirmed: true` in the journey). Without it: exit code 2.
- It refuses to `fill` fields that look like payment, card, password or one-time-code fields, and
  to click targets that look like "place order", "pay now", "complete purchase" or "buy now".
  **This is best-effort defense in depth, not a guarantee.**
- At most 6 add-to-cart attempts per run. **Each live run can leave abandoned carts** in the store.
- It never logs in, creates accounts, or tries to solve or evade a CAPTCHA, bot challenge or WAF.
  If it meets a challenge it reports it and stops.
- Default User-Agent: `agent-gauntlet/<version> (+https://github.com/jigar48/agent-gauntlet)`.
  Override with the `AGENT_GAUNTLET_USER_AGENT` environment variable.

## Limits

- Tested only on its own fixture shops. Presets (`generic`, `magento2`, `woocommerce`) are
  **experimental, not verified against a live store**.
- Local Chromium only; one viewport; no login; no payment step; no JavaScript-rendering check.
- A fast single run cannot see behaviour that depends on your IP, traffic level or bot rules.

## GitHub Action

`action.yml` is a composite action; see [examples/github-workflow.yml](examples/github-workflow.yml).
It can only be used from GitHub after it has been merged to the default branch.

## Honest comparison

| | Static AI-readiness scanners | LLM-driven checkout testers | agent-gauntlet |
| --- | --- | --- | --- |
| Looks at | `llms.txt`, structured data, `robots.txt` | A real checkout, driven by a model | A real checkout, driven by a script |
| Deterministic | Yes | No | Yes |
| Cost per run | Usually none | Model usage | None |
| Finds timing races, overlays, login walls | No | Sometimes, by chance | Yes, on purpose |
| Judges content, wording, product fit | Partly | Yes | No |

These are categories, not reviews of specific products; use whichever combination suits you.

## Development

```bash
pip install -e ".[dev]"
playwright install chromium
ruff check . && ruff format --check . && pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Docs: [checks](docs/checks.md),
[fixing guide](docs/fixing-guide.md), [safety](docs/safety.md), [changelog](CHANGELOG.md).

## License

MIT, copyright 2026 Jigar Prajapati.

## About the author

Built by **Jigar Prajapati**, freelance software developer and automation engineer in Ahmedabad,
India (Python, Playwright, FastAPI, AWS, e-commerce platforms, AI agents).

- GitHub: [github.com/jigar48](https://github.com/jigar48)
- Portfolio: [jigar48.github.io/automatewithjigar](https://jigar48.github.io/automatewithjigar/)
- LinkedIn: [Jigar Prajapati](https://www.linkedin.com/in/buildaiwith-jigar-prajapati/)

## Support my work

If agent-gauntlet saves you time, you can buy me a coffee.

<a href="https://buymeacoffee.com/buildwithjigar"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy me a coffee" height="41"></a>

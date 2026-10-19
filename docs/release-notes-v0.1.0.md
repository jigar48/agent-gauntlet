# agent-gauntlet v0.1.0

First release of a free, open-source, deterministic (no LLM, no API cost) tool that walks a
store's checkout journey the way an AI shopping agent does, reports in plain English where it
breaks, and stops before payment.

## What's in it

- `agent-gauntlet run`: one journey, two paces (human and machine), fresh browser contexts.
- Four checks: **early-action** (with an estimated minimum working delay), **overlay**,
  **login-wall**, **bot-challenge**. Scorecard reads "N of 4 checks passed".
- `result.json`, screenshots and a self-contained `report.html` (mobile friendly, dark-mode aware).
- `agent-gauntlet demo`: five fake fixture shops on localhost, one finding each.
- `agent-gauntlet init`: experimental presets for generic, Magento 2 and WooCommerce.
- A composite GitHub Action and an example workflow.

## Safety

Permission flag required for non-local hosts, payment/order guards (best effort), at most 6
add-to-cart attempts per run, never logs in, never evades a bot challenge. See `docs/safety.md`.

## Known limitations

- Tested only against its own fixture shops. **Not verified against any live store.**
- Presets are experimental.
- This is not a certification, and a pass is not a guarantee.
- The GitHub Action could not be run on GitHub before this release; it is validated with
  actionlint and unit-tested for structure only.

## Install

```bash
pip install -e ".[dev]"
playwright install chromium
agent-gauntlet demo
```

No package is published to PyPI.

Full list of changes: `CHANGELOG.md`.

# Contributing

Thanks for helping. Please open an issue first for anything beyond a small fix, so we agree on
scope. This project is deliberately small: deterministic, no LLM, stops before payment.

## Ground rules

- **Never run tests or examples against a real site.** Everything in `tests/` uses the local
  fixture shops in `src/agent_gauntlet/fixtures/`. Do not add tests that need the internet.
- Do not add anything that logs in, creates accounts, places orders, or tries to get past a
  CAPTCHA, bot challenge or WAF.
- No secrets, tokens or private store URLs in code, tests, issues or logs.
- Do not claim a preset works on a real store unless you have verified it and say how.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium
```

## Before you open a pull request

```bash
ruff check .
ruff format --check .
pytest -q
actionlint .github/workflows/*.yml examples/github-workflow.yml tests/actionlint/local-action.yml
```

A change to a check needs a fixture-based test that shows it failing on the matching fixture
shop and passing on the clean one. Update `docs/checks.md` and `CHANGELOG.md`.

## New presets

Presets are starter files, tested only for validity. Include links to the platform's public
template source or documentation for every selector.

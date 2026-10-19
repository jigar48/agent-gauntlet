# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-10-19

First version. Tested only against the built-in fixture shops, not against any live store.

### Added
- `agent-gauntlet run`: runs a YAML journey at human pace and machine pace in fresh browser contexts.
- Journey validation with readable errors; step types `goto`, `click`, `fill`, `expect_text`,
  `expect_visible`, `screenshot`, `wait`.
- Permission gate for non-local hosts, payment and order-action guards, 6 add-to-cart attempt cap,
  configurable User-Agent.
- Four checks: early-action (reports a delay range from the retry grid), overlay, login-wall, bot-challenge.
- Scorecard ("N of 4 checks passed"), `result.json`, self-contained `report.html`, `report` command.
- `demo` command and five fixture shops (clean, slow-scripts, overlay, login-wall, bot-challenge).
- `init` command with experimental `generic`, `magento2` and `woocommerce` presets.
- Composite GitHub Action, example workflow, GitHub Pages demo workflow, CI with actionlint.

# Safety

agent-gauntlet drives a real browser at a real store. These rules limit what it does. Read them
before pointing it at anything other than the built-in fixture shops.

## Permission

Only test sites you own or have written permission to test.

- `localhost`, `127.0.0.1` and `::1` run without a flag.
- Any other host requires `--i-have-permission` on the command line, or
  `permission_confirmed: true` in the journey file. Without one, it exits with code 2 and
  runs nothing.
- Passing the flag is your statement that you have permission. The tool cannot check it.

## What it never does

- Place an order or submit payment details.
- Log in, create accounts, or enter passwords or one-time codes.
- Solve, bypass or evade a CAPTCHA, bot challenge or WAF. If it sees one it reports it and
  stops; nothing is retried.
- Send data anywhere other than the site under test. There is no telemetry.

## Guards (best effort, not a guarantee)

- A `fill` step is refused if its selector, or the element's `type`, `name`, `id`,
  `autocomplete`, placeholder or label, looks like a payment, card, password or one-time-code
  field.
- A `click` step is refused if its selector, or the element's visible text, id, name or label,
  looks like "place order", "pay now", "complete purchase", "buy now" or similar.
- `goto` may not leave the `base_url` host.

These are keyword checks. A pay button called "Finish" will not be caught. Keep your journey
ending at the cart or checkout page and never add a step that submits an order.

## Side effects on a live store

- Each run adds the product to a cart in a fresh browser session, once per pace, plus up to a
  few early-action retries. **Add-to-cart attempts are capped at 6 per run**, and at most three
  steps may be tagged `add_to_cart`.
- **A live run can leave abandoned carts**, reserved stock, analytics events and server log
  entries. Use a test product, and tell whoever watches the store.
- Default User-Agent: `agent-gauntlet/<version> (+https://github.com/jigar48/agent-gauntlet)`,
  so your logs can identify the traffic. Override with `AGENT_GAUNTLET_USER_AGENT`.

## Development rule

The project's own tests and CI never contact a real site; they use local fixture shops only.

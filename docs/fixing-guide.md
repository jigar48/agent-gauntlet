# Fixing guide for store owners

Plain-English next steps for each finding. This guide only states things that were checked against
the sources linked next to them. Anything else is labelled as a suggestion to try. Your theme,
plugins and hosting will differ, so test changes on a staging copy first.

## "Works without waiting" (early-action)

What it means: a click works for a person (who waits) but fails when done the moment the page
is ready, because page scripts are not finished yet.

- **Keep the button disabled until the page is ready.** Playwright, the browser library used by
  this tool, waits for a button to be *enabled* before clicking it
  ([actionability](https://playwright.dev/python/docs/actionability)), so a button that is only
  enabled once its scripts are ready cannot be clicked too early by a tool that waits for it.
  The default Magento 2 add-to-cart template renders its button with the `disabled` attribute
  ([template source](https://github.com/magento/magento2/blob/2.4-develop/app/code/Magento/Catalog/view/frontend/templates/product/view/addtocart.phtml)).
  If your theme or a customisation removes that, the button may be clickable before scripts attach.
  (That this is why a specific store failed is an inference; check your own page.)
- **Suggestion to try:** in your browser's developer tools, throttle the network and CPU, reload,
  and click the button immediately. Anything that fails there fails for fast agents too.
- **Suggestion to try:** errors such as "Invalid Form Key" right after load usually mean a token
  was not yet set when the form was sent. Look at what populates that field and when.

## "Nothing covers the buttons" (overlay)

What it means: another element (cookie banner, newsletter pop-up, chat widget) sits on top of
the button, so the click lands on it. Playwright treats a covered element as not receiving events
([actionability](https://playwright.dev/python/docs/actionability)).

- Look at the blocker named in the report (tag, id, class) and the screenshot.
- **Suggestion to try:** show pop-ups only after the shopper has had a chance to add to cart, or
  make sure they never cover the add-to-cart and checkout buttons.

## "No login wall at checkout" (login-wall)

What it means: checkout redirected to a sign-in or one-time-code page. An agent shopping for
someone has no account credentials.

- **Adobe Commerce / Magento 2:** the setting is *Allow Guest Checkout* under
  Stores > Settings > Configuration > Sales > Checkout > Checkout Options; see
  [Adobe's guest checkout documentation](https://experienceleague.adobe.com/en/docs/commerce-admin/stores-sales/point-of-purchase/checkout/checkout-guest).
- **WooCommerce:** *Allow customers to place orders without an account* under
  WooCommerce > Settings > Accounts & Privacy; see
  [WooCommerce's accounts and privacy documentation](https://woocommerce.com/document/accounts-and-privacy).
- If the wall is deliberate (B2B, members only), this `WARN` is expected; agents simply cannot
  complete those purchases.

## "No bot challenge" (bot-challenge)

What it means: the site returned 403, 429 or 503, a challenge header, or challenge text.
agent-gauntlet stopped and did not try to get past it, and neither should you try to make it.

- If you own the site and want to audit it, **allow your own audit traffic**, or test a
  staging copy that has no challenge. On Cloudflare, an IP Access rule set to Allow does not
  bypass WAF custom rules; a custom rule with the *Skip* action is the documented way to skip
  chosen security features for known IP addresses
  ([Cloudflare WAF custom rules](https://developers.cloudflare.com/waf/custom-rules/)).
- Note that allowing audit traffic also tells you nothing about how real agents are treated.
  Whether to let AI shopping agents through at all is your business decision.
- Set a recognisable User-Agent with `AGENT_GAUNTLET_USER_AGENT` if your rule matches on it.

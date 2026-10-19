"""Starter journeys for `agent-gauntlet init`.

Presets are EXPERIMENTAL and NOT verified against a live store: they are only tested against
the built-in fixture shops (that the files parse and validate). Selectors come from the public
template source of each platform's default theme/templates and will differ on customised stores.
"""

from __future__ import annotations

PRESET_NAMES = ("generic", "magento2", "woocommerce")
DEFAULT_BASE_URL = "https://your-store.example"

_HEADER = """\
# agent-gauntlet journey: {name} preset (EXPERIMENTAL, not verified against a live store).
#
# 1. Replace base_url and the product URL below with your own store.
# 2. Only run this against a site you own or have written permission to test:
#      agent-gauntlet run journey.yml --i-have-permission
# 3. Each run adds a product to a cart (up to 6 attempts) and can leave abandoned carts.
# 4. The journey stops before payment. It never places an order.
#
"""

GENERIC = (
    _HEADER.format(name="generic")
    + """\
name: My store checkout
base_url: https://your-store.example
steps:
  - goto: /products/replace-me          # a product page on your store
  - click:
      selector: "button[type=submit]:has-text('Add to cart')"   # replace with your button
      tag: add_to_cart
  - expect_text: "cart"                 # replace with text shown after adding
  - screenshot: added
  - goto: /cart                         # your cart page
  - click:
      selector: "a:has-text('Checkout')"   # replace with your checkout link/button
      tag: checkout
  - screenshot: checkout
"""
)

MAGENTO2 = (
    _HEADER.format(name="magento2")
    + """\
# Selectors follow Magento 2's default templates (add to cart button, cart "Proceed to Checkout"
# button). Themes often change them.
name: My Magento 2 checkout
base_url: https://your-store.example
steps:
  - goto: /replace-with-a-simple-product.html
  - click:
      selector: "#product-addtocart-button"
      tag: add_to_cart
  - expect_text: "You added"
  - screenshot: added
  - goto: /checkout/cart/
  - click:
      selector: "button[data-role='proceed-to-checkout']"
      tag: checkout
  - screenshot: checkout
"""
)

WOOCOMMERCE = (
    _HEADER.format(name="woocommerce")
    + """\
# Selectors follow WooCommerce's default templates (single product add to cart button, cart
# "Proceed to checkout" link). Themes and block-based carts may differ.
name: My WooCommerce checkout
base_url: https://your-store.example
steps:
  - goto: /product/replace-with-a-simple-product/
  - click:
      selector: "button.single_add_to_cart_button"
      tag: add_to_cart
  - expect_text: "has been added to your cart"
  - screenshot: added
  - goto: /cart/
  - click:
      selector: "a.checkout-button"
      tag: checkout
  - screenshot: checkout
"""
)

PRESETS = {"generic": GENERIC, "magento2": MAGENTO2, "woocommerce": WOOCOMMERCE}


def render_preset(name: str, base_url: str | None = None) -> str:
    text = PRESETS[name]
    if base_url:
        text = text.replace(f"base_url: {DEFAULT_BASE_URL}", f"base_url: {base_url}")
    return text

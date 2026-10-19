"""Journey definitions that match the fixture shops (used by tests and the demo)."""

from __future__ import annotations

from typing import Any


def fixture_journey(base_url: str, variant: str = "clean") -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {"goto": "/"},
        {"click": "#product-link"},
    ]
    steps += [
        {"click": {"selector": "#add-to-cart", "tag": "add_to_cart"}},
        {"expect_text": {"text": "Added to cart", "timeout_ms": 2500}},
        {"screenshot": "added"},
        {"click": "#cart-link"},
        {"expect_text": "Your cart"},
        {"click": {"selector": "#checkout-link", "tag": "checkout"}},
        {"expect_text": "Checkout"},
        {"screenshot": "checkout"},
    ]
    return {
        "name": f"Fixture shop: {variant}",
        "base_url": base_url,
        "steps": steps,
    }

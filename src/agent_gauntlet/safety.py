"""Best-effort safety guards.

These are defense in depth, not a guarantee. They look at selectors, visible text and
element attributes. A store can name a pay button anything, so always run journeys
only against sites you own or have written permission to test, and stop before payment.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_SENSITIVE_FIELD = re.compile(
    r"\b("
    r"card|credit|debit|cc|ccnum|cardnumber|cvv|cvc|csc|cvv2|"
    r"password|passwd|pwd|passcode|pin|"
    r"otp|totp|2fa|mfa|one time|onetime|verification code|security code|"
    r"iban|routing|account number|expiry|expiration|exp date|exp month|exp year"
    r")\b",
    re.IGNORECASE,
)

_ORDER_ACTION = re.compile(
    r"\b("
    r"place (your |the |my )?order|"
    r"pay now|pay (and|&) (order|confirm)|pay securely|"
    r"complete (your |the |my )?(purchase|order|payment)|"
    r"buy now|buy it now|"
    r"submit (your |the |my )?(order|payment)|"
    r"confirm (and pay|order|purchase|payment)|"
    r"purchase now"
    r")\b",
    re.IGNORECASE,
)


def _normalise(text: str) -> str:
    """Turn 'placeOrder', 'place-order', '#btn_place_order' into 'place order'."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"[^A-Za-z0-9&]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def looks_sensitive_field(*hints: str | None) -> bool:
    """True if any hint (selector, name, id, placeholder, autocomplete, type...) looks sensitive."""
    return any(h and _SENSITIVE_FIELD.search(_normalise(h)) for h in hints)


def looks_like_order_action(*hints: str | None) -> bool:
    """True if a selector or visible text looks like the final 'pay / place order' action."""
    return any(h and _ORDER_ACTION.search(_normalise(h)) for h in hints)


def hostname_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_local_url(url: str) -> bool:
    return hostname_of(url) in LOCAL_HOSTS

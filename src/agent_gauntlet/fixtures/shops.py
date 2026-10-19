"""Fixture shops served from the standard library, for tests and the demo.

Everything here is a fake store on localhost. It never talks to the internet.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

FORM_KEY = "fk-3f9a2c"

VARIANT_TITLES = {
    "clean": "Clean shop: everything works at any speed",
}


def _page(title: str, body: str, *, status_note: str = "") -> bytes:
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{escape(title)}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;color:#222}}
.fixture-banner{{background:#fff3cd;color:#664d03;padding:8px 16px;font-size:14px}}
main{{max-width:720px;margin:24px auto;padding:0 16px}}
button,a.btn{{font-size:16px;padding:10px 16px;cursor:pointer}}
</style></head><body>
<div class="fixture-banner">agent-gauntlet fixture: a fake shop for testing. Not a real store.{status_note}</div>
<main>{body}</main></body></html>"""
    return html.encode("utf-8")


class ShopState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cart_items = 0
        self.add_attempts = 0
        self.bad_form_key = 0
        self.hits: list[str] = []


class ShopHandler(BaseHTTPRequestHandler):
    server: ShopServer

    def log_message(self, *args: object) -> None:  # keep test output quiet
        pass

    # -- helpers
    def _send(
        self,
        status: int,
        body: bytes,
        ctype: str = "text/html; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -- routes
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        st = self.server.state
        with st.lock:
            st.hits.append(f"GET {path}")
        if path == "/":
            self._send(200, _page("Fixture Shop", HOME))
        elif path == "/product":
            self._send(200, _page("Trail Backpack", product_body(self.server.variant)))
        elif path == "/cart":
            with st.lock:
                n = st.cart_items
            self._send(200, _page("Cart", cart_body(n)))
        elif path == "/checkout":
            self._send(200, _page("Checkout", CHECKOUT))
        elif path == "/__state":
            with st.lock:
                data = {
                    "cart_items": st.cart_items,
                    "add_attempts": st.add_attempts,
                    "bad_form_key": st.bad_form_key,
                }
            self._send(200, json.dumps(data).encode(), "application/json")
        else:
            self._send(404, _page("Not found", "<h1>Not found</h1>"))

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        st = self.server.state
        length = int(self.headers.get("Content-Length") or 0)
        fields = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        with st.lock:
            st.hits.append(f"POST {path}")
        if path != "/cart/add":
            self._send(404, _page("Not found", "<h1>Not found</h1>"))
            return
        with st.lock:
            st.add_attempts += 1
            ok = fields.get("form_key", [""])[0] == FORM_KEY
            if ok:
                st.cart_items += 1
            else:
                st.bad_form_key += 1
        wants_json = self.headers.get("X-Requested-With") == "fetch"
        if not ok:
            if wants_json:
                self._send(400, b'{"ok":false}', "application/json")
            else:
                self._send(
                    400,
                    _page(
                        "Error",
                        "<h1>Invalid Form Key</h1><p>Please refresh the page and try again.</p>",
                    ),
                )
        elif wants_json:
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._redirect("/cart")


class ShopServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, variant: str, host: str = "127.0.0.1", port: int = 0):
        super().__init__((host, port), ShopHandler)
        self.variant = variant
        self.state = ShopState()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


HOME = """<h1>Fixture Shop</h1>
<p>One product, one cart, one checkout.</p>
<p><a id="product-link" href="/product">Trail Backpack, $49.00</a></p>"""

CHECKOUT = """<h1>Checkout</h1>
<form onsubmit="return false">
<p><label>Email <input id="email" name="email" type="email"></label></p>
<p><label>Card number <input id="card-number" name="card_number" autocomplete="cc-number"></label></p>
<p><button id="place-order" type="button">Place order</button></p>
</form>
<p>This fixture never takes payment.</p>"""


def cart_body(items: int) -> str:
    return (
        f'<h1>Your cart</h1><p id="cart-count">Cart: {items} item(s)</p>'
        '<p><a id="checkout-link" class="btn" href="/checkout">Go to checkout</a></p>'
    )


def product_script(delay_ms: int = 0) -> str:
    """Wires the form key and the add-to-cart handler, optionally after a delay."""
    return f"""
function init() {{
  var form = document.getElementById('atc');
  var status = document.getElementById('cart-status');
  document.getElementById('form_key').value = '{FORM_KEY}';
  form.addEventListener('submit', function (e) {{
    e.preventDefault();
    fetch('/cart/add', {{method: 'POST', headers: {{'X-Requested-With': 'fetch'}},
      body: new URLSearchParams(new FormData(form))}})
      .then(function (r) {{ status.textContent = r.ok ? 'Added to cart' : 'Could not add to cart'; }});
  }});
}}
{f"setTimeout(init, {delay_ms});" if delay_ms else "init();"}
"""


def product_body(variant: str) -> str:
    return f"""<h1>Trail Backpack</h1><p>$49.00</p>
<form id="atc" method="post" action="/cart/add">
<input type="hidden" name="form_key" id="form_key" value="">
<button id="add-to-cart" type="submit">Add to cart</button>
</form>
<p id="cart-status" role="status"></p>
<p><a id="cart-link" href="/cart">View cart</a></p>
<script>{product_script()}</script>"""


@contextmanager
def serve_shop(
    variant: str = "clean", host: str = "127.0.0.1", port: int = 0
) -> Iterator[ShopServer]:
    if variant not in VARIANT_TITLES:
        raise ValueError(f"unknown fixture variant: {variant}")
    server = ShopServer(variant, host, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

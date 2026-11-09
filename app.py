from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen
import mimetypes

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("PAYAGENT_DB", str(BASE_DIR / "instance" / "payagent.db")))
INSTANCE_DIR = DB_PATH.parent
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)


def load_local_env() -> None:
    """Load simple KEY=VALUE pairs from .env without third-party packages."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_local_env()

PRODUCTS: dict[str, dict[str, Any]] = {
    "watch-pro": {"id":"watch-pro", "name":"Pulse Watch Pro", "category":"Wearables", "description":"GPS fitness tracking, sleep insights and a 7-day battery.", "price":129.99, "color":"blue", "icon":"◉", "tag":"BEST SELLER"},
    "audio-max": {"id":"audio-max", "name":"Audio Max Headphones", "category":"Audio", "description":"Noise isolation, rich sound and all-day comfort.", "price":89.99, "color":"violet", "icon":"♫", "tag":"POPULAR"},
    "key-pro": {"id":"key-pro", "name":"Key Pro Mechanical", "category":"Workspace", "description":"Compact mechanical keyboard with hot-swap switches.", "price":119.00, "color":"orange", "icon":"⌨", "tag":"NEW"},
    "travel-pack": {"id":"travel-pack", "name":"Nomad Travel Pack", "category":"Travel", "description":"Weather-resistant 28L backpack with laptop protection.", "price":64.50, "color":"green", "icon":"▣", "tag":"VALUE PICK"},
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def money(value: float) -> float:
    return round(float(value) + 1e-9, 2)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def add_event(db: sqlite3.Connection, tx_id: str, event_type: str, detail: str) -> None:
    db.execute("INSERT INTO events(transaction_id, created_at, event_type, detail) VALUES (?, ?, ?, ?)", (tx_id, iso_now(), event_type, detail))


def seed_demo_data(db: sqlite3.Connection) -> None:
    now = utc_now()
    samples = [
        {"id":"PA-10428", "minutes":8, "buyer":"alex.buyer", "product_id":"watch-pro", "quantity":1, "unit_price":121.99, "status":"APPROVED", "risk_score":12, "risk_level":"LOW", "risk_reasons":["Known device", "Purchase pattern consistent"], "device_new":0, "country_mismatch":0, "payment_ref":"MOCK-8F3A21", "note":"Member price accepted after negotiation."},
        {"id":"PA-10427", "minutes":26, "buyer":"maya.chen", "product_id":"audio-max", "quantity":2, "unit_price":84.59, "status":"APPROVED", "risk_score":18, "risk_level":"LOW", "risk_reasons":["Returning buyer", "Quantity discount applied"], "device_new":0, "country_mismatch":0, "payment_ref":"MOCK-7D91B4", "note":"Bundle pricing accepted."},
        {"id":"PA-10426", "minutes":49, "buyer":"sam.rivera", "product_id":"key-pro", "quantity":1, "unit_price":109.00, "status":"REVIEW_REQUIRED", "risk_score":72, "risk_level":"HIGH", "risk_reasons":["New device fingerprint", "Billing country differs from recent profile", "Unusual order value"], "device_new":1, "country_mismatch":1, "payment_ref":"MOCK-4C8E10", "note":"Sample transaction intentionally flagged."},
        {"id":"PA-10425", "minutes":93, "buyer":"jordan.lee", "product_id":"travel-pack", "quantity":3, "unit_price":59.99, "status":"RESOLVED", "risk_score":42, "risk_level":"MEDIUM", "risk_reasons":["Higher than usual purchase velocity"], "device_new":0, "country_mismatch":0, "payment_ref":"MOCK-2A6B09", "note":"Evidence reviewed by merchant operations."},
    ]
    for item in samples:
        product = PRODUCTS[item["product_id"]]
        created = (now - timedelta(minutes=item["minutes"])).isoformat(timespec="seconds")
        total = money(item["unit_price"] * item["quantity"])
        evidence = [
            {"label":"Buyer profile", "value":f"{item['buyer']} · demo loyalty member"},
            {"label":"Order integrity", "value":"Product, quantity and negotiated price recorded"},
            {"label":"Device signal", "value":"New device" if item["device_new"] else "Known device"},
            {"label":"Location signal", "value":"Country mismatch" if item["country_mismatch"] else "Consistent billing region"},
            {"label":"Payment reference", "value":item["payment_ref"]},
        ]
        db.execute(
            """INSERT INTO transactions
            (id, created_at, buyer, product_id, product_name, quantity, unit_price, total, status,
             risk_score, risk_level, risk_reasons, payment_mode, payment_ref, device_new,
             country_mismatch, buyer_message, transcript, evidence, is_seed)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MOCK', ?, ?, ?, ?, ?, ?, 1)""",
            (item["id"], created, item["buyer"], item["product_id"], product["name"], item["quantity"], item["unit_price"], total,
             item["status"], item["risk_score"], item["risk_level"], json.dumps(item["risk_reasons"]), item["payment_ref"],
             item["device_new"], item["country_mismatch"], item["note"], json.dumps([{"role":"agent", "text":item["note"]}]), json.dumps(evidence)),
        )
        add_event(db, item["id"], "INITIATED", "Buyer agent created the order intent.")
        add_event(db, item["id"], "AGREEMENT", "Negotiated terms and final amount were recorded.")
        add_event(db, item["id"], "PAYMENT_SIMULATED", "Demo payment reference: " + item["payment_ref"])
        add_event(db, item["id"], "RISK_ASSESSED", f"Risk score {item['risk_score']} / 100 ({item['risk_level']}).")
        if item["status"] == "RESOLVED":
            add_event(db, item["id"], "RESOLVED", "Merchant operations marked the review as resolved.")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, buyer TEXT NOT NULL, product_id TEXT NOT NULL,
            product_name TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price REAL NOT NULL, total REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD', status TEXT NOT NULL, risk_score INTEGER NOT NULL,
            risk_level TEXT NOT NULL, risk_reasons TEXT NOT NULL, payment_mode TEXT NOT NULL, payment_ref TEXT,
            device_new INTEGER NOT NULL DEFAULT 0, country_mismatch INTEGER NOT NULL DEFAULT 0,
            buyer_message TEXT NOT NULL DEFAULT '', transcript TEXT NOT NULL DEFAULT '[]', evidence TEXT NOT NULL DEFAULT '[]',
            is_seed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id TEXT NOT NULL, created_at TEXT NOT NULL,
            event_type TEXT NOT NULL, detail TEXT NOT NULL,
            FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS pending_orders (paypal_order_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL);
        """)
        count = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        if count == 0:
            seed_demo_data(db)


def extract_price(message: str) -> float | None:
    text = (message or "").strip().lower()
    if not text:
        return None
    patterns = [r"\$\s*(\d{1,4}(?:\.\d{1,2})?)", r"\b(?:usd|dollars?)\s*(\d{1,4}(?:\.\d{1,2})?)\b", r"\b(?:pay|offer|budget|do|at|for)\s*(?:me\s*)?(?:is\s*)?\$?\s*(\d{1,4}(?:\.\d{1,2})?)\b"]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    if re.fullmatch(r"\s*\d{1,4}(?:\.\d{1,2})?\s*", text):
        return float(text)
    return None


def negotiate(product_id: str, quantity: int, message: str) -> dict[str, Any]:
    product = PRODUCTS.get(product_id)
    if not product:
        raise ValueError("Choose a valid product before negotiating.")
    if quantity < 1 or quantity > 5:
        raise ValueError("Quantity must be between 1 and 5 for this demo.")
    base = float(product["price"])
    quantity_discount = 0.00 if quantity == 1 else (0.04 if quantity == 2 else 0.06)
    loyalty_discount = 0.03
    total_discount = min(0.08, quantity_discount + loyalty_discount)
    personalized_price = money(base * (1 - total_discount))
    floor_price = money(base * 0.82)
    requested = extract_price(message)
    if requested is None:
        final_price, accepted = personalized_price, False
        headline = "Your member price is ready"
        explanation = f"I found a {total_discount * 100:.0f}% personalized saving based on your Plus membership" + (" and multi-item order." if quantity > 1 else ".") + " You can apply this price to checkout."
        decision = "PERSONALIZED_OFFER"
    elif requested > base:
        final_price, accepted = base, True
        headline = "Offer accepted at list price"
        explanation = "Your proposed amount is above the current list price, so the checkout price stays at the lower list price."
        decision = "CAPPED_AT_LIST"
    elif requested >= floor_price:
        final_price, accepted = money(requested), True
        headline = "Deal accepted"
        explanation = f"Your offer is within the merchant's demo negotiation range. You save ${money(base - final_price):.2f} per item."
        decision = "OFFER_ACCEPTED"
    else:
        final_price, accepted = max(floor_price, personalized_price), False
        headline = "The agent has a counter-offer"
        explanation = f"${requested:.2f} is below the demo merchant's minimum of ${floor_price:.2f}. I can offer ${final_price:.2f} per item instead."
        decision = "COUNTER_OFFER"
    transcript = [{"role":"buyer", "text":message or "Find my best member price."}, {"role":"agent", "text":explanation}]
    return {"product":product, "quantity":quantity, "list_price":money(base), "requested_price":money(requested) if requested is not None else None,
            "suggested_price":money(final_price), "total":money(final_price*quantity), "savings_per_item":money(base-final_price),
            "accepted":accepted, "decision":decision, "headline":headline, "message":explanation, "floor_price":floor_price, "transcript":transcript}


def evaluate_risk(total: float, device_new: bool, country_mismatch: bool, quantity: int, buyer: str = "demo_member") -> dict[str, Any]:
    score = 8
    reasons = ["Baseline transaction checks passed"]
    if total >= 250:
        score += 18; reasons.append("Order value is above the demo review threshold ($250)")
    if total >= 500:
        score += 12; reasons.append("High-value order requires additional review")
    if device_new:
        score += 30; reasons.append("New device fingerprint")
    if country_mismatch:
        score += 30; reasons.append("Billing country differs from recent buyer profile")
    since = (utc_now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    with get_db() as db:
        velocity = db.execute("SELECT COUNT(*) FROM transactions WHERE buyer = ? AND created_at >= ? AND is_seed = 0", (buyer, since)).fetchone()[0]
    if velocity >= 2:
        score += 20; reasons.append("Unusual checkout velocity for this buyer")
    if quantity >= 4:
        score += 8; reasons.append("Large quantity compared with a typical demo order")
    score = min(100, score)
    level = "HIGH" if score >= 60 else ("MEDIUM" if score >= 30 else "LOW")
    return {"score":score, "level":level, "status":"REVIEW_REQUIRED" if level == "HIGH" else "APPROVED", "reasons":reasons}


def paypal_enabled() -> bool:
    return bool(os.getenv("PAYPAL_CLIENT_ID") and os.getenv("PAYPAL_CLIENT_SECRET"))


def paypal_request(method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    client_id, secret = os.getenv("PAYPAL_CLIENT_ID", ""), os.getenv("PAYPAL_CLIENT_SECRET", "")
    if not client_id or not secret:
        raise RuntimeError("PayPal Sandbox credentials are not configured.")
    credentials = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    token_req = Request("https://api-m.sandbox.paypal.com/v1/oauth2/token", data=b"grant_type=client_credentials", method="POST",
                        headers={"Authorization":f"Basic {credentials}", "Accept":"application/json", "Accept-Language":"en_US", "Content-Type":"application/x-www-form-urlencoded"})
    with urlopen(token_req, timeout=20) as response:
        token = json.loads(response.read().decode())["access_token"]
    body = json.dumps(data or {}).encode()
    req = Request("https://api-m.sandbox.paypal.com" + path, data=body if method.upper() != "GET" else None, method=method.upper(),
                  headers={"Authorization":f"Bearer {token}", "Content-Type":"application/json", "PayPal-Request-Id":str(uuid.uuid4())})
    with urlopen(req, timeout=25) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw else {}


def persist_transaction(payload: dict[str, Any], payment_mode: str, payment_ref: str) -> dict[str, Any]:
    tx_id = "PA-" + uuid.uuid4().hex[:8].upper()
    now = iso_now()
    product = PRODUCTS[payload["product_id"]]
    total = money(float(payload["unit_price"]) * int(payload["quantity"]))
    risk = evaluate_risk(total, bool(payload.get("device_new")), bool(payload.get("country_mismatch")), int(payload["quantity"]), payload.get("buyer", "demo_member"))
    evidence = [
        {"label":"Buyer profile", "value":f"{payload.get('buyer','demo_member')} · Plus demo member"},
        {"label":"Negotiation", "value":payload.get("buyer_message") or "Personalized member offer"},
        {"label":"Order integrity", "value":f"{payload['quantity']} × {product['name']} at ${float(payload['unit_price']):.2f} each"},
        {"label":"Device signal", "value":"New device fingerprint" if payload.get("device_new") else "Known device"},
        {"label":"Location signal", "value":"Billing country mismatch" if payload.get("country_mismatch") else "Consistent billing region"},
        {"label":"Payment reference", "value":payment_ref},
        {"label":"Payment mode", "value":"PayPal Sandbox" if payment_mode == "PAYPAL_SANDBOX" else "Simulated payment - no money moved"},
    ]
    transcript = payload.get("transcript", []) if isinstance(payload.get("transcript", []), list) else []
    with get_db() as db:
        db.execute("""INSERT INTO transactions
            (id, created_at, buyer, product_id, product_name, quantity, unit_price, total, currency, status,
             risk_score, risk_level, risk_reasons, payment_mode, payment_ref, device_new, country_mismatch,
             buyer_message, transcript, evidence, is_seed)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'USD', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (tx_id, now, payload.get("buyer","demo_member"), payload["product_id"], product["name"], int(payload["quantity"]),
             float(payload["unit_price"]), total, risk["status"], risk["score"], risk["level"], json.dumps(risk["reasons"]),
             payment_mode, payment_ref, int(bool(payload.get("device_new"))), int(bool(payload.get("country_mismatch"))),
             payload.get("buyer_message", ""), json.dumps(transcript), json.dumps(evidence)))
        add_event(db, tx_id, "INITIATED", "Buyer agent initiated checkout and stored the order intent.")
        add_event(db, tx_id, "AGREEMENT", f"Negotiated unit price ${float(payload['unit_price']):.2f}; quantity {payload['quantity']}.")
        add_event(db, tx_id, "PAYMENT_CAPTURED" if payment_mode == "PAYPAL_SANDBOX" else "PAYMENT_SIMULATED", f"Payment reference: {payment_ref}")
        add_event(db, tx_id, "RISK_ASSESSED", f"Risk score {risk['score']} / 100 ({risk['level']}).")
        if risk["status"] == "REVIEW_REQUIRED":
            add_event(db, tx_id, "SHIELD_ALERT", "Funds/order routed to merchant review queue by the demo risk rules.")
        else:
            add_event(db, tx_id, "AUTO_APPROVED", "Transaction passed the demo risk rules.")
    return {"id":tx_id, "risk":risk, "total":total, "payment_ref":payment_ref, "payment_mode":payment_mode}


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key in ("risk_reasons", "transcript", "evidence"):
        try: item[key] = json.loads(item[key] or "[]")
        except (TypeError, json.JSONDecodeError): item[key] = []
    for key in ("device_new", "country_mismatch", "is_seed"):
        item[key] = bool(item[key])
    return item


def build_state() -> dict[str, Any]:
    with get_db() as db:
        transactions = [row_to_dict(row) for row in db.execute("SELECT * FROM transactions ORDER BY created_at DESC LIMIT 100").fetchall()]
        events = [dict(row) for row in db.execute("SELECT * FROM events ORDER BY event_id DESC LIMIT 30").fetchall()]
        total_count = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        approved_count = db.execute("SELECT COUNT(*) FROM transactions WHERE status = 'APPROVED'").fetchone()[0]
        cleared_count = db.execute("SELECT COUNT(*) FROM transactions WHERE status IN ('APPROVED','RESOLVED')").fetchone()[0]
        review_count = db.execute("SELECT COUNT(*) FROM transactions WHERE status='REVIEW_REQUIRED'").fetchone()[0]
        volume = db.execute("SELECT COALESCE(SUM(total),0) FROM transactions").fetchone()[0]
    mode = os.getenv("PAYMENT_MODE", "mock").lower()
    return {"products":list(PRODUCTS.values()), "transactions":transactions, "events":events,
            "stats":{"total_transactions":total_count, "approved_transactions":approved_count, "cleared_transactions":cleared_count, "review_queue":review_count,
                     "gross_volume":money(volume), "approval_rate":round(cleared_count/total_count*100) if total_count else 0},
            "config":{"payment_mode":"PAYPAL_SANDBOX" if mode == "paypal" and paypal_enabled() else "MOCK", "paypal_ready":paypal_enabled()}}


class PayAgentHandler(BaseHTTPRequestHandler):
    server_version = "PayAgentDemo/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the local terminal readable; HTTP requests still return standard statuses.
        print(f"[{self.log_date_time_string()}] {format % args}")

    def send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any]:
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 1_000_000)
            raw = self.rfile.read(length) if length else b"{}"
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else {}
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        target = None
        content_type = "text/html; charset=utf-8"
        body_length = 0
        if path == "/":
            html = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
            html = html.replace("{{ url_for('static', filename='styles.css') }}", "/static/styles.css")
            html = html.replace("{{ url_for('static', filename='app.js') }}", "/static/app.js")
            body_length = len(html.encode("utf-8"))
        elif path.startswith("/static/"):
            relative = path.removeprefix("/static/")
            target = (BASE_DIR / "static" / relative).resolve()
            static_root = (BASE_DIR / "static").resolve()
            if not str(target).startswith(str(static_root)) or not target.is_file():
                self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            body_length = target.stat().st_size
        else:
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(body_length))
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path == "/":
            html = (BASE_DIR / "index.html").read_text(encoding="utf-8")
            self.send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
        elif path in {"/app.js", "/style.css"} or path.startswith("/static/"):
            relative = path.rsplit("/", 1)[-1]
            if relative not in {"app.js", "style.css"}:
                self.send_json({"error":"File not found."}, 404); return
            target = BASE_DIR / relative
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.send_bytes(target.read_bytes(), content_type)
        elif path == "/api/state":
            self.send_json(build_state())
        elif path.startswith("/api/transactions/") and path.endswith("/evidence"):
            tx_id = path.split("/")[3]
            self.handle_evidence(tx_id)
        elif path.startswith("/api/transactions/"):
            tx_id = path.split("/")[3]
            self.handle_transaction_detail(tx_id)
        elif path == "/paypal/return":
            self.handle_paypal_return(parse_qs(parsed.query).get("token", [""])[0])
        elif path == "/paypal/cancel":
            self.redirect("/?payment=cancelled")
        else:
            self.send_json({"error":"Not found."}, 404)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        data = self.read_json()
        if path == "/api/negotiate":
            try:
                result = negotiate(str(data.get("product_id", "")), int(data.get("quantity", 1)), str(data.get("message", "")))
                self.send_json(result)
            except (ValueError, TypeError) as exc:
                self.send_json({"error":str(exc)}, 400)
        elif path == "/api/checkout":
            self.handle_checkout(data)
        elif path.startswith("/api/transactions/") and path.endswith("/action"):
            tx_id = unquote(path.split("/")[3])
            self.handle_transaction_action(tx_id, data)
        elif path == "/api/reset-demo":
            with get_db() as db:
                db.execute("DELETE FROM events"); db.execute("DELETE FROM transactions"); db.execute("DELETE FROM pending_orders")
                seed_demo_data(db)
            self.send_json({"success":True, "message":"Demo data has been reset."})
        else:
            self.send_json({"error":"Not found."}, 404)

    def handle_checkout(self, data: dict[str, Any]) -> None:
        product_id = str(data.get("product_id", ""))
        if product_id not in PRODUCTS:
            self.send_json({"error":"Select a valid product."}, 400); return
        try:
            quantity = int(data.get("quantity", 1))
            unit_price = money(float(data.get("unit_price", PRODUCTS[product_id]["price"])))
        except (ValueError, TypeError):
            self.send_json({"error":"Quantity or price is invalid."}, 400); return
        product = PRODUCTS[product_id]
        floor_price = money(product["price"] * 0.82)
        if quantity < 1 or quantity > 5:
            self.send_json({"error":"Quantity must be between 1 and 5."}, 400); return
        if unit_price < floor_price or unit_price > product["price"]:
            self.send_json({"error":f"Price must be between ${floor_price:.2f} and ${product['price']:.2f}. Please negotiate again."}, 400); return
        payload = {"buyer":"demo_member", "product_id":product_id, "quantity":quantity, "unit_price":unit_price,
                   "device_new":bool(data.get("device_new")), "country_mismatch":bool(data.get("country_mismatch")),
                   "buyer_message":str(data.get("buyer_message", ""))[:500], "transcript":data.get("transcript", []) if isinstance(data.get("transcript", []), list) else []}
        if os.getenv("PAYMENT_MODE", "mock").lower() == "paypal":
            if not paypal_enabled():
                self.send_json({"error":"PayPal Sandbox mode is selected, but PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are missing. Add them to .env or switch PAYMENT_MODE=mock."}, 400); return
            total = money(unit_price * quantity)
            host = self.headers.get("Host", "127.0.0.1:5000")
            if not re.fullmatch(r"[A-Za-z0-9.:-]+", host):
                self.send_json({"error":"Invalid local Host header."}, 400); return
            base = f"http://{host}"
            order_body = {"intent":"CAPTURE", "purchase_units":[{"reference_id":"PAYAGENT-"+uuid.uuid4().hex[:10].upper(),
                "description":f"PayAgent AI demo order - {product['name']}", "amount":{"currency_code":"USD", "value":f"{total:.2f}"}}],
                "payment_source":{"paypal":{"experience_context":{"brand_name":"PayAgent AI Demo", "user_action":"PAY_NOW", "shipping_preference":"NO_SHIPPING",
                "return_url":base+"/paypal/return", "cancel_url":base+"/paypal/cancel"}}}}
            try:
                order = paypal_request("POST", "/v2/checkout/orders", order_body)
                approve_url = next((link["href"] for link in order.get("links", []) if link.get("rel") in ("payer-action", "approve")), None)
                if not approve_url:
                    self.send_json({"error":"PayPal created the order but did not return an approval link."}, 502); return
                with get_db() as db:
                    db.execute("INSERT OR REPLACE INTO pending_orders(paypal_order_id,payload,created_at) VALUES(?,?,?)", (order["id"], json.dumps(payload), iso_now()))
                self.send_json({"paypal":True, "approve_url":approve_url, "order_id":order["id"]})
            except (HTTPError, URLError, TimeoutError, RuntimeError, KeyError) as exc:
                detail = getattr(exc, "reason", str(exc))
                if isinstance(exc, HTTPError):
                    try: detail = exc.read().decode("utf-8")[:600]
                    except Exception: pass
                self.send_json({"error":"PayPal Sandbox request failed.", "details":str(detail)[:600]}, 502)
            return
        payment_ref = "MOCK-" + uuid.uuid4().hex[:8].upper()
        result = persist_transaction(payload, "MOCK", payment_ref)
        self.send_json({"success":True, "simulated":True, "message":"Demo checkout completed. No real money was moved.", **result})

    def handle_paypal_return(self, order_id: str) -> None:
        with get_db() as db:
            row = db.execute("SELECT payload FROM pending_orders WHERE paypal_order_id = ?", (order_id,)).fetchone()
        if not row:
            self.redirect("/?payment=unknown"); return
        try:
            capture = paypal_request("POST", f"/v2/checkout/orders/{order_id}/capture", {})
            if capture.get("status") != "COMPLETED":
                self.redirect("/?payment=not_completed"); return
            result = persist_transaction(json.loads(row["payload"]), "PAYPAL_SANDBOX", order_id)
            with get_db() as db:
                db.execute("DELETE FROM pending_orders WHERE paypal_order_id = ?", (order_id,))
            self.redirect(f"/?payment=success&transaction={result['id']}")
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError, KeyError):
            self.redirect("/?payment=error")

    def handle_transaction_detail(self, tx_id: str) -> None:
        with get_db() as db:
            row = db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
            if not row:
                self.send_json({"error":"Transaction not found."}, 404); return
            events = [dict(r) for r in db.execute("SELECT * FROM events WHERE transaction_id = ? ORDER BY event_id", (tx_id,)).fetchall()]
        self.send_json({"transaction":row_to_dict(row), "events":events})

    def handle_evidence(self, tx_id: str) -> None:
        with get_db() as db:
            row = db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
            if not row:
                self.send_json({"error":"Transaction not found."}, 404); return
            events = [dict(r) for r in db.execute("SELECT * FROM events WHERE transaction_id = ? ORDER BY event_id", (tx_id,)).fetchall()]
        item = row_to_dict(row)
        packet = {"packet_type":"PayAgent AI demo evidence packet", "generated_at":iso_now(),
                  "notice":"Demonstration data only. This is not a real chargeback submission or legal evidence certification.",
                  "transaction":item, "risk_assessment":{"score":item["risk_score"], "level":item["risk_level"], "reasons":item["risk_reasons"]},
                  "evidence":item["evidence"], "audit_timeline":events}
        self.send_json(packet)

    def handle_transaction_action(self, tx_id: str, data: dict[str, Any]) -> None:
        action = data.get("action")
        with get_db() as db:
            row = db.execute("SELECT status FROM transactions WHERE id = ?", (tx_id,)).fetchone()
            if not row:
                self.send_json({"error":"Transaction not found."}, 404); return
            if action == "resolve":
                db.execute("UPDATE transactions SET status='RESOLVED' WHERE id = ?", (tx_id,))
                add_event(db, tx_id, "RESOLVED", "Merchant operations marked the transaction review as resolved in demo mode.")
                message = "Review marked as resolved."
            elif action == "request_evidence":
                add_event(db, tx_id, "EVIDENCE_REQUESTED", "Merchant operations requested additional buyer evidence.")
                message = "Evidence request added to the audit timeline."
            else:
                self.send_json({"error":"Unsupported action."}, 400); return
        self.send_json({"success":True, "message":message})


def main() -> None:
    init_db()
    host = "0.0.0.0" if os.getenv("DOCKER_MODE") == "1" else "127.0.0.1"
    port = int(os.getenv("PORT", "5000"))
    server = ThreadingHTTPServer((host, port), PayAgentHandler)
    print("\n  PayAgent AI demo is running")
    print(f"  Open http://127.0.0.1:{port} in your browser")
    print(f"  Payment mode: {'PayPal Sandbox' if os.getenv('PAYMENT_MODE','mock').lower() == 'paypal' and paypal_enabled() else 'Mock (no real money)'}")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PayAgent AI demo...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

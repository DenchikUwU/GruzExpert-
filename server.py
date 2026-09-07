#!/usr/bin/env python3
"""GruZExpert local production starter. Run: python3 server.py"""
import json
import os
import secrets
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
ORDERS_FILE = ROOT / "data" / "orders.json"
ADMIN_KEY = os.getenv("GRUZEXPERT_ADMIN_KEY", "")
MAX_BODY = 20_000
REQUIRED_FIELDS = ("from", "to", "name", "phone", "email", "pickupLift", "deliveryLift", "tariff")

def read_orders():
    try:
        with ORDERS_FILE.open(encoding="utf-8") as file:
            records = json.load(file)
            return records if isinstance(records, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def write_orders(records):
    ORDERS_FILE.parent.mkdir(exist_ok=True)
    temp_file = ORDERS_FILE.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
    temp_file.replace(ORDERS_FILE)

def send_email(order):
    """Sends email only after SMTP settings are configured in environment variables."""
    host, recipient = os.getenv("SMTP_HOST"), os.getenv("ORDER_RECIPIENT")
    if not host or not recipient:
        return False
    text = "\n".join(f"{key}: {value}" for key, value in order.items() if key not in ("id",))
    message = EmailMessage()
    message["Subject"] = f"Naujas GruZExpert užsakymas – {order['name']}"
    message["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "orders@localhost"))
    message["To"] = recipient
    message.set_content(text)
    port = int(os.getenv("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as server:
        if os.getenv("SMTP_USER"):
            server.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        server.send_message(message)
    return True

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def json_response(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def is_admin(self):
        return bool(ADMIN_KEY) and secrets.compare_digest(self.headers.get("X-Admin-Key", ""), ADMIN_KEY)

    def do_POST(self):
        if urlparse(self.path).path != "/api/orders":
            return self.send_error(HTTPStatus.NOT_FOUND)
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > MAX_BODY:
            return self.json_response(HTTPStatus.BAD_REQUEST, {"error": "Invalid request size"})
        try:
            order = json.loads(self.rfile.read(size))
        except json.JSONDecodeError:
            return self.json_response(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON"})
        if not isinstance(order, dict) or any(not str(order.get(field, "")).strip() for field in REQUIRED_FIELDS):
            return self.json_response(HTTPStatus.BAD_REQUEST, {"error": "Please complete required fields"})
        order = {key: str(value).strip()[:1000] for key, value in order.items() if isinstance(key, str)}
        order["id"] = secrets.token_urlsafe(10)
        order["createdAt"] = datetime.now(timezone.utc).isoformat()
        orders = read_orders(); orders.append(order); write_orders(orders)
        try:
            emailed = send_email(order)
        except Exception as error:
            print(f"Email was not sent: {error}")
            emailed = False
        return self.json_response(HTTPStatus.CREATED, {"ok": True, "id": order["id"], "emailed": emailed})

    def do_GET(self):
        if urlparse(self.path).path != "/api/orders":
            return super().do_GET()
        if not self.is_admin():
            return self.json_response(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
        return self.json_response(HTTPStatus.OK, read_orders())

    def do_DELETE(self):
        order_id = urlparse(self.path).path.removeprefix("/api/orders/")
        if not order_id or not self.is_admin():
            return self.json_response(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
        orders = read_orders()
        remaining = [order for order in orders if order.get("id") != order_id]
        if len(remaining) == len(orders):
            return self.json_response(HTTPStatus.NOT_FOUND, {"error": "Order not found"})
        write_orders(remaining)
        return self.json_response(HTTPStatus.OK, {"ok": True})

if __name__ == "__main__":
    if not ADMIN_KEY:
        print("WARNING: set GRUZEXPERT_ADMIN_KEY before placing the site online; admin access is disabled.")
    port = int(os.getenv("PORT", "8000"))
    print(f"GruZExpert is running on http://localhost:{port}")
    ThreadingHTTPServer(("", port), Handler).serve_forever()

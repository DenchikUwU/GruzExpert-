#!/usr/bin/env python3
"""GruZExpert local production starter. Run: python3 server.py"""
import base64
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
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"

def load_env_file():
    """Loads local deployment settings without adding another dependency."""
    if not ENV_FILE.exists():
        return
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env_file()
ORDERS_FILE = ROOT / "data" / "orders.json"
REVIEWS_FILE = ROOT / "data" / "reviews.json"
ADMIN_KEY = os.getenv("GRUZEXPERT_ADMIN_KEY", "")
MAX_BODY = 20_000
REQUIRED_FIELDS = ("from", "to", "name", "phone", "email", "pickupLift", "deliveryLift", "tariff")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
FRONTEND_ORIGINS = {"https://gruzexpert.onrender.com", "http://localhost:8000", "http://127.0.0.1:8000"}
try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None
    Jsonb = None


def db_connect():
    if not DATABASE_URL:
        return None
    if psycopg is None:
        raise RuntimeError("DATABASE_URL is set but psycopg is not installed")
    return psycopg.connect(DATABASE_URL)


def ensure_database():
    if not DATABASE_URL:
        print("DATABASE_URL not set; using local JSON files (not durable on Render).")
        return

    with db_connect() as conn:
        # Inspect an existing table before changing it. Older versions of the
        # project may have created this table with a different schema.
        table_exists = conn.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'gruzexpert_records'
            )
        """).fetchone()[0]

        if table_exists:
            columns = {
                row[0] for row in conn.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'gruzexpert_records'
                """).fetchall()
            }
            # If the existing table is from an incompatible older schema,
            # preserve it under a legacy name instead of deleting its rows.
            # The application then creates a clean table with the schema it uses.
            if not {'record_type', 'record_id'}.issubset(columns):
                legacy_name = 'gruzexpert_records_legacy'
                legacy_exists = conn.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = current_schema() AND table_name = %s
                    )
                """, (legacy_name,)).fetchone()[0]
                if legacy_exists:
                    suffix = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
                    legacy_name = f'gruzexpert_records_legacy_{suffix}'
                # legacy_name is generated from a fixed prefix and UTC digits.
                conn.execute(f'ALTER TABLE gruzexpert_records RENAME TO {legacy_name}')
                print(f"Preserved incompatible database table as {legacy_name}; legacy rows were not deleted.")

        conn.execute("""CREATE TABLE IF NOT EXISTS gruzexpert_records (
            record_type TEXT NOT NULL,
            record_id TEXT NOT NULL,
            data JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (record_type, record_id)
        )""")
        conn.execute("ALTER TABLE gruzexpert_records ADD COLUMN IF NOT EXISTS data JSONB")
        conn.execute("ALTER TABLE gruzexpert_records ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    print("PostgreSQL storage is ready (schema checked).")


def db_read_records(record_type):
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT data FROM gruzexpert_records WHERE record_type = %s ORDER BY created_at ASC",
            (record_type,)
        ).fetchall()
        return [row[0] for row in rows]


def db_write_records(record_type, records):
    with db_connect() as conn:
        # Keep legacy rows with NULL data intact; they may contain records in
        # an older schema that this version cannot safely reinterpret.
        conn.execute("DELETE FROM gruzexpert_records WHERE record_type = %s AND data IS NOT NULL", (record_type,))
        for record in records:
            conn.execute(
                "INSERT INTO gruzexpert_records (record_type, record_id, data) VALUES (%s, %s, %s) "
                "ON CONFLICT (record_type, record_id) DO UPDATE SET data = EXCLUDED.data, created_at = NOW()",
                (record_type, str(record["id"]), Jsonb(record))
            )

def read_records(file_path):
    try:
        with file_path.open(encoding="utf-8") as file:
            records = json.load(file)
            return records if isinstance(records, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def write_records(file_path, records):
    file_path.parent.mkdir(exist_ok=True)
    temp_file = file_path.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
    temp_file.replace(file_path)

def read_orders():
    return db_read_records("order") if DATABASE_URL else read_records(ORDERS_FILE)

def write_orders(records):
    if DATABASE_URL:
        db_write_records("order", records)
    else:
        write_records(ORDERS_FILE, records)

def read_reviews():
    return db_read_records("review") if DATABASE_URL else read_records(REVIEWS_FILE)

def write_reviews(records):
    if DATABASE_URL:
        db_write_records("review", records)
    else:
        write_records(REVIEWS_FILE, records)

def order_text(order):
    labels = {
        "from": "Iš kur", "to": "Į kur", "name": "Klientas", "phone": "Telefonas",
        "email": "El. paštas", "date": "Data", "loadingTime": "Время загрузки", "deliveryTime": "Время доставки", "pickupLift": "Liftas paėmime",
        "deliveryLift": "Liftas pristatyme", "tariff": "Tarifas", "details": "Pastabos",
        "createdAt": "Gauta", "language": "Svetainės kalba"
    }
    return "\n".join(f"{labels.get(key, key)}: {value}" for key, value in order.items() if key not in ("id", "consent"))

def send_email(order):
    """Sends an order email only after SMTP settings are configured."""
    host, recipient = os.getenv("SMTP_HOST"), os.getenv("ORDER_RECIPIENT")
    if not host or not recipient:
        return {"sent": False, "reason": "email_not_configured"}
    message = EmailMessage()
    message["Subject"] = f"Naujas GruZExpert užsakymas – {order['name']}"
    message["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "orders@localhost"))
    message["To"] = recipient
    message.set_content(order_text(order))
    port = int(os.getenv("SMTP_PORT", "465"))
    try:
        if os.getenv("SMTP_USE_TLS", "false").lower() == "true":
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls(context=ssl.create_default_context())
                if os.getenv("SMTP_USER"):
                    server.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
                server.send_message(message)
        else:
            with smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context()) as server:
                if os.getenv("SMTP_USER"):
                    server.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
                server.send_message(message)
        return {"sent": True}
    except Exception as error:
        print(f"Email was not sent: {error}")
        return {"sent": False, "reason": "email_failed"}

def send_sms(recipient, text):
    """Sends an SMS through Twilio; credentials are read only from the private .env file."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    sender = os.getenv("TWILIO_FROM")
    if not account_sid or not auth_token or not sender or not recipient:
        return {"sent": False, "reason": "sms_not_configured"}
    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    body = urlencode({"From": sender, "To": recipient, "Body": text[:1500]}).encode("utf-8")
    request = Request(endpoint, data=body, method="POST")
    token = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(request, timeout=20) as response:
            if response.status not in (200, 201):
                return {"sent": False, "reason": "sms_failed"}
        return {"sent": True}
    except Exception as error:
        print(f"SMS was not sent: {error}")
        return {"sent": False, "reason": "sms_failed"}
def send_telegram(order):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return {"sent": False, "error": "telegram_not_configured"}

    text = (
        "🚚 НОВА ЗАЯВКА GRUZEXPERT\n\n"
        f"👤 Ім'я: {order.get('name', '—')}\n"
        f"📞 Телефон: {order.get('phone', '—')}\n"
        f"📧 Email: {order.get('email', '—')}\n\n"
        f"📍 Звідки: {order.get('from', '—')}\n"
        f"📍 Куди: {order.get('to', '—')}\n"
        f"💰 Тариф: {order.get('tariff', '—')}\n"
        f"🏠 Ліфт при завантаженні: {order.get('pickupLift', '—')}\n"
        f"🏠 Ліфт при доставці: {order.get('deliveryLift', '—')}\n"
        f"📅 Дата: {order.get('date', '—')}\n"
        f"⏰ Время загрузки: {order.get('loadingTime', '—')}\n"
        f"⏰ Время доставки: {order.get('deliveryTime', '—')}\n"
        f"📝 Примітки: {order.get('details', '—')}"
    )

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": text
        }).encode("utf-8")

        request = Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))

        if result.get("ok"):
            return {"sent": True}

        return {"sent": False, "error": str(result)}

    except Exception as e:
        return {"sent": False, "error": str(e)}


def send_notifications(order):
    results = {
        "email": send_email(order),
        "telegram": send_telegram(order),
    }

    return results

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def json_response(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        origin = self.headers.get("Origin", "")
        if origin in FRONTEND_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def is_admin(self):
        return bool(ADMIN_KEY) and secrets.compare_digest(self.headers.get("X-Admin-Key", ""), ADMIN_KEY)

    def request_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if size <= 0 or size > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(size))
        except json.JSONDecodeError:
            return None

    def create_order(self, order):
        if not isinstance(order, dict) or any(not str(order.get(field, "")).strip() for field in REQUIRED_FIELDS):
            return self.json_response(HTTPStatus.BAD_REQUEST, {"error": "Please complete required fields"})
        order = {key: str(value).strip()[:1000] for key, value in order.items() if isinstance(key, str)}
        order["id"] = secrets.token_urlsafe(10)
        order["createdAt"] = datetime.now(timezone.utc).isoformat()
        orders = read_orders(); orders.append(order); write_orders(orders)
        notifications = send_notifications(order)
        delivery_complete = all(item["sent"] for item in notifications.values())
        status = HTTPStatus.CREATED if delivery_complete else HTTPStatus.ACCEPTED
        return self.json_response(status, {"ok": True, "id": order["id"], "notifications": notifications})

    def create_review(self, review):
        required = ("name", "rating", "text")
        if not isinstance(review, dict) or any(not str(review.get(field, "")).strip() for field in required):
            return self.json_response(HTTPStatus.BAD_REQUEST, {"error": "Please complete required fields"})
        if str(review["rating"]) not in ("1", "2", "3", "4", "5"):
            return self.json_response(HTTPStatus.BAD_REQUEST, {"error": "Invalid rating"})
        item = {
            "id": secrets.token_urlsafe(10),
            "name": str(review["name"]).strip()[:80],
            "rating": str(review["rating"]),
            "text": str(review["text"]).strip()[:1000],
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
        records = read_reviews(); records.insert(0, item); write_reviews(records)
        return self.json_response(HTTPStatus.CREATED, {"ok": True, "id": item["id"]})

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        origin = self.headers.get("Origin", "")
        if origin in FRONTEND_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.request_json()
        if body is None:
            return self.json_response(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON or request size"})
        if path == "/api/orders":
            return self.create_order(body)
        if path == "/api/reviews":
            return self.create_review(body)
        return self.send_error(HTTPStatus.NOT_FOUND)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/orders":
            if not self.is_admin():
                return self.json_response(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
            return self.json_response(HTTPStatus.OK, read_orders())
        if path == "/api/reviews":
            public_reviews = [{"id": item.get("id"), "name": item.get("name"), "rating": item.get("rating"), "text": item.get("text"), "createdAt": item.get("createdAt")} for item in read_reviews()]
            return self.json_response(HTTPStatus.OK, public_reviews)
        return super().do_GET()

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not self.is_admin():
            return self.json_response(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
        if path.startswith("/api/orders/"):
            records, write, record_id = read_orders(), write_orders, path.removeprefix("/api/orders/")
        elif path.startswith("/api/reviews/"):
            records, write, record_id = read_reviews(), write_reviews, path.removeprefix("/api/reviews/")
        else:
            return self.json_response(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        remaining = [record for record in records if record.get("id") != record_id]
        if not record_id or len(remaining) == len(records):
            return self.json_response(HTTPStatus.NOT_FOUND, {"error": "Record not found"})
        write(remaining)
        return self.json_response(HTTPStatus.OK, {"ok": True})

if __name__ == "__main__":
    if not ADMIN_KEY:
        print("WARNING: set GRUZEXPERT_ADMIN_KEY before placing the site online; admin access is disabled.")
    port = int(os.getenv("PORT", "8000"))
    ensure_database()
    print(f"GruZExpert is running on 0.0.0.0:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

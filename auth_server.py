from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import http.cookies
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
SESSION_IDLE_SECONDS = 5 * 60
SESSION_MAX_SECONDS = 30 * 24 * 60 * 60
PASSWORD_ITERATIONS = 310_000
MAX_REQUEST_BYTES = 16_384
PUBLIC_PATHS = {"/login", "/logo.png"}
PUBLIC_API_PATHS = {
    "/api/session",
    "/api/setup-status",
    "/api/setup",
    "/api/login",
    "/api/logout",
}
ALLOWED_EXTENSIONS = {
    ".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg",
    ".ico", ".woff", ".woff2",
}

LOGIN_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Sign in | Sahu Jewellery</title>
  <style>
    :root { font-family: Georgia, 'Times New Roman', serif; color: #24231f; background: #f3f1ea; }
    * { box-sizing: border-box; }
    body { min-height: 100vh; margin: 0; display: grid; place-items: center; padding: 24px; background: radial-gradient(ellipse at 12% 18%, #fffdf6 0, transparent 34%), linear-gradient(135deg, #f3f1ea, #e8e5dc); }
    main { width: min(100%, 430px); padding: 38px; background: #fffefa; border: 1px solid #ded9ca; box-shadow: 0 22px 65px #302b2018; animation: arrive .35s ease-out both; }
    .brand { display: flex; align-items: center; gap: 14px; padding-bottom: 25px; border-bottom: 1px solid #e8e3d6; }
    .brand img { width: 52px; height: 52px; object-fit: contain; }
    h1 { margin: 0; font-size: 21px; font-weight: 600; }
    .brand p { margin: 4px 0 0; color: #777166; font: 13px/1.4 Arial, sans-serif; }
    .eyebrow { margin: 27px 0 8px; color: #88733c; font: 700 11px/1.2 Arial, sans-serif; text-transform: uppercase; }
    h2 { margin: 0 0 22px; font-size: 29px; font-weight: 500; }
    label { display: block; margin: 16px 0 7px; color: #4a473f; font: 13px Arial, sans-serif; }
    input { width: 100%; min-height: 46px; padding: 10px 12px; border: 1px solid #d6d1c5; border-radius: 2px; background: #fff; color: #24231f; font: 15px Arial, sans-serif; }
    input:focus { outline: 2px solid #c3a45b; outline-offset: 1px; }
    button { width: 100%; min-height: 47px; margin-top: 23px; border: 0; border-radius: 2px; background: #282821; color: #fffdf6; cursor: pointer; font: 600 14px Arial, sans-serif; }
    button:hover { background: #454332; }
    button:disabled { opacity: .6; cursor: wait; }
    #message { min-height: 20px; margin: 13px 0 0; color: #9c302a; font: 13px/1.45 Arial, sans-serif; }
    .hidden { display: none; }
    @keyframes arrive { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
    @media (max-width: 480px) { main { padding: 27px 23px; } }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .01ms !important; } }
  </style>
</head>
<body>
  <main>
    <header class="brand">
      <img src="/logo.png" alt="">
      <div><h1>Sahu Jewellery</h1><p>Nilagiri, Balasore</p></div>
    </header>
    <p class="eyebrow">Jewellery Billing</p>
    <h2 id="heading">Sign in</h2>
    <form id="authForm" novalidate>
      <div id="setupCodeField" class="hidden">
        <label for="setupCode">One-time setup code</label>
        <input id="setupCode" name="setupCode" autocomplete="one-time-code">
      </div>
      <label for="username">Username</label>
      <input id="username" name="username" autocomplete="username" required>
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <p id="passwordHint" class="hidden" style="margin:7px 0 0;color:#777166;font:12px/1.4 Arial,sans-serif">Use at least 12 characters for the first admin password.</p>
      <button id="submitButton" type="submit">Sign in</button>
      <p id="message" role="alert" aria-live="polite"></p>
    </form>
  </main>
  <script>
    const form = document.querySelector('#authForm');
    const heading = document.querySelector('#heading');
    const setupCodeField = document.querySelector('#setupCodeField');
    const passwordHint = document.querySelector('#passwordHint');
    const password = document.querySelector('#password');
    const button = document.querySelector('#submitButton');
    const message = document.querySelector('#message');
    let needsSetup = false;

    async function initialize() {
      const [setupResponse, sessionResponse] = await Promise.all([
        fetch('/api/setup-status'), fetch('/api/session')
      ]);
      const setup = await setupResponse.json();
      const session = await sessionResponse.json();
    if (session.authenticated) { location.replace('/wordCustomer.html'); return; }
      needsSetup = !setup.configured;
      if (needsSetup) {
        heading.textContent = 'Create admin account';
        setupCodeField.classList.remove('hidden');
        passwordHint.classList.remove('hidden');
        password.autocomplete = 'new-password';
        button.textContent = 'Create account';
      }
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      message.textContent = '';
      button.disabled = true;
      try {
        const body = needsSetup
          ? { setupCode: form.setupCode.value, username: form.username.value, password: password.value }
          : { username: form.username.value, password: password.value };
        const response = await fetch(needsSetup ? '/api/setup' : '/api/login', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Unable to sign in.');
        location.replace('/wordCustomer.html');
      } catch (error) {
        message.textContent = error.message || 'The server could not be reached.';
      } finally {
        button.disabled = false;
      }
    });

    initialize().catch(() => { message.textContent = 'Cannot reach the authentication server.'; });
  </script>
</body>
</html>"""


class AuthStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS admin_user ("
                "id INTEGER PRIMARY KEY CHECK (id = 1), username TEXT NOT NULL, "
                "salt BLOB NOT NULL, password_hash BLOB NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS auth_session ("
                "token_hash BLOB PRIMARY KEY, username TEXT NOT NULL, "
                "idle_expires_at REAL NOT NULL, absolute_expires_at REAL NOT NULL)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def is_configured(self) -> bool:
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM admin_user WHERE id = 1").fetchone() is not None

    def create_admin(self, username: str, password: str) -> bool:
        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO admin_user (id, username, salt, password_hash) VALUES (1, ?, ?, ?)",
                    (username, salt, password_hash),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def verify_admin(self, username: str, password: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT username, salt, password_hash FROM admin_user WHERE id = 1"
            ).fetchone()
        if row is None:
            return False
        stored_username, salt, password_hash = row
        candidate_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
        )
        return hmac.compare_digest(stored_username.encode("utf-8"), username.encode("utf-8")) and hmac.compare_digest(
            password_hash, candidate_hash
        )

    def create_session(self, token: str, username: str) -> None:
        token_hash = hashlib.sha256(token.encode("ascii")).digest()
        now = time.time()
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_session WHERE idle_expires_at <= ?", (now,))
            connection.execute(
                "INSERT INTO auth_session "
                "(token_hash, username, idle_expires_at, absolute_expires_at) VALUES (?, ?, ?, ?)",
                (token_hash, username, now + SESSION_IDLE_SECONDS, now + SESSION_MAX_SECONDS),
            )

    def get_session_user(self, token: str) -> str | None:
        token_hash = hashlib.sha256(token.encode("ascii")).digest()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT username, idle_expires_at, absolute_expires_at "
                "FROM auth_session WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            username, idle_expires_at, absolute_expires_at = row
            now = time.time()
            if idle_expires_at <= now or absolute_expires_at <= now:
                connection.execute("DELETE FROM auth_session WHERE token_hash = ?", (token_hash,))
                return None
            connection.execute(
                "UPDATE auth_session SET idle_expires_at = ? WHERE token_hash = ?",
                (min(now + SESSION_IDLE_SECONDS, absolute_expires_at), token_hash),
            )
            return username

    def delete_session(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode("ascii")).digest()
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_session WHERE token_hash = ?", (token_hash,))


class AuthHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], store: AuthStore,
                 root: Path, setup_code: str, secure_cookie: bool) -> None:
        super().__init__(address, handler)
        self.store = store
        self.root = root.resolve()
        self.setup_code = setup_code
        self.secure_cookie = secure_cookie


class AuthRequestHandler(BaseHTTPRequestHandler):
    server: AuthHTTPServer

    def do_GET(self) -> None:
        path = self._path()
        if path == "/login":
            self._send_bytes(HTTPStatus.OK, LOGIN_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/session":
            username = self._session_user()
            self._send_json(HTTPStatus.OK, {"authenticated": username is not None, "username": username})
            return
        if path == "/api/setup-status":
            self._send_json(HTTPStatus.OK, {"configured": self.server.store.is_configured()})
            return
        if not self._session_user() and path not in PUBLIC_PATHS:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/login")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self._serve_file(path)

    def do_POST(self) -> None:
        path = self._path()
        if path not in PUBLIC_API_PATHS:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        if not self._is_same_origin():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Request origin rejected"})
            return
        payload = self._read_json()
        if payload is None:
            return

        if path == "/api/setup":
            self._setup(payload)
        elif path == "/api/login":
            self._login(payload)
        elif path == "/api/logout":
            self._logout()
        else:
            self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Method not allowed"})

    def do_HEAD(self) -> None:
        path = self._path()
        if path not in PUBLIC_PATHS and not self._session_user():
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.end_headers()
            return
        self._serve_file(path, head_only=True)

    def _setup(self, payload: dict[str, object]) -> None:
        if self.server.store.is_configured():
            self._send_json(HTTPStatus.CONFLICT, {"error": "An admin account already exists"})
            return
        setup_code = payload.get("setupCode")
        username = payload.get("username")
        password = payload.get("password")
        if not isinstance(setup_code, str) or not hmac.compare_digest(setup_code, self.server.setup_code):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Invalid setup code"})
            return
        if not isinstance(username, str) or not 3 <= len(username.strip()) <= 64:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Username must be 3 to 64 characters"})
            return
        if not isinstance(password, str) or len(password) < 12:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Password must be at least 12 characters"})
            return
        if not self.server.store.create_admin(username.strip(), password):
            self._send_json(HTTPStatus.CONFLICT, {"error": "An admin account already exists"})
            return
        self.server.setup_code = ""
        self._create_session(username.strip())

    def _login(self, payload: dict[str, object]) -> None:
        username = payload.get("username")
        password = payload.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Enter your username and password"})
            return
        if not self.server.store.verify_admin(username.strip(), password):
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Incorrect username or password"})
            return
        self._create_session(username.strip())

    def _create_session(self, username: str) -> None:
        token = secrets.token_urlsafe(32)
        self.server.store.create_session(token, username)
        cookie = f"session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_MAX_SECONDS}"
        if self.server.secure_cookie:
            cookie += "; Secure"
        self._send_json(HTTPStatus.OK, {"authenticated": True, "username": username},
                        extra_headers={"Set-Cookie": cookie})

    def _logout(self) -> None:
        token = self._cookie_value("session")
        if token:
            self.server.store.delete_session(token)
        cookie = "session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
        if self.server.secure_cookie:
            cookie += "; Secure"
        self._send_json(HTTPStatus.OK, {"authenticated": False}, extra_headers={"Set-Cookie": cookie})

    def _session_user(self) -> str | None:
        token = self._cookie_value("session")
        if not token:
            return None
        return self.server.store.get_session_user(token)

    def _cookie_value(self, key: str) -> str | None:
        raw_cookie = self.headers.get("Cookie")
        if not raw_cookie:
            return None
        parsed = http.cookies.SimpleCookie()
        try:
            parsed.load(raw_cookie)
        except http.cookies.CookieError:
            return None
        morsel = parsed.get(key)
        return morsel.value if morsel else None

    def _is_same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return False
        parsed = urlsplit(origin)
        return parsed.scheme in {"http", "https"} and parsed.netloc == self.headers.get("Host")

    def _read_json(self) -> dict[str, object] | None:
        content_type = self.headers.get_content_type()
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if content_type != "application/json" or length <= 0 or length > MAX_REQUEST_BYTES:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid request"})
            return None
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid request"})
            return None
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid request"})
            return None
        return payload

    def _path(self) -> str:
        return unquote(urlsplit(self.path).path)

    def _serve_file(self, url_path: str, head_only: bool = False) -> None:
        relative_path = "index.html" if url_path == "/" else url_path.lstrip("/")
        parts = Path(relative_path).parts
        if not parts or any(part.startswith(".") for part in parts):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        file_path = (self.server.root / relative_path).resolve()
        if self.server.root not in file_path.parents or file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            content = file_path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type, _ = mimetypes.guess_type(file_path.name)
        content_type = content_type or "application/octet-stream"
        if content_type == "text/html":
            username = html.escape(self._session_user() or "")
            toolbar = (
                '<div id="authToolbar"><span>Signed in as ' + username + '</span>'
                '<button type="button" id="authLogout">Sign out</button></div>'
                '<style>#authToolbar{position:sticky;top:0;z-index:2000;display:flex;justify-content:flex-end;'
                'align-items:center;gap:12px;padding:8px 16px;background:#282821;color:#fffdf6;'
                'font:13px Arial,sans-serif}#authToolbar button{border:1px solid #c3a45b;border-radius:2px;'
                'padding:5px 10px;background:transparent;color:inherit;cursor:pointer}'
                '@media print{#authToolbar{display:none!important}}</style>'
                '<script>document.getElementById("authLogout").addEventListener("click",async()=>{'
                'await fetch("/api/logout",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});'
                'location.replace("/login")});'
                'let inactivityTimer,lastSessionCheck=0;'
                'const trackActivity=()=>{clearTimeout(inactivityTimer);'
                'inactivityTimer=setTimeout(()=>location.replace("/login"),300000);'
                'const now=Date.now();if(now-lastSessionCheck<60000)return;lastSessionCheck=now;'
                'fetch("/api/session",{cache:"no-store"}).then(r=>r.json()).then(s=>{'
                'if(!s.authenticated)location.replace("/login")}).catch(()=>{});};'
                '["pointerdown","keydown","touchstart"].forEach(e=>document.addEventListener(e,trackActivity,{passive:true}));'
                'trackActivity()</script>'
            ).encode("utf-8")
            body_opening = re.search(rb"<body\b[^>]*>", content, re.IGNORECASE)
            if body_opening:
                insert_at = body_opening.end()
                content = content[:insert_at] + toolbar + content[insert_at:]
        if content_type.startswith("text/") or content_type in {"application/javascript", "image/svg+xml"}:
            content_type += "; charset=utf-8"
        self._send_bytes(HTTPStatus.OK, content, content_type, head_only=head_only)

    def _send_json(self, status: HTTPStatus, body: dict[str, object],
                   extra_headers: dict[str, str] | None = None) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self._send_bytes(status, encoded, "application/json; charset=utf-8", extra_headers=extra_headers)

    def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str,
                    head_only: bool = False, extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        super().log_message(format, *args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the jewellery billing pages behind login.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost only)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    parser.add_argument("--data-dir", type=Path, default=ROOT, help="Directory for the SQLite auth database")
    args = parser.parse_args()

    database_path = args.data_dir.resolve() / ".jewellery-auth.sqlite3"
    store = AuthStore(database_path)
    setup_code = ""
    if not store.is_configured():
        setup_code = secrets.token_urlsafe(18)
        print("First-run setup code (enter this on the login page):", setup_code, flush=True)

    server = AuthHTTPServer(
        (args.host, args.port), AuthRequestHandler, store, ROOT, setup_code,
        secure_cookie=os.environ.get("AUTH_COOKIE_SECURE", "0") == "1",
    )
    print(f"Serving Sahu Jewellery at http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping authentication server", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

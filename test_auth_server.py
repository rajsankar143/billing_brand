import http.cookiejar
import hashlib
import json
import secrets
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

from auth_server import (
    DEFAULT_BRAND_ADDRESS,
    DEFAULT_BRAND_NAME,
    AuthHTTPServer,
    AuthRequestHandler,
    AuthStore,
    load_auth_config,
)


ROOT = Path(__file__).resolve().parent


class AuthenticationServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = AuthStore(Path(self.temp_dir.name) / "auth.sqlite3")
        self.server = AuthHTTPServer(
            ("127.0.0.1", 0), AuthRequestHandler, self.store, ROOT, "test-setup-code", False
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def post_json(self, path: str, payload: dict[str, str]):
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": self.base_url,
            },
            method="POST",
        )
        return self.opener.open(request)

    def test_session_persists_after_store_reopen_and_expires(self) -> None:
        token = secrets.token_urlsafe(32)
        self.store.create_session(token, "billing-admin")

        reopened_store = AuthStore(self.store.database_path)
        self.assertEqual(reopened_store.get_session_user(token), "billing-admin")

        expired_token = secrets.token_urlsafe(32)
        self.store.create_session(expired_token, "billing-admin")
        expired_hash = hashlib.sha256(expired_token.encode("ascii")).digest()
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE auth_session SET idle_expires_at = ? WHERE token_hash = ?",
                (time.time() - 1, expired_hash),
            )
        self.assertIsNone(reopened_store.get_session_user(expired_token))

        reopened_store.delete_session(token)
        self.assertIsNone(self.store.get_session_user(token))

    def test_optional_brand_settings_default_and_persist(self) -> None:
        self.store.create_admin("billing-admin", "long-enough-test-password")
        with self.post_json(
            "/api/login",
            {"username": "billing-admin", "password": "long-enough-test-password"},
        ):
            pass

        with self.opener.open(self.base_url + "/api/brand-settings") as response:
            self.assertEqual(json.load(response), {
                "name": DEFAULT_BRAND_NAME,
                "address": DEFAULT_BRAND_ADDRESS,
            })

        with self.post_json(
            "/api/brand-settings",
            {"name": "Gem House", "address": "12 Main Road"},
        ) as response:
            self.assertEqual(json.load(response), {
                "name": "Gem House",
                "address": "12 Main Road",
            })

        with self.post_json("/api/brand-settings", {"name": "", "address": ""}) as response:
            self.assertEqual(json.load(response), {
                "name": DEFAULT_BRAND_NAME,
                "address": DEFAULT_BRAND_ADDRESS,
            })

    def test_login_events_are_logged_without_passwords(self) -> None:
        username = "billing-admin"
        password = "long-enough-test-password"
        rejected_password = "incorrect-password"
        self.store.create_admin(username, password)

        with self.assertLogs("sahu_jewellery.auth", level="INFO") as captured:
            with self.assertRaises(urllib.error.HTTPError):
                self.post_json(
                    "/api/login",
                    {"username": username, "password": rejected_password},
                )
            with self.post_json(
                "/api/login",
                {"username": username, "password": password},
            ) as response:
                self.assertEqual(response.status, 200)

        output = "\n".join(captured.output)
        self.assertIn("auth.login.failed", output)
        self.assertIn("auth.login.succeeded", output)
        self.assertNotIn(password, output)
        self.assertNotIn(rejected_password, output)

    def test_setup_login_protected_page_and_logout(self) -> None:
        with self.opener.open(self.base_url + "/") as response:
            self.assertTrue(response.url.endswith("/login"))
            login_page = response.read()
            self.assertIn(b"Sign in", login_page)
            self.assertIn(b"location.replace('/wordCustomer.html')", login_page)
            self.assertIn(b"const secureLogin", login_page)
            self.assertIn(b"session cookie was not retained", login_page)

        setup_payload = {
            "setupCode": "test-setup-code",
            "username": "billing-admin",
            "password": "long-enough-test-password",
        }
        with self.post_json("/api/setup", setup_payload) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("session=", response.headers["Set-Cookie"])
        self.assertTrue(self.store.is_configured())

        with closing(sqlite3.connect(self.store.database_path)) as connection:
            stored_password_hash = connection.execute(
                "SELECT password_hash FROM admin_user WHERE id = 1"
            ).fetchone()[0]
        self.assertNotEqual(stored_password_hash, setup_payload["password"].encode("utf-8"))

        with self.assertRaises(urllib.error.HTTPError) as invalid_login:
            self.post_json(
                "/api/login",
                {"username": "billing-admin", "password": "incorrect-password"},
            )
        self.assertEqual(invalid_login.exception.code, 401)

        with self.post_json(
            "/api/login",
            {"username": "billing-admin", "password": setup_payload["password"]},
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("session=", response.headers["Set-Cookie"])

        with self.opener.open(self.base_url + "/wordCustomer.html") as response:
            receipt_page = response.read()
            self.assertEqual(response.status, 200)
            self.assertIn(b'id="invoiceBody"', receipt_page)
            self.assertIn(b"inactivityTimer", receipt_page)

        with self.opener.open(self.base_url + "/wordCustomer.html") as response:
            self.assertEqual(response.status, 200)

        with self.post_json("/api/logout", {}) as response:
            self.assertEqual(response.status, 200)
        with self.opener.open(self.base_url + "/") as response:
            self.assertTrue(response.url.endswith("/login"))

    def test_config_credentials_replace_admin_and_revoke_sessions(self) -> None:
        self.store.create_admin("previous-admin", "previous-admin-password")
        token = secrets.token_urlsafe(32)
        self.store.create_session(token, "previous-admin")
        config_path = Path(self.temp_dir.name) / "auth_config.json"
        config_path.write_text(
            json.dumps({"username": "fresh-admin", "password": "fresh-admin-password"}),
            encoding="utf-8",
        )

        credentials = load_auth_config(config_path)
        self.assertEqual(credentials, ("fresh-admin", "fresh-admin-password"))
        self.store.set_admin_credentials(*credentials)

        self.assertTrue(self.store.verify_admin("fresh-admin", "fresh-admin-password"))
        self.assertFalse(self.store.verify_admin("previous-admin", "previous-admin-password"))
        self.assertIsNone(self.store.get_session_user(token))
        with self.post_json(
            "/api/login",
            {"username": "fresh-admin", "password": "fresh-admin-password"},
        ) as response:
            self.assertEqual(response.status, 200)

    def test_login_throttle_blocks_after_five_failures(self) -> None:
        self.store.create_admin("billing-admin", "long-enough-test-password")
        for _ in range(5):
            with self.assertRaises(urllib.error.HTTPError) as invalid_login:
                self.post_json(
                    "/api/login",
                    {"username": "billing-admin", "password": "wrong-password"},
                )
            self.assertEqual(invalid_login.exception.code, 401)

        with self.assertRaises(urllib.error.HTTPError) as blocked_login:
            self.post_json(
                "/api/login",
                {"username": "billing-admin", "password": "long-enough-test-password"},
            )
        self.assertEqual(blocked_login.exception.code, 429)


if __name__ == "__main__":
    unittest.main()

import http.cookiejar
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

from auth_server import AuthHTTPServer, AuthRequestHandler, AuthStore


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

    def test_setup_login_protected_page_and_logout(self) -> None:
        with self.opener.open(self.base_url + "/") as response:
            self.assertTrue(response.url.endswith("/login"))
            login_page = response.read()
            self.assertIn(b"Sign in", login_page)
            self.assertEqual(login_page.count(b"location.replace('/wordCustomer.html')"), 2)

        setup_payload = {
            "setupCode": "test-setup-code",
            "username": "billing-admin",
            "password": "long-enough-test-password",
        }
        with self.post_json("/api/setup", setup_payload) as response:
            self.assertEqual(response.status, 200)
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

        with self.opener.open(self.base_url + "/") as response:
            page = response.read()
            self.assertEqual(response.status, 200)
            self.assertIn(b"id=\"authLogout\"", page)
            self.assertIn(b"Jewellery Billing", page)
            self.assertLess(page.index(b"id=\"authLogout\""), page.index(b"class=\"container\""))
            self.assertIn("https://code.jquery.com", response.headers["Content-Security-Policy"])

        with self.opener.open(self.base_url + "/wordCustomer.html") as response:
            receipt_page = response.read()
            self.assertEqual(response.status, 200)
            self.assertIn(b"p_rateLabel", receipt_page)

        with self.post_json("/api/logout", {}) as response:
            self.assertEqual(response.status, 200)
        with self.opener.open(self.base_url + "/") as response:
            self.assertTrue(response.url.endswith("/login"))


if __name__ == "__main__":
    unittest.main()

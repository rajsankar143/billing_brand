# Sahu Jewellery Billing Server

The standalone billing pages are served by a Python authentication server. Do not open the HTML files directly; use the server URL so access checks and login sessions are enforced.

## Run locally

From this folder, run:

```powershell
py -3 auth_server.py
```

Open `http://127.0.0.1:8000/`. On first startup, the terminal prints a one-time setup code. Enter it on the sign-in page to create the first admin account. Choose a password of at least 12 characters. The account is stored in `.jewellery-auth.sqlite3`; the password is stored as a salted PBKDF2 hash.

After setup, sign in with that admin account. Authenticated pages include a **Sign out** control. Sessions are stored in SQLite and survive service restarts. Authenticated requests extend the five-minute idle timeout, with a 30-day maximum lifetime. Signing out revokes the current session.

## Network deployment

The default bind address is `127.0.0.1`, which only allows local access. For a private network, bind to a specific trusted interface, for example:

```powershell
py -3 auth_server.py --host 0.0.0.0 --port 8000
```

Do not expose the built-in HTTP server directly to the public internet. Put it behind a TLS-enabled reverse proxy, firewall it to trusted users, and set `AUTH_COOKIE_SECURE=1` for HTTPS deployments so browsers only send the session cookie over HTTPS.

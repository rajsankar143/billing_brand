# Sahu Jewellery Billing Server

The standalone billing pages are served by a Python authentication server. Do not open the HTML files directly; use the server URL so access checks and login sessions are enforced.

## Run locally

From this folder, run:

```powershell
py -3 auth_server.py
```

Open `http://127.0.0.1:8000/`. On first startup, the terminal prints a one-time setup code. Enter it on the sign-in page to create the first admin account. Choose a password of at least 12 characters. The account is stored in `.jewellery-auth.sqlite3`; the password is stored as a salted PBKDF2 hash.

For local development, set `username` and `password` in `auth_config.json` and restart the server. The configured credentials become the single admin account, including when an account already exists; changing them revokes existing sessions. Keep this file local and do not commit it because it contains a plaintext password. If the file is absent or both values are empty, the one-time setup-code flow is used instead. `auth_config.example.json` is a blank template.

After setup, each successful setup or login returns a random, 60-second, single-use ticket for the `wordCustomer.html` response. Only the ticket hash is stored in SQLite. The ticket is consumed on first use and removed from the browser address bar. No new session cookie is issued. A browser-side inactivity timer returns to login after five minutes, but that timer is not server-side authorization after the HTML has been delivered. Use HTTPS for credential submission.

## Network deployment

The default bind address is `127.0.0.1`, which only allows local access. For a private network, bind to a specific trusted interface, for example:

```powershell
py -3 auth_server.py --host 0.0.0.0 --port 8000
```

Do not expose the built-in HTTP server directly to the public internet. Put it behind a TLS-enabled reverse proxy, firewall it to trusted users, and set `AUTH_COOKIE_SECURE=1` for HTTPS deployments so browsers only send the session cookie over HTTPS.

## AWS EC2 deployment

The EC2-generated `*.compute.amazonaws.com` hostname is not eligible for a publicly trusted certificate. For secure browser sign-in, use a domain you control and point its DNS A record to an Elastic IP assigned to the instance. Do not disable Secure cookies to make public HTTP login work.

The repository includes an Amazon Linux systemd unit at `deploy/aws/sahu-jewellery.service` and an Nginx reverse-proxy template at `deploy/aws/sahu-jewellery.conf`. Replace `/opt/billing_brand` if your app is installed elsewhere, and replace `billing.example.com` with your domain.

On the EC2 instance:

1. Allow inbound TCP ports `80` and `443` in the instance security group. Do not expose port `8000`.
2. Install the web/runtime packages:

	```bash
	sudo dnf install -y python3 nginx certbot python3-certbot-nginx
	```

3. Create a dedicated service account and persistent SQLite directory, then give the service account read access to the app files:

	```bash
	sudo useradd --system --no-create-home --shell /sbin/nologin billing
	sudo chown -R root:billing /opt/billing_brand
	sudo chmod -R g+rX,o-rwx /opt/billing_brand
	sudo install -d -o billing -g billing -m 750 /var/lib/sahu-jewellery
	```

4. Create the private credentials file. Replace the sample values with your chosen username and a password of at least 12 characters. The file is owned by root and readable only by root and the billing service group:

	```bash
	sudo install -d -o root -g billing -m 750 /etc/sahu-jewellery
	sudo install -o root -g billing -m 640 /dev/null /etc/sahu-jewellery/auth_config.json
	sudo nano /etc/sahu-jewellery/auth_config.json
	```

	Use this JSON structure:

	```json
	{
	  "username": "your-admin-name",
	  "password": "replace-with-a-long-unique-password"
	}
	```

	The service reads this file at startup, hashes the password into its SQLite database, and uses those credentials for login. Updating the file and restarting the service changes the admin credentials and revokes existing sessions. Never expose the file through Nginx or commit it to source control.

5. Install and start the service and Nginx configuration:

	```bash
	sudo cp deploy/aws/sahu-jewellery.service /etc/systemd/system/
	sudo cp deploy/aws/sahu-jewellery.conf /etc/nginx/conf.d/sahu-jewellery.conf
	sudo systemctl daemon-reload
	sudo systemctl enable --now sahu-jewellery nginx
	sudo nginx -t && sudo systemctl reload nginx
	```

6. After DNS resolves to the instance, obtain the certificate and configure HTTPS:

	```bash
	sudo certbot --nginx --redirect -d billing.example.com
	sudo nginx -t && sudo systemctl reload nginx
	```

7. Visit `https://billing.example.com/login` and sign in with the username and password from `/etc/sahu-jewellery/auth_config.json`. Do not enter credentials over HTTP.

To change the AWS admin credentials later, edit `/etc/sahu-jewellery/auth_config.json` and restart the service:

	```bash
	sudo systemctl restart sahu-jewellery
	```

For deployment checks, use a GET request (not `curl -I`, because `/login` is generated dynamically):

```bash
curl -sS -o /dev/null -w 'Login page: HTTP %{http_code}\n' https://billing.example.com/login
```

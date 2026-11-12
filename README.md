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

From Windows PowerShell, upload the app files and deployment templates to a temporary directory on the instance. Replace the key path and Elastic IP. This deliberately does not upload `auth_config.json`:

```powershell
$Key = "C:\path\to\your-key.pem"
$HostName = "ec2-user@YOUR_ELASTIC_IP"
ssh -i $Key $HostName "mkdir -p /tmp/sahu-jewellery"
$Files = @(
	".\auth_server.py",
	".\index.html",
	".\dashbord.html",
	".\silver.html",
	".\updatedReceipt.html",
	".\wordCustomer.html",
	".\logo.png",
	".\deploy\aws\sahu-jewellery.service",
	".\\deploy\\aws\\sahu-jewellery.conf",
	".\\deploy\\aws\\sahu-jewellery-cloudfront.conf"
)
scp -i $Key @Files "${HostName}:/tmp/sahu-jewellery/"
```

On the EC2 instance:

1. Allow inbound TCP ports `80` and `443` in the instance security group. Restrict SSH (`22`) to your IP. Do not expose port `8000`.
2. Install the web/runtime packages:

	```bash
	sudo dnf install -y python3 nginx certbot python3-certbot-nginx
	```

3. Install the uploaded app files and create a dedicated service account and persistent SQLite directory:

	```bash
	sudo useradd --system --no-create-home --shell /sbin/nologin billing
	sudo install -d -o root -g billing -m 750 /opt/billing_brand
	sudo cp /tmp/sahu-jewellery/*.html /tmp/sahu-jewellery/auth_server.py /tmp/sahu-jewellery/logo.png /opt/billing_brand/
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
	sudo cp /tmp/sahu-jewellery/sahu-jewellery.service /etc/systemd/system/
	sudo cp /tmp/sahu-jewellery/sahu-jewellery.conf /etc/nginx/conf.d/sahu-jewellery.conf
	sudo nano /etc/nginx/conf.d/sahu-jewellery.conf
	```

	Replace `billing.example.com` with your domain, then run:

	```bash
	sudo systemctl daemon-reload
	sudo systemctl enable --now sahu-jewellery nginx
	sudo nginx -t && sudo systemctl reload nginx
	```

6. Confirm your domain's DNS A record resolves to the Elastic IP, then obtain the certificate and configure HTTPS. Certbot updates Nginx to listen on `443` and redirect HTTP to HTTPS:

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

### HTTPS troubleshooting

If the HTTP login page loads but HTTPS reports `ERR_CONNECTION_REFUSED`, the TLS endpoint is not listening or inbound TCP `443` is blocked. Do not enter credentials over HTTP. The EC2 `*.compute.amazonaws.com` hostname is not eligible for a publicly trusted certificate; use a domain you control.

On the instance, check Nginx and the certificate:

```bash
sudo systemctl status nginx sahu-jewellery --no-pager
sudo nginx -t
sudo certbot certificates
sudo ss -lntp | grep -E ':(80|443)([[:space:]]|$)'
```

If there is no valid certificate for your domain, first verify its DNS A record points to the Elastic IP and that security group TCP `80` and `443` rules are active. Then run:

```bash
sudo certbot --nginx --redirect -d billing.example.com
sudo nginx -t && sudo systemctl reload nginx
```

Finally, test `https://billing.example.com/login`. The expected response is HTTP `200`.

### AWS browser access without a custom domain

To use a browser over trusted HTTPS without registering a domain, put CloudFront in front of this EC2 app. CloudFront provides an HTTPS `*.cloudfront.net` hostname. Keep the existing app authentication and `AUTH_COOKIE_SECURE=1`; do not turn off secure cookies or expose port `8000`.

1. In the EC2 security group, allow inbound TCP `80` for the CloudFront origin and restrict SSH (`22`) to your IP. The app itself must continue listening only on `127.0.0.1:8000`.
2. Connect to EC2 and generate an origin-only secret. Keep it private; you will enter the same value in CloudFront and Nginx:

	```bash
	openssl rand -hex 32
	```

3. In AWS Console, open **CloudFront** and create a distribution:
   - Origin domain: the EC2 public DNS hostname, without `http://` or a path.
   - Origin protocol: **HTTP only**, port `80`.
   - Add an origin custom header named `X-Origin-Verify` with the secret generated above.
   - Viewer protocol policy: **Redirect HTTP to HTTPS**.
   - Allowed methods: all methods (`GET`, `HEAD`, `OPTIONS`, `PUT`, `POST`, `PATCH`, `DELETE`).
   - Cache policy: **CachingDisabled**.
   - Origin request policy: **AllViewer**, so the browser `Host`, `Origin`, cookies, and request body reach the app correctly.
   - Leave the alternate domain name and custom certificate fields empty. Wait until the distribution status is **Deployed**, then copy its domain name, for example `d123example.cloudfront.net`.

4. If you did not upload it in the earlier PowerShell `scp` step, add `deploy/aws/sahu-jewellery-cloudfront.conf` to `$Files` and upload again. On EC2, install and edit it:

	```bash
	sudo install -m 644 /tmp/sahu-jewellery/sahu-jewellery-cloudfront.conf /etc/nginx/conf.d/sahu-jewellery-cloudfront.conf
	sudo nano /etc/nginx/conf.d/sahu-jewellery-cloudfront.conf
	```

	Replace `YOUR_DISTRIBUTION.cloudfront.net` with the distribution hostname and `REPLACE_WITH_ORIGIN_SECRET` with the exact secret entered in CloudFront. Save, then verify and reload Nginx:

	```bash
	sudo nginx -t && sudo systemctl reload nginx
	```

5. Open `https://YOUR_DISTRIBUTION.cloudfront.net/login`. Use the admin credentials already configured on EC2. HTTP should redirect to HTTPS, and direct origin requests without the private header should receive `403`.

Keep CloudFront caching disabled for every app path. Do not enable caching for HTML, API responses, or cookies, because those responses contain user-specific billing and session data. CloudFront usage may incur AWS charges.

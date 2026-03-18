# Deployment Guide

This app runs on a single AWS Lightsail instance with SQLite on disk.
Deployments are fully automated via GitHub Actions — merging to `main` runs tests
and, if they pass, deploys to the server automatically.

---

## Prerequisites

- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) installed and configured (`aws configure`)
- SSH client available locally
- The repo pushed to GitHub

---

## 1. Create the Lightsail Instance

Run these from your **local machine**:

```bash
# Create a Ubuntu 22.04 instance
aws lightsail create-instances \
  --instance-names tennis-league \
  --availability-zone us-east-1a \
  --blueprint-id ubuntu_22_04 \
  --bundle-id micro_3_0

# Wait until state is "running" (poll every 10s)
aws lightsail get-instance --instance-name tennis-league \
  --query 'instance.state.name'

# Open HTTP and HTTPS ports
aws lightsail open-instance-public-ports \
  --instance-name tennis-league \
  --port-info fromPort=80,toPort=80,protocol=TCP

aws lightsail open-instance-public-ports \
  --instance-name tennis-league \
  --port-info fromPort=443,toPort=443,protocol=TCP

# Allocate and attach a static IP so it doesn't change on reboot
aws lightsail allocate-static-ip --static-ip-name tennis-league-ip

aws lightsail attach-static-ip \
  --static-ip-name tennis-league-ip \
  --instance-name tennis-league

# Get the static IP address (you'll need this throughout)
aws lightsail get-static-ip --static-ip-name tennis-league-ip \
  --query 'staticIp.ipAddress' --output text
```

---

## 2. Get the SSH Key

Run from your **local machine**:

```bash
aws lightsail download-default-key-pair \
  --query 'privateKeyBase64' --output text \
  | base64 --decode > ~/.ssh/lightsail-tennis-league.pem

chmod 600 ~/.ssh/lightsail-tennis-league.pem
```

Test the connection:
```bash
ssh -i ~/.ssh/lightsail-tennis-league.pem ubuntu@YOUR_STATIC_IP
```

---

## 3. Enable Automatic Daily Snapshots

Run from your **local machine**:

```bash
aws lightsail enable-add-on \
  --resource-name tennis-league \
  --add-on-request 'addOnType=AutoSnapshot,autoSnapshotAddOnRequest={snapshotTimeOfDay=03:00}'
```

This takes a daily snapshot at 3am UTC and retains the last 7. Restoring means
spinning up a new instance from the snapshot in the Lightsail console.

---

## 4. Set Up the Server

SSH into the instance and run `deploy.sh`:

```bash
ssh -i ~/.ssh/lightsail-tennis-league.pem ubuntu@YOUR_STATIC_IP
```

On the server:

```bash
# Clone the repo (only needed the very first time)
git clone https://github.com/YOUR_ORG/YOUR_REPO.git tennis-scores-app
cd tennis-scores-app

# Run the setup script
./deploy.sh
```

The script requires a **real DNS domain name** pointed at the server's static IP — Let's Encrypt cannot issue certificates for bare IP addresses. Point an A record at the static IP before running the script.

The script will prompt for:
- **Domain name** — e.g. `tennis.example.com` (must resolve to this server)
- **Let's Encrypt email** — for certificate expiry notifications
- **GitHub repo URL** — used if the repo isn't already cloned
- **S3 backups** — optional; see § S3 Backups below

It then handles automatically:
- System package installation (including `certbot` and `python3-certbot-nginx`)
- Python venv and dependency installation
- `.env` generation (random `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`)
- Database migration and static file collection
- Gunicorn systemd service (enabled + started)
- Sudoers entry so the deploy workflow can restart gunicorn without a password
- Nginx site configuration
- Let's Encrypt TLS certificate via certbot (rewrites nginx config to HTTPS-only with HTTP → HTTPS redirect)
- Certbot auto-renewal systemd timer (enabled)

After the script finishes, create the admin user:

```bash
.venv/bin/python manage.py createsuperuser --settings=config.settings_production
```

---

## 5. S3 Backups (optional but recommended)

When `deploy.sh` asks about S3 backups, answer `y` and provide a globally unique
bucket name. The script will:

1. Create the S3 bucket
2. Add a 30-day lifecycle expiry rule
3. Install a daily cron at `/etc/cron.daily/backup-db` that snapshots the SQLite
   file and uploads it to the bucket

The AWS CLI on the instance must have permissions to write to that bucket. Attach
an IAM role to the instance or configure `aws configure` on the server.

---

## 6. Configure GitHub Actions Secrets

In the GitHub repo go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `LIGHTSAIL_HOST` | Your static IP address |
| `LIGHTSAIL_USER` | `ubuntu` |
| `LIGHTSAIL_SSH_KEY` | Full contents of `~/.ssh/lightsail-tennis-league.pem` |
| `APP_DIR` | `/home/ubuntu/tennis-scores-app` |

---

## CI/CD Pipeline

Two GitHub Actions workflows live in `.github/workflows/`:

### `ci.yml` — runs on every pull request to `main`

1. Installs Python 3.12 and dependencies
2. Runs the full test suite against an in-memory SQLite database
3. PR cannot be merged if this fails

### `deploy.yml` — runs on every push to `main` (i.e. after a PR merges)

1. **test job** — same as ci.yml; deploy is blocked if tests fail
2. **deploy job** (only runs if test passes):
   - SSHes into the Lightsail instance
   - `git pull origin main`
   - `pip install -r requirements.txt`
   - `python manage.py migrate`
   - `python manage.py collectstatic`
   - `sudo systemctl restart gunicorn`

The deploy job uses `appleboy/ssh-action` and the four `LIGHTSAIL_*` secrets above.

---

## Troubleshooting

### Log locations

| Source | How to read |
|--------|-------------|
| **Gunicorn** (Django app output, Python errors) | `sudo journalctl -u gunicorn -n 100 -f` |
| **Nginx access log** | `sudo tail -f /var/log/nginx/access.log` |
| **Nginx error log** (bad gateway, socket errors) | `sudo tail -f /var/log/nginx/error.log` |
| **Certbot** | `sudo journalctl -u certbot -n 50` or `/var/log/letsencrypt/letsencrypt.log` |
| **Cron / S3 backup** | `sudo journalctl -u cron -n 50` |

Django has no `LOGGING` configuration, so all application output (requests, errors, tracebacks) goes to gunicorn's stdout/stderr, which systemd captures in the journal.

### Reading the journal

`journalctl` is how you read logs for any systemd-managed service. Key flags:

```bash
sudo journalctl -u gunicorn -n 100    # last 100 lines
sudo journalctl -u gunicorn -f        # follow live output
sudo journalctl -u gunicorn -p err    # errors only
sudo journalctl -u gunicorn --since "2026-03-18 10:00"
```

Each line is formatted as `timestamp hostname service[pid]: message`. If a request returns a bad response, check gunicorn first (Django traceback will be there). If the request never reaches gunicorn, check the nginx error log (usually a socket permission problem).

### Common checks

```bash
# Is gunicorn running and did it start cleanly?
sudo systemctl status gunicorn

# Can nginx reach the socket? (permission denied = /home/ubuntu is not world-executable)
sudo -u www-data stat /home/ubuntu/tennis-scores-app/gunicorn.sock

# Fix socket permission issue
sudo chmod o+x /home/ubuntu

# Test nginx config before reloading
sudo nginx -t

# Check TLS certificate status
sudo certbot certificates
```

---

## Restoring from Backup

**From S3 (database only):**

```bash
sudo systemctl stop gunicorn
aws s3 cp s3://tennis-league-backups/tennis-db-YYYYMMDD.sqlite3 \
  /home/ubuntu/tennis-scores-app/db.sqlite3
sudo systemctl start gunicorn
```

**From Lightsail snapshot (full instance):**

1. Go to Lightsail console → Snapshots
2. Select the snapshot → Create new instance
3. Attach the static IP to the new instance
4. Add the new instance's SSH key to GitHub secrets if it differs

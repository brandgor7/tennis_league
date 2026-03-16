# Deployment Guide

This app runs on a single AWS Lightsail instance ($5/month) with SQLite on disk.
Deployments are fully automated via GitHub Actions — merging to `main` runs tests
and, if they pass, deploys to the server automatically.

---

## Prerequisites

- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) installed and configured (`aws configure`)
- SSH client available locally
- The repo pushed to GitHub

---

## 1. Create the Lightsail Instance

```bash
# Create a $5/month Ubuntu 22.04 instance
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

Lightsail uses its own key pair. Download it and lock down permissions:

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

```bash
aws lightsail enable-add-on \
  --resource-name tennis-league \
  --add-on-request 'addOnType=AutoSnapshot,autoSnapshotAddOnRequest={snapshotTimeOfDay=03:00}'
```

This takes a daily snapshot at 3am UTC and retains the last 7. Restoring means
spinning up a new instance from the snapshot in the Lightsail console.

---

## 4. Set Up the Server

SSH into the instance and run the following:

### System packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip git nginx
```

### Clone the repo

```bash
cd /home/ubuntu
git clone https://github.com/YOUR_ORG/YOUR_REPO.git tennis-scores-app
cd tennis-scores-app
```

### Python environment

```bash
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### Environment file

```bash
cp .env.example .env
```

Edit `.env` with production values:

```
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(50))">
DEBUG=False
ALLOWED_HOSTS=YOUR_STATIC_IP,yourdomain.com
```

### Initialise the app

```bash
.venv/bin/python manage.py migrate --settings=config.settings_production
.venv/bin/python manage.py collectstatic --noinput --settings=config.settings_production
.venv/bin/python manage.py createsuperuser --settings=config.settings_production
```

---

## 5. Configure Gunicorn

Create the systemd service:

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

Paste:

```ini
[Unit]
Description=Gunicorn for tennis-league
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/tennis-scores-app
ExecStart=/home/ubuntu/tennis-scores-app/.venv/bin/gunicorn \
    --workers 2 \
    --bind unix:/home/ubuntu/tennis-scores-app/gunicorn.sock \
    config.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn

# Verify it's running
sudo systemctl status gunicorn
```

Allow the deploy workflow to restart gunicorn without a password prompt:

```bash
echo "ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart gunicorn" \
  | sudo tee /etc/sudoers.d/gunicorn
```

---

## 6. Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/tennis-league
```

Paste:

```nginx
server {
    listen 80;
    server_name YOUR_STATIC_IP;

    location /static/ {
        alias /home/ubuntu/tennis-scores-app/staticfiles/;
    }

    location / {
        proxy_pass http://unix:/home/ubuntu/tennis-scores-app/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Enable the site and reload:

```bash
sudo ln -s /etc/nginx/sites-available/tennis-league /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 7. Set Up S3 Backups (optional but recommended)

```bash
# Create a bucket (replace with a globally unique name)
aws s3 mb s3://tennis-league-backups

# Set a lifecycle rule to delete backups older than 30 days
aws s3api put-bucket-lifecycle-configuration \
  --bucket tennis-league-backups \
  --lifecycle-configuration '{
    "Rules": [{
      "ID": "expire-old-backups",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "Expiration": {"Days": 30}
    }]
  }'
```

Create the daily backup cron:

```bash
sudo nano /etc/cron.daily/backup-db
```

Paste:

```bash
#!/bin/bash
set -e
BACKUP=/tmp/tennis-db-$(date +%Y%m%d).sqlite3
sqlite3 /home/ubuntu/tennis-scores-app/db.sqlite3 ".backup $BACKUP"
aws s3 cp "$BACKUP" s3://tennis-league-backups/
rm "$BACKUP"
```

```bash
sudo chmod +x /etc/cron.daily/backup-db
```

---

## 8. Configure GitHub Actions Secrets

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

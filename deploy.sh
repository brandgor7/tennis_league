#!/bin/bash
set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────
# Pass these as env vars or be prompted at runtime.
# Example: DOMAIN=tennis.example.com CERTBOT_EMAIL=you@example.com REPO_URL=https://github.com/org/repo.git S3_BUCKET=my-bucket ./deploy.sh
# NOTE: DOMAIN must be a real DNS name pointing to this server — Let's Encrypt cannot issue certs for bare IPs.

APP_DIR=/home/ubuntu/tennis-scores-app

# ─── Helpers ──────────────────────────────────────────────────────────────────
prompt() {
    local var="$1" msg="$2"
    if [ -z "${!var:-}" ]; then
        read -rp "$msg: " "$var"
    fi
}

# ─── Gather inputs ────────────────────────────────────────────────────────────
prompt DOMAIN          "Domain name pointing to this server (e.g. tennis.example.com)"
prompt CERTBOT_EMAIL   "Email for Let's Encrypt certificate notifications"
prompt REPO_URL        "GitHub repo URL (e.g. https://github.com/org/repo.git)"

# SERVER_NAME is the domain used in nginx and ALLOWED_HOSTS
SERVER_NAME="$DOMAIN"

read -rp "Enable S3 database backups? [y/N]: " ENABLE_S3
if [[ "${ENABLE_S3,,}" == "y" ]]; then
    prompt S3_BUCKET "S3 bucket name (must be globally unique, e.g. tennis-league-backups)"
fi

echo
echo "==> Domain      : $DOMAIN"
echo "==> Cert email  : $CERTBOT_EMAIL"
echo "==> Repo        : $REPO_URL"
echo "==> App dir     : $APP_DIR"
[[ "${ENABLE_S3,,}" == "y" ]] && echo "==> S3 bucket   : $S3_BUCKET"
echo

# ─── 1. System packages ───────────────────────────────────────────────────────
echo "==> Installing system packages..."
sudo apt update -qq && sudo apt upgrade -y -qq
sudo apt install -y python3.12 python3.12-venv python3-pip git nginx certbot python3-certbot-nginx unzip

# ─── 2. Clone repo ────────────────────────────────────────────────────────────
echo "==> Cloning repo..."
if [ -d "$APP_DIR" ]; then
    echo "    Directory already exists — pulling latest instead."
    git -C "$APP_DIR" pull origin main
else
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ─── 3. Python environment ────────────────────────────────────────────────────
echo "==> Setting up Python venv..."
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

# ─── 4. Environment file ──────────────────────────────────────────────────────
echo "==> Configuring .env..."
if [ ! -f .env ]; then
    cp .env.example .env
fi

SECRET_KEY=$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))")

# Write production values (overwrite existing keys if present)
sed_set() {
    local key="$1" val="$2"
    if grep -q "^${key}=" .env 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${val}|" .env
    else
        echo "${key}=${val}" >> .env
    fi
}

sed_set SECRET_KEY  "$SECRET_KEY"
sed_set DEBUG       "False"
sed_set ALLOWED_HOSTS "$SERVER_NAME"

echo "    .env written. Review it at $APP_DIR/.env if you need to add extra values."

# ─── 5. Initialise the app ────────────────────────────────────────────────────
echo "==> Running migrations and collectstatic..."
.venv/bin/python manage.py migrate --settings=config.settings_production
.venv/bin/python manage.py collectstatic --noinput --settings=config.settings_production

# ─── 6. Gunicorn systemd service ──────────────────────────────────────────────
echo "==> Creating gunicorn systemd service..."
sudo tee /etc/systemd/system/gunicorn.service > /dev/null <<EOF
[Unit]
Description=Gunicorn for tennis-league
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/gunicorn \\
    --workers 2 \\
    --bind unix:$APP_DIR/gunicorn.sock \\
    config.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl restart gunicorn

# www-data (nginx) needs execute on /home/ubuntu to reach the unix socket inside it.
sudo chmod o+x /home/ubuntu

echo "ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart gunicorn" \
    | sudo tee /etc/sudoers.d/gunicorn > /dev/null

echo "==> Gunicorn status:"
sudo systemctl status gunicorn --no-pager

# ─── 7. Nginx + TLS ───────────────────────────────────────────────────────────
echo "==> Configuring Nginx (initial HTTP config for ACME challenge)..."

# Write a minimal port-80 config so certbot can complete the ACME challenge.
# The certbot --nginx plugin will rewrite this file to add the HTTPS server block
# and a 301 redirect from port 80 to 443.
sudo tee /etc/nginx/sites-available/tennis-league > /dev/null <<EOF
server {
    listen 80;
    server_name $SERVER_NAME;

    location /static/ {
        alias $APP_DIR/staticfiles/;
    }

    location / {
        proxy_pass http://unix:$APP_DIR/gunicorn.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/tennis-league /etc/nginx/sites-enabled/tennis-league
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "==> Obtaining Let's Encrypt certificate for $DOMAIN..."
# --nginx        — uses and rewrites the existing nginx config
# --redirect     — adds a 301 HTTP→HTTPS redirect block
# --no-eff-email — skip the EFF mailing list prompt
sudo certbot --nginx \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "$CERTBOT_EMAIL" \
    --redirect \
    --no-eff-email

echo "==> Verifying auto-renewal timer..."
sudo systemctl is-enabled certbot.timer || sudo systemctl enable certbot.timer
sudo systemctl status certbot.timer --no-pager

# ─── 8. S3 backup cron (optional) ────────────────────────────────────────────
if [[ "${ENABLE_S3,,}" == "y" ]]; then
    echo "==> Creating S3 bucket and lifecycle rule..."
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    sudo ./aws/install
    aws s3 mb "s3://$S3_BUCKET"
    aws s3api put-bucket-lifecycle-configuration \
        --bucket "$S3_BUCKET" \
        --lifecycle-configuration '{
          "Rules": [{
            "ID": "expire-old-backups",
            "Status": "Enabled",
            "Filter": {"Prefix": ""},
            "Expiration": {"Days": 30}
          }]
        }'

    echo "==> Installing daily backup cron..."
    sudo tee /etc/cron.daily/backup-db > /dev/null <<EOF
#!/bin/bash
set -e
BACKUP=/tmp/tennis-db-\$(date +%Y%m%d).sqlite3
sqlite3 $APP_DIR/db.sqlite3 ".backup \$BACKUP"
aws s3 cp "\$BACKUP" s3://$S3_BUCKET/
rm "\$BACKUP"
EOF
    sudo chmod +x /etc/cron.daily/backup-db
fi

# ─── Done ─────────────────────────────────────────────────────────────────────
echo
echo "============================================================"
echo " Server setup complete."
echo " Next steps:"
echo "   1. Create an admin user:"
echo "      cd $APP_DIR && .venv/bin/python manage.py createsuperuser --settings=config.settings_production"
echo "   2. Add GitHub Actions secrets (see DEPLOY.md § Configure GitHub Actions Secrets)"
echo "   3. Visit https://$SERVER_NAME to confirm the site is live"
echo "============================================================"

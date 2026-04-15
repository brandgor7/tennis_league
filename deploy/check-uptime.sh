#!/bin/bash
# Uptime monitor — curl the site, email via Brevo API on state changes only.
# Cron: */5 * * * * /path/to/check-uptime.sh

SITE_URL="https://__DOMAIN__"
ALERT_TO="__ALERT_TO__"
ALERT_FROM="alerts@__DOMAIN__"
BREVO_API_KEY="__BREVO_API_KEY__"
FLAG_FILE="/tmp/site_down.flag"

# Check the /health/ endpoint — Django returns "ok"; nginx maintenance page does not.
# Status code is always 200 (by design for Cloudflare), so we check the body instead.
RESPONSE=$(curl -s --max-time 10 "$SITE_URL/health/")

send_email() {
    local subject="$1"
    local body="$2"
    curl -s -X POST "https://api.brevo.com/v3/smtp/email" \
        -H "api-key: $BREVO_API_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"sender\": {\"email\": \"$ALERT_FROM\"},
            \"to\": [{\"email\": \"$ALERT_TO\"}],
            \"subject\": \"$subject\",
            \"textContent\": \"$body\"
        }"
}

if [[ "$RESPONSE" != "ok" ]]; then
    if [[ ! -f "$FLAG_FILE" ]]; then
        touch "$FLAG_FILE"
        send_email \
            "ALERT: Site is down" \
            "$(date): $SITE_URL/health/ did not return 'ok'. Check nginx/gunicorn."
    fi
else
    if [[ -f "$FLAG_FILE" ]]; then
        rm "$FLAG_FILE"
        send_email \
            "RESOLVED: Site is back up" \
            "$(date): $SITE_URL is responding normally again."
    fi
fi

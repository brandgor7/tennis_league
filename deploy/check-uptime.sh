#!/bin/bash
# Uptime monitor — curl the site, email via Brevo API on state changes only.
# Cron: */5 * * * * /path/to/check-uptime.sh

SITE_URL="https://__DOMAIN__"
ALERT_TO="test@me.com"
ALERT_FROM="alerts@__DOMAIN__"
BREVO_API_KEY="__BREVO_API_KEY__"
FLAG_FILE="/tmp/site_down.flag"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$SITE_URL")

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

if [[ "$HTTP_CODE" != "200" ]]; then
    if [[ ! -f "$FLAG_FILE" ]]; then
        touch "$FLAG_FILE"
        send_email \
            "ALERT: Site is down ($HTTP_CODE)" \
            "$(date): $SITE_URL returned HTTP $HTTP_CODE (or timed out). Check nginx/gunicorn."
    fi
else
    if [[ -f "$FLAG_FILE" ]]; then
        rm "$FLAG_FILE"
        send_email \
            "RESOLVED: Site is back up" \
            "$(date): $SITE_URL is responding normally again."
    fi
fi

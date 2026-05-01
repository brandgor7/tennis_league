#!/bin/bash
# Uptime monitor — curl the site, email via Brevo API on state changes only.
# Cron: */5 * * * * /path/to/check-uptime.sh

SITE_URL="https://__DOMAIN__"
ALERT_TO="__ALERT_TO__"
ALERT_FROM="alerts@__DOMAIN__"
BREVO_API_KEY="__BREVO_API_KEY__"
FLAG_FILE="/tmp/site_down.flag"
LOG_FILE="/var/log/site-uptime.log"

CONFIRM_ATTEMPTS=3   # retries before declaring failure (avoids transient false positives)
CONFIRM_DELAY=5      # seconds between confirmation retries
DIAG_PROBES=3        # additional probes logged after confirmed failure
DIAG_DELAY=10        # seconds between diagnostic probes

probe_site() {
    local tmpfile
    tmpfile=$(mktemp)
    LAST_STATUS=$(curl -s -o "$tmpfile" -w "%{http_code}" --max-time 10 "$SITE_URL/health/")
    LAST_BODY=$(head -c 500 "$tmpfile")
    rm -f "$tmpfile"
}

log_probe() {
    local label="$1"
    {
        echo "--- $label @ $(date) ---"
        echo "HTTP Status: ${LAST_STATUS:-unknown}"
        echo "Response Body: ${LAST_BODY:-(empty)}"
        echo ""
        echo "[uptime / load]"
        uptime
        echo ""
        echo "[top - cpu/wait]"
        top -bn1 | head -12
        echo ""
        echo "[vmstat - io wait]"
        vmstat 1 2 | tail -1
        echo ""
        echo "[disk]"
        df -h /
        echo "---"
        echo ""
    } >> "$LOG_FILE"
}

send_email() {
    local subject="$1" body="$2"
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

# Retry before declaring failure to filter transient blips
SITE_OK=false
for i in $(seq 1 $CONFIRM_ATTEMPTS); do
    probe_site
    if [[ "$LAST_BODY" == "ok" ]]; then
        SITE_OK=true
        if [[ $i -gt 1 ]]; then
            echo "=== TRANSIENT BLIP (recovered on attempt $i) @ $(date) ===" >> "$LOG_FILE"
        fi
        break
    fi
    log_probe "confirmation attempt $i/$CONFIRM_ATTEMPTS"
    [[ $i -lt $CONFIRM_ATTEMPTS ]] && sleep $CONFIRM_DELAY
done

if [[ "$SITE_OK" == "false" ]]; then
    if [[ ! -f "$FLAG_FILE" ]]; then
        touch "$FLAG_FILE"

        echo "=== SITE DOWN CONFIRMED @ $(date) ===" >> "$LOG_FILE"

        for i in $(seq 1 $DIAG_PROBES); do
            probe_site
            log_probe "diagnostic probe $i/$DIAG_PROBES"
            [[ $i -lt $DIAG_PROBES ]] && sleep $DIAG_DELAY
        done

        send_email \
            "ALERT: Site is down" \
            "$(date): $SITE_URL/health/ did not return 'ok' after $CONFIRM_ATTEMPTS attempts. Check nginx/gunicorn. Diagnostics logged to $LOG_FILE."
    fi
else
    if [[ -f "$FLAG_FILE" ]]; then
        rm "$FLAG_FILE"
        echo "=== SITE RECOVERED @ $(date) ===" >> "$LOG_FILE"
        send_email \
            "RESOLVED: Site is back up" \
            "$(date): $SITE_URL is responding normally again."
    fi
fi

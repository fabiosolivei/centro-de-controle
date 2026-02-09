#!/bin/bash
# Health Check Script for Centro de Controle
# Checks API, Langfuse, and Grafana. Alerts Nova via Telegram if anything is down.
# Usage: Run via cron every 5 minutes on VPS
#   */5 * * * * /root/Nova/openclaw-workspace/projects/centro-de-controle/scripts/health-check.sh >> /tmp/health-check.log 2>&1

set -euo pipefail

STATE_FILE="/tmp/health-check-state"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-2097306140}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TAILSCALE_PC="100.126.23.80"

# Services to check
declare -A SERVICES=(
    ["Centro de Controle API"]="http://localhost:8100/api/health"
    ["Langfuse"]="http://${TAILSCALE_PC}:3100/api/public/health"
    ["Grafana"]="http://${TAILSCALE_PC}:3001/api/health"
)

send_telegram() {
    local message="$1"
    if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
        echo "[$(date -Is)] WARN: No TELEGRAM_BOT_TOKEN set, cannot alert"
        return 1
    fi
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\": \"${TELEGRAM_CHAT_ID}\", \"text\": \"${message}\", \"parse_mode\": \"Markdown\"}" \
        > /dev/null 2>&1
}

# Load previous state
declare -A PREV_STATE
if [ -f "$STATE_FILE" ]; then
    while IFS='=' read -r key value; do
        PREV_STATE["$key"]="$value"
    done < "$STATE_FILE"
fi

# Check each service
declare -A CURR_STATE
has_changes=false

for name in "${!SERVICES[@]}"; do
    url="${SERVICES[$name]}"
    if curl -sf --connect-timeout 5 --max-time 10 "$url" > /dev/null 2>&1; then
        CURR_STATE["$name"]="up"
    else
        CURR_STATE["$name"]="down"
    fi

    prev="${PREV_STATE[$name]:-unknown}"
    curr="${CURR_STATE[$name]}"

    if [ "$prev" != "$curr" ]; then
        has_changes=true
        if [ "$curr" = "down" ]; then
            echo "[$(date -Is)] ALERT: $name is DOWN ($url)"
            send_telegram "🚨 *$name* is DOWN
URL: \`$url\`
Time: $(date '+%H:%M %d/%m')"
        elif [ "$prev" = "down" ]; then
            echo "[$(date -Is)] RECOVERED: $name is back UP ($url)"
            send_telegram "✅ *$name* recovered
URL: \`$url\`
Time: $(date '+%H:%M %d/%m')"
        fi
    fi
done

# Save current state
> "$STATE_FILE"
for name in "${!CURR_STATE[@]}"; do
    echo "${name}=${CURR_STATE[$name]}" >> "$STATE_FILE"
done

if [ "$has_changes" = false ]; then
    echo "[$(date -Is)] OK: All services healthy"
fi

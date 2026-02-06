#!/bin/bash
# Seed Life Operating System scheduled messages
# Usage: ./scripts/seed-life-os.sh
#
# This calls the API endpoint that creates all recurring messages
# for the Life Operating System. It's idempotent (safe to run multiple times).

set -e

VPS_URL="https://srv1315519.hstgr.cloud"
ATLAS_KEY="${ATLAS_PUSH_KEY:-}"

# Try to get key from environment or .env
if [ -z "$ATLAS_KEY" ]; then
    ENV_FILE="$(dirname "$0")/../backend/.env"
    if [ -f "$ENV_FILE" ]; then
        ATLAS_KEY=$(grep ATLAS_PUSH_KEY "$ENV_FILE" 2>/dev/null | cut -d= -f2)
    fi
fi

if [ -z "$ATLAS_KEY" ]; then
    echo "Error: ATLAS_PUSH_KEY not set"
    echo "Set it via: export ATLAS_PUSH_KEY=your_key"
    exit 1
fi

echo "=== Seeding Life Operating System Messages ==="
echo "Target: $VPS_URL"
echo ""

RESPONSE=$(curl -s -X POST "$VPS_URL/api/scheduled-messages/seed-life-os" \
    -H "X-Atlas-Key: $ATLAS_KEY" \
    -H "Content-Type: application/json")

echo "Response: $RESPONSE"
echo ""

# Verify by listing
echo "=== Current Scheduled Messages ==="
curl -s "$VPS_URL/api/scheduled-messages" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

echo ""
echo "=== Done ==="

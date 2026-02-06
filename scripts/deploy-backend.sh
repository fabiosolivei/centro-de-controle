#!/bin/bash
# Deploy Centro de Controle Backend to VPS
# Usage: ./scripts/deploy-backend.sh

set -e

VPS_HOST="root@srv1315519.hstgr.cloud"
BACKEND_PATH="/root/Nova/openclaw-workspace/projects/centro-de-controle/backend"
LOCAL_BACKEND="$(dirname "$0")/../backend"

echo "=== Deploy Centro de Controle Backend ==="

# 1. Check connection
echo "[1/4] Checking VPS connection..."
ssh $VPS_HOST "echo 'Connection OK'"

# 2. Copy backend files (excluding .env, database, __pycache__)
echo "[2/4] Deploying backend files..."
scp $LOCAL_BACKEND/*.py $VPS_HOST:$BACKEND_PATH/

# 3. Restart service
echo "[3/4] Restarting service..."
ssh $VPS_HOST "systemctl restart centro-de-controle"

# 4. Verify
echo "[4/4] Verifying..."
sleep 2
ssh $VPS_HOST "systemctl is-active centro-de-controle && curl -s http://localhost:8100/api/health | head -100"

echo ""
echo "=== Deploy complete! ==="
echo "Dashboard: https://fabiosolivei.github.io/centro-de-controle/"
echo "API: https://srv1315519.hstgr.cloud/api/health"

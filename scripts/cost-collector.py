#!/usr/bin/env python3
"""
Cost Collector for Centro de Controle
Collects Moonshot API balance and parses OpenClaw logs for token usage.
Pushes data to the Centro de Controle API.

Usage:
    python3 cost-collector.py

Cron (every 6 hours):
    0 */6 * * * python3 /root/Nova/openclaw-workspace/projects/centro-de-controle/scripts/cost-collector.py >> /tmp/cost-collector.log 2>&1

Environment variables:
    MOONSHOT_API_KEY  - Moonshot API key (from openclaw.json)
    ATLAS_PUSH_KEY    - Centro de Controle API key
    CC_API_URL        - Centro de Controle API URL (default: http://localhost:8100)
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ============================================
# CONFIG
# ============================================

CC_API_URL = os.environ.get("CC_API_URL", "http://localhost:8100")
ATLAS_PUSH_KEY = os.environ.get("ATLAS_PUSH_KEY", "")
MOONSHOT_API_KEY = os.environ.get("MOONSHOT_API_KEY", "")
OPENCLAW_LOG = os.environ.get("OPENCLAW_LOG", "/tmp/openclaw/")
OPENCLAW_CONFIG = os.environ.get("OPENCLAW_CONFIG", "/root/.openclaw/openclaw.json")
STATE_FILE = "/tmp/cost-collector-state.json"

# Kimi K2.5 pricing (USD per 1M tokens)
# Source: https://platform.moonshot.ai/docs/pricing/chat
PRICING = {
    "kimi-k2.5": {"input": 0.60, "output": 3.00, "cached_input": 0.10},
    "default": {"input": 0.60, "output": 3.00},
}


def log(msg: str):
    print(f"[{datetime.now().isoformat()}] {msg}", flush=True)


# ============================================
# LOAD SECRETS FROM OPENCLAW CONFIG
# ============================================

def load_secrets():
    """Load API keys from OpenClaw config if not in env."""
    global MOONSHOT_API_KEY, ATLAS_PUSH_KEY
    if MOONSHOT_API_KEY and ATLAS_PUSH_KEY:
        return

    config_path = Path(OPENCLAW_CONFIG)
    if not config_path.exists():
        log(f"OpenClaw config not found at {OPENCLAW_CONFIG}")
        return

    try:
        with open(config_path) as f:
            config = json.load(f)
        env = config.get("env", {})
        if not MOONSHOT_API_KEY:
            MOONSHOT_API_KEY = env.get("MOONSHOT_API_KEY", "")
        # Atlas key might be in a .env file or systemd env
        if not ATLAS_PUSH_KEY:
            env_file = Path("/root/Nova/openclaw-workspace/projects/centro-de-controle/backend/.env")
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("ATLAS_PUSH_KEY="):
                        ATLAS_PUSH_KEY = line.split("=", 1)[1].strip()
                        break
        log(f"Loaded secrets (moonshot={'yes' if MOONSHOT_API_KEY else 'no'}, atlas={'yes' if ATLAS_PUSH_KEY else 'no'})")
    except Exception as e:
        log(f"Error loading secrets: {e}")


# ============================================
# FETCH MOONSHOT BALANCE
# ============================================

def fetch_moonshot_balance() -> dict | None:
    """Call Moonshot API to get current account balance."""
    if not MOONSHOT_API_KEY:
        log("No MOONSHOT_API_KEY, skipping balance check")
        return None

    try:
        req = urllib.request.Request(
            "https://api.moonshot.ai/v1/users/me/balance",
            headers={"Authorization": f"Bearer {MOONSHOT_API_KEY}"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        balance = data.get("data", data)
        log(f"Moonshot balance: ${balance.get('available_balance', '?'):.2f} "
            f"(voucher: ${balance.get('voucher_balance', 0):.2f}, "
            f"cash: ${balance.get('cash_balance', 0):.2f})")
        return {
            "moonshot_balance": balance.get("available_balance", 0),
            "voucher_balance": balance.get("voucher_balance", 0),
            "cash_balance": balance.get("cash_balance", 0),
        }
    except Exception as e:
        log(f"Error fetching Moonshot balance: {e}")
        return None


# ============================================
# PARSE OPENCLAW LOGS
# ============================================

def load_state() -> dict:
    """Load collector state (last processed log position)."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_offset": 0, "last_run": None}


def save_state(state: dict):
    """Save collector state."""
    state["last_run"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def parse_openclaw_logs() -> list[dict]:
    """Parse OpenClaw JSON logs for token usage data.

    OpenClaw writes daily logs to /tmp/openclaw/openclaw-YYYY-MM-DD.log
    in structured JSON format. Token usage appears in lines containing
    "prompt_tokens" or "completion_tokens" when the model returns usage info.

    Since OpenClaw currently doesn't log per-call token counts in its log files,
    the primary cost tracking mechanism is through Moonshot balance snapshots.
    This parser is kept as a best-effort approach for when token data appears.
    """
    log_dir = Path(OPENCLAW_LOG)
    if not log_dir.exists():
        log(f"OpenClaw log directory not found at {OPENCLAW_LOG}")
        return []

    state = load_state()
    last_files_processed = state.get("files_processed", {})

    calls = []
    try:
        # Process all log files from last 7 days
        today = datetime.now()
        for days_back in range(7):
            d = today - timedelta(days=days_back)
            log_file = log_dir / f"openclaw-{d.strftime('%Y-%m-%d')}.log"
            if not log_file.exists():
                continue

            file_key = log_file.name
            file_size = log_file.stat().st_size
            last_offset = last_files_processed.get(file_key, 0)

            if file_size <= last_offset:
                continue  # No new data

            with open(log_file, "r", errors="replace") as f:
                f.seek(last_offset)
                content = f.read()
                new_offset = f.tell()

            # Parse JSON log lines for token usage
            for line in content.splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                # Look for usage data in various locations within the JSON
                line_str = json.dumps(entry)
                if "prompt_tokens" not in line_str and "input_tokens" not in line_str:
                    continue

                # Extract token counts
                usage_match = re.search(
                    r'"prompt_tokens"\s*:\s*(\d+).*?"completion_tokens"\s*:\s*(\d+)',
                    line_str
                )
                if not usage_match:
                    usage_match = re.search(
                        r'"input_tokens"\s*:\s*(\d+).*?"output_tokens"\s*:\s*(\d+)',
                        line_str
                    )
                if not usage_match:
                    continue

                input_tokens = int(usage_match.group(1))
                output_tokens = int(usage_match.group(2))

                # Extract cached tokens (Moonshot returns cached_tokens at top level of usage)
                cached_match = re.search(r'"cached_tokens"\s*:\s*(\d+)', line_str)
                cached_tokens = int(cached_match.group(1)) if cached_match else 0

                # Extract model
                model_match = re.search(r'"model"\s*:\s*"([^"]+)"', line_str)
                model = model_match.group(1) if model_match else "kimi-k2.5"

                # Calculate cost (separate cached vs non-cached input tokens)
                pricing = PRICING.get(model, PRICING["default"])
                non_cached_input = max(0, input_tokens - cached_tokens)
                cached_cost = cached_tokens * pricing.get("cached_input", pricing["input"]) / 1_000_000
                input_cost = non_cached_input * pricing["input"] / 1_000_000
                output_cost = output_tokens * pricing["output"] / 1_000_000
                cost = cached_cost + input_cost + output_cost

                # Extract timestamp
                timestamp = entry.get("time") or entry.get("_meta", {}).get("date", "")
                if not timestamp:
                    ts_match = re.search(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', line_str)
                    timestamp = ts_match.group(0) if ts_match else datetime.now().isoformat()

                calls.append({
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cached_tokens": cached_tokens,
                    "cost_usd": round(cost, 6),
                    "source": "openclaw_log",
                    "timestamp": timestamp,
                })

            last_files_processed[file_key] = new_offset

        state["files_processed"] = last_files_processed
        save_state(state)
        log(f"Parsed {len(calls)} LLM calls from OpenClaw logs")
    except Exception as e:
        log(f"Error parsing OpenClaw logs: {e}")

    return calls


# ============================================
# PUSH TO CENTRO DE CONTROLE
# ============================================

def push_to_api(snapshot: dict | None, calls: list[dict]):
    """Push cost data to Centro de Controle API."""
    if not ATLAS_PUSH_KEY:
        log("No ATLAS_PUSH_KEY, skipping push")
        return False

    payload = {
        "snapshot": snapshot,
        "calls": calls,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{CC_API_URL}/api/metrics/costs",
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Atlas-Key": ATLAS_PUSH_KEY,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        log(f"Pushed to API: {result}")
        return True
    except Exception as e:
        log(f"Error pushing to API: {e}")
        return False


# ============================================
# MAIN
# ============================================

def main():
    log("=== Cost Collector Starting ===")

    load_secrets()

    # 1. Fetch Moonshot balance
    snapshot = fetch_moonshot_balance()

    # 2. Parse OpenClaw logs for token usage
    calls = parse_openclaw_logs()

    # 3. Push to Centro de Controle API
    if snapshot or calls:
        success = push_to_api(snapshot, calls)
        if success:
            log(f"Done: {1 if snapshot else 0} snapshot, {len(calls)} calls pushed")
        else:
            log("Failed to push data")
    else:
        log("No data to push")

    log("=== Cost Collector Finished ===")


if __name__ == "__main__":
    main()

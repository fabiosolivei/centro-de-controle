#!/usr/bin/env python3
"""
Reminder & Scheduled Message Dispatcher

Runs every minute via cron. Handles two types of notifications:
1. One-time reminders (existing system)
2. Recurring scheduled messages (Life Operating System)

Sends via OpenClaw CLI to Telegram (same mechanism as sibling relay).

Cron:
  * * * * * cd /root/Nova/openclaw-workspace/projects/centro-de-controle/backend && python3 reminder_dispatcher.py >> /tmp/reminder_dispatcher.log 2>&1
"""

import json
import os
import sqlite3
import subprocess
from datetime import datetime

# Try to import pytz, fall back to manual offset
try:
    import pytz
    TIMEZONE = pytz.timezone("America/Sao_Paulo")
    def now_local():
        return datetime.now(TIMEZONE)
except ImportError:
    from datetime import timedelta, timezone
    SP_TZ = timezone(timedelta(hours=-3))
    def now_local():
        return datetime.now(SP_TZ)

# Configuracoes
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "2097306140")

# Load .env if exists
env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, value = line.strip().split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


BUTTON_LAYOUTS = {
    "morning_energy": [
        [
            {"text": "1", "callback_data": "life_os:morning_energy:1"},
            {"text": "2", "callback_data": "life_os:morning_energy:2"},
            {"text": "3", "callback_data": "life_os:morning_energy:3"},
            {"text": "4", "callback_data": "life_os:morning_energy:4"},
            {"text": "5", "callback_data": "life_os:morning_energy:5"},
        ]
    ],
    "morning_routine": [
        [
            {"text": "\U0001f48a Medicacao", "callback_data": "life_os:morning_routine:medicacao"},
            {"text": "\U0001f3cb\ufe0f Academia", "callback_data": "life_os:morning_routine:academia"},
        ],
        [
            {"text": "\U0001f3c3 Corrida", "callback_data": "life_os:morning_routine:corrida"},
            {"text": "\U0001f964 Shake matinal", "callback_data": "life_os:morning_routine:shake"},
        ],
    ],
    "lunch_break": [
        [{"text": "\U0001f37d\ufe0f Saindo pro almoco", "callback_data": "life_os:lunch_break:done"}]
    ],
    "wins_journal": [
        [
            {"text": "\u270d\ufe0f Registrar wins", "callback_data": "life_os:wins_journal:log"},
            {"text": "\u23ed\ufe0f Pular hoje", "callback_data": "life_os:wins_journal:skip"},
        ]
    ],
    "work_stop": [
        [
            {"text": "\u2705 Ja parei", "callback_data": "life_os:work_stop:stopped"},
            {"text": "\u23f0 30 min", "callback_data": "life_os:work_stop:30min"},
            {"text": "\U0001f3e0 Ja estava off", "callback_data": "life_os:work_stop:already_off"},
        ]
    ],
    "evening_wind_down": [
        [
            {"text": "\U0001f9d8 Meditei", "callback_data": "life_os:evening_wind_down:done"},
            {"text": "\u23ed\ufe0f Pular hoje", "callback_data": "life_os:evening_wind_down:skip"},
        ]
    ],
    "wednesday_mba": [
        [
            {"text": "\u26a0\ufe0f Sim, tem deadline", "callback_data": "life_os:wednesday_mba:has_deadline"},
            {"text": "\u2705 Tudo ok", "callback_data": "life_os:wednesday_mba:ok"},
        ]
    ],
}


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def send_via_openclaw(text: str) -> int:
    """Send message via OpenClaw CLI. Returns message_id on success, 0 on failure."""
    try:
        result = subprocess.run(
            ["openclaw", "message", "send",
             "--channel", "telegram",
             "--target", TELEGRAM_CHAT_ID,
             "--message", text],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode == 0:
            import re
            match = re.search(r"Message ID:\s*(\d+)", result.stdout)
            msg_id = int(match.group(1)) if match else 0
            print(f"  [openclaw] sent, message_id={msg_id}")
            return msg_id
        else:
            print(f"  [openclaw] error: {result.stderr[:200]}")
            return 0
    except FileNotFoundError:
        print("  [openclaw] CLI not found")
        return 0
    except Exception as e:
        print(f"  [openclaw] exception: {e}")
        return 0


def send_telegram_message(text: str) -> bool:
    """Send message via OpenClaw CLI, fallback to direct Bot API."""
    msg_id = send_via_openclaw(text)
    if msg_id:
        return True
    print("  [fallback] trying direct Telegram API")
    return send_telegram_direct(text)


def send_telegram_direct(text: str) -> bool:
    """Fallback: send via Telegram Bot API directly"""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        print(f"  No TELEGRAM_BOT_TOKEN set, cannot send: {text[:50]}...")
        return False
    
    try:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = httpx.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"  Telegram API error: {e}")
        return False


def add_buttons_to_message(message_id: int, buttons: list) -> bool:
    """Add inline keyboard buttons to an existing message via editMessageReplyMarkup."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        print(f"  [buttons] no TELEGRAM_BOT_TOKEN, skipping buttons")
        return False

    try:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/editMessageReplyMarkup"
        response = httpx.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": buttons},
        }, timeout=10)
        if response.status_code == 200:
            print(f"  [buttons] added to message {message_id}")
            return True
        print(f"  [buttons] API error {response.status_code}: {response.text[:200]}")
        return False
    except Exception as e:
        print(f"  [buttons] error: {e}")
        return False


def send_telegram_with_buttons(text: str, buttons: list) -> bool:
    """Send message via OpenClaw (Nova gets context) then add buttons via Bot API.
    Two-step: 1) OpenClaw send (Nova sees it) 2) editMessageReplyMarkup (buttons appear)."""
    msg_id = send_via_openclaw(text)
    if msg_id:
        add_buttons_to_message(msg_id, buttons)
        return True

    print("  [fallback] OpenClaw failed, sending with buttons via Bot API directly")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        print(f"  [fallback] no token, sending plain text")
        return send_telegram_direct(text)

    try:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = httpx.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": buttons},
        }, timeout=10)
        if response.status_code == 200:
            print(f"  [fallback] sent with buttons via Bot API")
            return True
        print(f"  [fallback] Bot API error {response.status_code}: {response.text[:200]}")
        return send_telegram_direct(text)
    except Exception as e:
        print(f"  [fallback] error: {e}")
        return send_telegram_direct(text)


def process_one_time_reminders():
    """Process one-time reminders (existing system)"""
    conn = get_db()
    cursor = conn.cursor()
    
    now_str = now_local().strftime("%Y-%m-%dT%H:%M")
    
    cursor.execute("""
        SELECT * FROM reminders 
        WHERE is_completed = 0 
        AND datetime(due_datetime) <= datetime(?)
        ORDER BY due_datetime ASC
    """, (now_str,))
    
    reminders = [dict(row) for row in cursor.fetchall()]
    
    for reminder in reminders:
        priority_emoji = {
            "high": "🔴", "urgent": "🚨", "normal": "🔔", "low": "📝"
        }.get(reminder.get("priority", "normal"), "🔔")
        
        text = f"{priority_emoji} LEMBRETE\n\n{reminder['title']}"
        if reminder.get("description"):
            text += f"\n\n{reminder['description']}"
        
        print(f"  Sending reminder: {reminder['title'][:50]}...")
        if send_telegram_message(text):
            cursor.execute("UPDATE reminders SET is_completed = 1 WHERE id = ?", (reminder['id'],))
            conn.commit()
            print(f"  ✅ Sent and marked complete")
        else:
            print(f"  ⚠️ Failed, will retry next minute")
    
    conn.close()
    return len(reminders)


def process_scheduled_messages():
    """Process recurring scheduled messages (Life Operating System)"""
    conn = get_db()
    cursor = conn.cursor()
    
    now = now_local()
    current_time = now.strftime("%H:%M")
    # Python weekday: Mon=0, Sun=6. Our system: Mon=1, Sun=7
    current_day = str(now.isoweekday())
    today_date = now.strftime("%Y-%m-%d")
    
    # Find active messages matching current time and day
    cursor.execute("""
        SELECT * FROM scheduled_messages 
        WHERE is_active = 1 
        AND time = ?
    """, (current_time,))
    
    messages = [dict(row) for row in cursor.fetchall()]
    sent_count = 0
    
    for msg in messages:
        # Check if today is in the scheduled days
        scheduled_days = msg['days'].split(',')
        if current_day not in scheduled_days:
            continue
        
        # Check if already sent today (prevent duplicates)
        if msg.get('last_sent_at') and msg['last_sent_at'].startswith(today_date):
            continue
        
        # Send the message
        category_prefix = {
            "life_os": "🧠",
            "mba": "📚",
            "work": "💼",
        }.get(msg.get("category", "life_os"), "📌")
        
        text = f"{category_prefix} {msg['message']}"
        
        buttons = BUTTON_LAYOUTS.get(msg['name'])
        mode = "buttons" if buttons else "plain"
        print(f"  Sending scheduled: {msg['name']} ({current_time}) [{mode}]")
        success = send_telegram_with_buttons(text, buttons) if buttons else send_telegram_message(text)
        if success:
            cursor.execute(
                "UPDATE scheduled_messages SET last_sent_at = ? WHERE id = ?",
                (now.isoformat(), msg['id'])
            )
            conn.commit()
            sent_count += 1
            print(f"  ✅ Sent: {msg['name']} [{mode}]")
        else:
            print(f"  ⚠️ Failed: {msg['name']} [{mode}]")
    
    conn.close()
    return sent_count


def main():
    now = now_local()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # Only log header every 15 minutes to reduce noise
    if now.minute % 15 == 0:
        print(f"\n[{timestamp}] Dispatcher check (day={now.isoweekday()}, time={now.strftime('%H:%M')})")
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        return
    
    # Process one-time reminders
    reminder_count = process_one_time_reminders()
    
    # Process recurring scheduled messages
    scheduled_count = process_scheduled_messages()
    
    # Only log when something happened or every 15 min
    if reminder_count > 0 or scheduled_count > 0:
        print(f"[{timestamp}] Sent: {reminder_count} reminders, {scheduled_count} scheduled messages")
    elif now.minute % 15 == 0:
        print(f"  ✓ No messages due")


if __name__ == "__main__":
    main()

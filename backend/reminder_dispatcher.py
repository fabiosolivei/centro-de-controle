#!/usr/bin/env python3
"""
Reminder Dispatcher - Verifica lembretes pendentes e envia notificações

Este script deve ser executado periodicamente (a cada minuto) via cron.
Verifica lembretes com due_datetime <= now() e envia via Telegram.

Uso:
  python reminder_dispatcher.py

Cron (a cada minuto):
  * * * * * cd /home/fabio/Documents/centro-de-controle/backend && python3 reminder_dispatcher.py >> /tmp/reminder_dispatcher.log 2>&1
"""

import os
import sqlite3
import httpx
from datetime import datetime, timedelta
import pytz

# Configurações
DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TIMEZONE = pytz.timezone("America/Sao_Paulo")

# Carregar do .env se existir
env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, value = line.strip().split("=", 1)
                os.environ.setdefault(key, value)
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_due_reminders():
    """Busca lembretes com due_datetime <= agora e não completados"""
    conn = get_db()
    cursor = conn.cursor()
    
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%dT%H:%M")
    
    cursor.execute("""
        SELECT * FROM reminders 
        WHERE is_completed = 0 
        AND datetime(due_datetime) <= datetime(?)
        ORDER BY due_datetime ASC
    """, (now,))
    
    reminders = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reminders


def send_telegram_notification(reminder: dict) -> bool:
    """Envia notificação via Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️ Telegram não configurado. Lembrete: {reminder['title']}")
        return False
    
    # Formatar mensagem
    priority_emoji = {
        "high": "🔴",
        "urgent": "🚨",
        "normal": "🔔",
        "low": "📝"
    }.get(reminder.get("priority", "normal"), "🔔")
    
    message = f"""{priority_emoji} **LEMBRETE**

📌 {reminder['title']}

{reminder.get('description', '') if reminder.get('description') else ''}

⏰ Agendado para: {reminder['due_datetime']}
"""
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        response = httpx.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Notificação enviada: {reminder['title']}")
            return True
        else:
            print(f"❌ Erro ao enviar: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Erro de conexão: {e}")
        return False


def mark_as_notified(reminder_id: int):
    """Marca lembrete como completado após notificação"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE reminders SET is_completed = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def main():
    timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] Verificando lembretes pendentes...")
    
    # Verificar se DB existe
    if not os.path.exists(DB_PATH):
        print(f"❌ Database não encontrado: {DB_PATH}")
        return
    
    # Buscar lembretes pendentes
    reminders = get_due_reminders()
    
    if not reminders:
        print("✓ Nenhum lembrete pendente")
        return
    
    print(f"📋 {len(reminders)} lembrete(s) para notificar")
    
    # Processar cada lembrete
    for reminder in reminders:
        print(f"\n📌 Processando: {reminder['title']}")
        print(f"   Due: {reminder['due_datetime']}")
        
        # Enviar notificação
        if send_telegram_notification(reminder):
            # Marcar como completado após notificação bem-sucedida
            mark_as_notified(reminder['id'])
            print(f"   ✅ Marcado como completado")
        else:
            print(f"   ⚠️ Notificação falhou, tentará novamente")


if __name__ == "__main__":
    main()

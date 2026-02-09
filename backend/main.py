#!/usr/bin/env python3
"""
Centro de Controle - Backend API
Dashboard pessoal do Fábio
"""

import os
import json
import re
from datetime import datetime, date
from typing import Optional, List
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env file
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        # Fallback: manual .env parsing
        with open(_env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    os.environ.setdefault(key.strip(), value.strip())

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import shutil
import uuid

import sqlite3

# Calendar integration
from calendar_integration import (
    get_today_events as cal_get_today_events,
    get_week_events as cal_get_week_events,
    get_events_for_date as cal_get_events_for_date,
    fetch_calendar_events
)

# ============================================
# DATABASE SETUP
# ============================================

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa o banco de dados com as tabelas necessárias"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabela de Tarefas (Kanban)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'todo',
            priority TEXT DEFAULT 'normal',
            due_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Lembretes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_datetime TEXT NOT NULL,
            is_completed INTEGER DEFAULT 0,
            priority TEXT DEFAULT 'normal',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Notas (Reuniões)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            meeting_date TEXT,
            tags TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Eventos do Dia
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            event_date TEXT NOT NULL,
            event_time TEXT,
            event_type TEXT DEFAULT 'meeting',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Projetos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            priority TEXT DEFAULT 'normal',
            progress INTEGER DEFAULT 0,
            category TEXT DEFAULT 'pessoal',
            due_date TEXT,
            tags TEXT,
            nova_notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Documentos/Links do Projeto
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            doc_type TEXT DEFAULT 'link',
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    
    # Migrations: adicionar project_id em tasks e notes
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN project_id INTEGER")
    except:
        pass  # Coluna já existe
    
    try:
        cursor.execute("ALTER TABLE notes ADD COLUMN project_id INTEGER")
    except:
        pass  # Coluna já existe
    
    # ============================================
    # CONFLUENCE TABLES
    # ============================================
    
    # Tabela de Sprints
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS confluence_sprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sprint_name TEXT NOT NULL,
            sprint_number INTEGER UNIQUE,
            start_date TEXT,
            end_date TEXT,
            release_date TEXT,
            is_current INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Initiatives (BEESIP)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS confluence_initiatives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            beesip_id TEXT UNIQUE NOT NULL,
            title TEXT,
            status TEXT,
            priority TEXT,
            team TEXT,
            kickoff_date TEXT,
            zone_approval TEXT,
            jira_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Epics (BEESCAD)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS confluence_epics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            beescad_id TEXT UNIQUE NOT NULL,
            initiative_beesip TEXT,
            title TEXT,
            status TEXT,
            size TEXT,
            sprint TEXT,
            milestones TEXT,
            jira_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (initiative_beesip) REFERENCES confluence_initiatives(beesip_id)
        )
    """)
    
    # Tabela de Risks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS confluence_risks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            beescad_id TEXT UNIQUE NOT NULL,
            title TEXT,
            assignee TEXT,
            status TEXT,
            priority TEXT,
            gut_score INTEGER,
            jira_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Bugs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS confluence_bugs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            beescad_id TEXT UNIQUE NOT NULL,
            title TEXT,
            priority TEXT,
            status TEXT,
            team TEXT,
            jira_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Sync Status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS confluence_sync_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            items_synced INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )
    """)
    
    # Tabela de Sync Log (unified, all sources)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            items_count INTEGER DEFAULT 0,
            error_message TEXT,
            synced_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Meeting Notes (from Notion/Atlas push)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meeting_notes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            date TEXT,
            project TEXT,
            summary TEXT,
            participants TEXT,
            action_items TEXT,
            source TEXT DEFAULT 'notion',
            notion_url TEXT,
            synced_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sibling_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            message TEXT NOT NULL,
            context TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            read_at TEXT
        )
    """)
    
    # Tabela de Mensagens Agendadas Recorrentes (Life Operating System)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            message TEXT NOT NULL,
            time TEXT NOT NULL,
            days TEXT NOT NULL DEFAULT '1,2,3,4,5,6,7',
            priority TEXT DEFAULT 'normal',
            category TEXT DEFAULT 'life_os',
            is_active INTEGER DEFAULT 1,
            last_sent_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Journal (Life OS responses - Fabio's replies to scheduled messages)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS life_os_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_name TEXT,
            prompt TEXT,
            response TEXT NOT NULL,
            energy_level INTEGER,
            wins TEXT,
            mood TEXT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela de Weekly Briefs (intelligence pushed from Atlas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weekly_briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            week_glance TEXT,
            action_items_urgent TEXT DEFAULT '[]',
            action_items_important TEXT DEFAULT '[]',
            decisions TEXT DEFAULT '[]',
            energy_check TEXT DEFAULT '{}',
            full_markdown TEXT,
            generated_at TEXT,
            pushed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Atlas canonical memory mirror — decisions log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS atlas_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            decision_text TEXT NOT NULL,
            rationale TEXT,
            category TEXT NOT NULL DEFAULT 'architecture',
            superseded_by INTEGER,
            conversation_id TEXT,
            created_by TEXT DEFAULT 'atlas',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Atlas canonical memory mirror — state snapshots
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS state_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            updated_by TEXT DEFAULT 'atlas',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ============================================
    # OBSERVABILITY TABLES
    # ============================================

    # Session-level tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_number INTEGER DEFAULT 1,
            role TEXT NOT NULL DEFAULT 'user',
            content_preview TEXT,
            intent_classified TEXT,
            tools_called TEXT,
            tools_failed TEXT,
            duration_ms INTEGER,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Per-tool-call telemetry
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            tool_name TEXT NOT NULL,
            arguments_preview TEXT,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            duration_ms INTEGER,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Intent accuracy tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routing_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            query_preview TEXT,
            intents_classified TEXT,
            intents_expected TEXT,
            tools_called TEXT,
            tools_succeeded TEXT,
            context_tokens_estimate INTEGER,
            accuracy_score REAL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # LLM-as-judge results
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quality_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            evaluator TEXT NOT NULL DEFAULT 'claude',
            dimension TEXT NOT NULL,
            score INTEGER NOT NULL,
            rationale TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Aggregated daily reports
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL UNIQUE,
            report_json TEXT NOT NULL,
            summary TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Aggregated weekly reports
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weekly_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL UNIQUE,
            report_json TEXT NOT NULL,
            summary TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized")


# ============================================
# AUTH HELPERS
# ============================================

ATLAS_PUSH_KEY = os.environ.get("ATLAS_PUSH_KEY", "")

def verify_atlas_key(request: Request):
    """Verify the Atlas push API key"""
    if not ATLAS_PUSH_KEY:
        raise HTTPException(503, "Push not configured (ATLAS_PUSH_KEY not set)")
    key = request.headers.get("X-Atlas-Key", "")
    if key != ATLAS_PUSH_KEY:
        raise HTTPException(401, "Invalid or missing Atlas key")


def log_sync(source: str, status: str, items_count: int = 0, error_message: str = None):
    """Write a sync log entry"""
    conn = get_db()
    conn.execute("""
        INSERT INTO sync_log (source, status, items_count, error_message, synced_at)
        VALUES (?, ?, ?, ?, ?)
    """, (source, status, items_count, error_message, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def _persist_confluence_data(data: dict, conn=None) -> int:
    """Persist parsed Confluence situation wall data to SQLite. Returns total items synced."""
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    
    cursor = conn.cursor()
    total = 0
    
    # Sprints
    for sprint in data.get("sprints", []):
        cursor.execute("""
            INSERT OR REPLACE INTO confluence_sprints 
            (sprint_name, sprint_number, start_date, end_date, release_date, is_current)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            sprint.get("name", ""),
            sprint.get("number", 0),
            sprint.get("start_date", ""),
            sprint.get("end_date", ""),
            sprint.get("release_date", ""),
            sprint.get("is_current", False)
        ))
        total += 1
    
    # Initiatives
    for init in data.get("initiatives", []):
        cursor.execute("""
            INSERT OR REPLACE INTO confluence_initiatives
            (beesip_id, title, status, priority, team, kickoff_date, jira_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            init.get("beesip_id", ""),
            init.get("title", ""),
            init.get("status", ""),
            init.get("priority", ""),
            init.get("team", ""),
            init.get("kickoff_date", ""),
            init.get("jira_url", "")
        ))
        total += 1
    
    # Epics
    for epic in data.get("epics", []):
        cursor.execute("""
            INSERT OR REPLACE INTO confluence_epics
            (beescad_id, title, status, size, sprint, initiative_beesip, jira_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            epic.get("beescad_id", ""),
            epic.get("title", ""),
            epic.get("status", ""),
            epic.get("size", ""),
            epic.get("sprint", ""),
            epic.get("initiative_beesip", ""),
            epic.get("jira_url", "")
        ))
        total += 1
    
    # Risks
    for risk in data.get("risks", []):
        cursor.execute("""
            INSERT OR REPLACE INTO confluence_risks
            (beescad_id, title, assignee, status, priority, gut_score, jira_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            risk.get("beescad_id", ""),
            risk.get("title", ""),
            risk.get("assignee", ""),
            risk.get("status", ""),
            risk.get("priority", ""),
            risk.get("gut_score", 0),
            risk.get("jira_url", "")
        ))
        total += 1
    
    # Bugs
    for bug in data.get("bugs", []):
        cursor.execute("""
            INSERT OR REPLACE INTO confluence_bugs
            (beescad_id, title, priority, status, team, jira_url)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            bug.get("beescad_id", ""),
            bug.get("title", ""),
            bug.get("priority", ""),
            bug.get("status", ""),
            bug.get("team", ""),
            bug.get("jira_url", "")
        ))
        total += 1
    
    conn.commit()
    if close_conn:
        conn.close()
    
    return total


# ============================================
# PYDANTIC MODELS
# ============================================

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"  # todo, doing, done
    priority: str = "normal"  # low, normal, high, urgent
    due_date: Optional[str] = None
    project_id: Optional[int] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    project_id: Optional[int] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None

class Task(TaskCreate):
    id: int
    created_at: str
    updated_at: str

class ReminderCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_datetime: str
    priority: str = "normal"

class Reminder(ReminderCreate):
    id: int
    is_completed: bool
    created_at: str

class ScheduledMessageCreate(BaseModel):
    name: str
    message: str
    time: str  # HH:MM format
    days: str = "1,2,3,4,5,6,7"  # 1=Mon, 7=Sun
    priority: str = "normal"
    category: str = "life_os"

class ScheduledMessage(ScheduledMessageCreate):
    id: int
    is_active: bool
    last_sent_at: Optional[str] = None
    created_at: str

class JournalEntryCreate(BaseModel):
    message_name: Optional[str] = None  # which scheduled message prompted this
    prompt: Optional[str] = None  # the original prompt text
    response: str  # Fabio's reply
    energy_level: Optional[int] = None  # 1-5 scale
    wins: Optional[str] = None  # comma-separated wins
    mood: Optional[str] = None  # free-text mood tag

class NoteCreate(BaseModel):
    title: str
    content: Optional[str] = None
    meeting_date: Optional[str] = None
    tags: Optional[str] = None
    project_id: Optional[int] = None

class Note(NoteCreate):
    id: int
    created_at: str
    updated_at: str

class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    event_date: str
    event_time: Optional[str] = None
    event_type: str = "meeting"

class Event(EventCreate):
    id: int
    created_at: str

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = "active"  # active, paused, completed, archived
    priority: str = "normal"  # low, normal, high
    progress: int = 0  # 0-100
    category: str = "pessoal"  # trabalho, mba, pessoal, familia
    due_date: Optional[str] = None
    tags: Optional[str] = None
    nova_notes: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    progress: Optional[int] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    tags: Optional[str] = None
    nova_notes: Optional[str] = None

class Project(ProjectCreate):
    id: int
    created_at: str
    updated_at: str

# ============================================
# APP SETUP
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown
    pass

app = FastAPI(
    title="Centro de Controle API",
    description="Dashboard pessoal do Fábio",
    version="1.0.0",
    lifespan=lifespan
)

# CORS para permitir frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# TASKS ROUTES (KANBAN)
# ============================================

@app.get("/api/tasks", response_model=List[dict])
async def get_tasks(status: Optional[str] = None):
    """Lista todas as tarefas, opcionalmente filtradas por status"""
    conn = get_db()
    cursor = conn.cursor()
    
    if status:
        cursor.execute("SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, created_at DESC", (status,))
    else:
        cursor.execute("SELECT * FROM tasks ORDER BY priority DESC, created_at DESC")
    
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tasks

@app.post("/api/tasks", response_model=dict)
async def create_task(task: TaskCreate):
    """Cria uma nova tarefa"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO tasks (title, description, status, priority, due_date, project_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (task.title, task.description, task.status, task.priority, task.due_date, task.project_id))
    
    task_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    new_task = dict(cursor.fetchone())
    conn.close()
    
    return new_task

@app.put("/api/tasks/{task_id}", response_model=dict)
async def update_task(task_id: int, task: TaskUpdate):
    """Atualiza uma tarefa existente"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Verificar se existe
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Atualizar apenas campos fornecidos
    updates = []
    values = []
    for field, value in task.model_dump(exclude_unset=True).items():
        if value is not None:
            updates.append(f"{field} = ?")
            values.append(value)
    
    if updates:
        updates.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(task_id)
        
        cursor.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    updated_task = dict(cursor.fetchone())
    conn.close()
    
    return updated_task

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int):
    """Deleta uma tarefa"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found")
    
    conn.commit()
    conn.close()
    return {"message": "Task deleted"}

# ============================================
# REMINDERS ROUTES
# ============================================

@app.get("/api/reminders", response_model=List[dict])
async def get_reminders(include_completed: bool = False):
    """Lista lembretes"""
    conn = get_db()
    cursor = conn.cursor()
    
    if include_completed:
        cursor.execute("SELECT * FROM reminders ORDER BY due_datetime ASC")
    else:
        cursor.execute("SELECT * FROM reminders WHERE is_completed = 0 ORDER BY due_datetime ASC")
    
    reminders = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reminders

@app.post("/api/reminders", response_model=dict)
async def create_reminder(reminder: ReminderCreate):
    """Cria um novo lembrete"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO reminders (title, description, due_datetime, priority)
        VALUES (?, ?, ?, ?)
    """, (reminder.title, reminder.description, reminder.due_datetime, reminder.priority))
    
    reminder_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    new_reminder = dict(cursor.fetchone())
    conn.close()
    
    return new_reminder

@app.put("/api/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: int):
    """Marca lembrete como completo"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE reminders SET is_completed = 1 WHERE id = ?", (reminder_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    conn.commit()
    conn.close()
    return {"message": "Reminder completed"}

@app.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int):
    """Deleta um lembrete"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    conn.commit()
    conn.close()
    return {"message": "Reminder deleted"}

# ============================================
# SCHEDULED MESSAGES ROUTES (Life Operating System)
# ============================================

@app.get("/api/scheduled-messages", response_model=List[dict])
async def get_scheduled_messages(category: Optional[str] = None, active_only: bool = True):
    """Lista mensagens agendadas recorrentes"""
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM scheduled_messages WHERE 1=1"
    params = []
    
    if active_only:
        query += " AND is_active = 1"
    if category:
        query += " AND category = ?"
        params.append(category)
    
    query += " ORDER BY time ASC"
    cursor.execute(query, params)
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return messages

@app.post("/api/scheduled-messages", response_model=dict)
async def create_scheduled_message(msg: ScheduledMessageCreate):
    """Cria uma nova mensagem agendada recorrente"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO scheduled_messages (name, message, time, days, priority, category)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (msg.name, msg.message, msg.time, msg.days, msg.priority, msg.category))
    
    msg_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM scheduled_messages WHERE id = ?", (msg_id,))
    new_msg = dict(cursor.fetchone())
    conn.close()
    
    return new_msg

@app.put("/api/scheduled-messages/{msg_id}", response_model=dict)
async def update_scheduled_message(msg_id: int, msg: ScheduledMessageCreate):
    """Atualiza uma mensagem agendada"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE scheduled_messages 
        SET name = ?, message = ?, time = ?, days = ?, priority = ?, category = ?,
            is_active = 1
        WHERE id = ?
    """, (msg.name, msg.message, msg.time, msg.days, msg.priority, msg.category, msg_id))
    
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Scheduled message not found")
    
    conn.commit()
    cursor.execute("SELECT * FROM scheduled_messages WHERE id = ?", (msg_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated

@app.delete("/api/scheduled-messages/{msg_id}")
async def delete_scheduled_message(msg_id: int):
    """Deleta uma mensagem agendada"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM scheduled_messages WHERE id = ?", (msg_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Scheduled message not found")
    
    conn.commit()
    conn.close()
    return {"message": "Scheduled message deleted"}

@app.put("/api/scheduled-messages/{msg_id}/toggle")
async def toggle_scheduled_message(msg_id: int):
    """Ativa/desativa uma mensagem agendada"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT is_active FROM scheduled_messages WHERE id = ?", (msg_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Scheduled message not found")
    
    new_state = 0 if row["is_active"] else 1
    cursor.execute("UPDATE scheduled_messages SET is_active = ? WHERE id = ?", (new_state, msg_id))
    conn.commit()
    conn.close()
    return {"message": f"Scheduled message {'activated' if new_state else 'deactivated'}", "is_active": bool(new_state)}

# ============================================
# LIFE OS JOURNAL (Response Tracking)
# ============================================

@app.post("/api/life-os/journal", response_model=dict)
async def create_journal_entry(entry: JournalEntryCreate):
    """Records a Life OS journal entry (Fabio's response to a scheduled message)"""
    conn = get_db()
    cursor = conn.cursor()
    
    now = datetime.now()
    
    cursor.execute("""
        INSERT INTO life_os_journal (message_name, prompt, response, energy_level, wins, mood, date, time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (entry.message_name, entry.prompt, entry.response, entry.energy_level,
          entry.wins, entry.mood, now.strftime("%Y-%m-%d"), now.strftime("%H:%M")))
    
    entry_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM life_os_journal WHERE id = ?", (entry_id,))
    new_entry = dict(cursor.fetchone())
    conn.close()
    
    return new_entry

@app.get("/api/life-os/journal", response_model=List[dict])
async def get_journal_entries(
    days: int = 7,
    message_name: Optional[str] = None
):
    """Returns journal entries for analysis"""
    conn = get_db()
    cursor = conn.cursor()
    
    from_date = (datetime.now() - __import__('datetime').timedelta(days=days)).strftime("%Y-%m-%d")
    
    query = "SELECT * FROM life_os_journal WHERE date >= ?"
    params = [from_date]
    
    if message_name:
        query += " AND message_name = ?"
        params.append(message_name)
    
    query += " ORDER BY date DESC, time DESC"
    cursor.execute(query, params)
    entries = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return entries

@app.get("/api/life-os/analytics", response_model=dict)
async def get_life_os_analytics(days: int = 30):
    """Returns Life OS analytics - patterns, streaks, energy trends"""
    conn = get_db()
    cursor = conn.cursor()
    
    from_date = (datetime.now() - __import__('datetime').timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Total entries
    cursor.execute("SELECT COUNT(*) as count FROM life_os_journal WHERE date >= ?", (from_date,))
    total = cursor.fetchone()['count']
    
    # Energy trend (daily averages)
    cursor.execute("""
        SELECT date, AVG(energy_level) as avg_energy, COUNT(*) as entries
        FROM life_os_journal 
        WHERE date >= ? AND energy_level IS NOT NULL
        GROUP BY date ORDER BY date
    """, (from_date,))
    energy_trend = [dict(row) for row in cursor.fetchall()]
    
    # Response rate per message type
    cursor.execute("""
        SELECT message_name, COUNT(*) as count, AVG(energy_level) as avg_energy
        FROM life_os_journal 
        WHERE date >= ? AND message_name IS NOT NULL
        GROUP BY message_name ORDER BY count DESC
    """, (from_date,))
    by_message = [dict(row) for row in cursor.fetchall()]
    
    # Wins frequency (most common wins)
    cursor.execute("""
        SELECT wins FROM life_os_journal 
        WHERE date >= ? AND wins IS NOT NULL AND wins != ''
    """, (from_date,))
    all_wins = []
    for row in cursor.fetchall():
        all_wins.extend([w.strip() for w in row['wins'].split(',') if w.strip()])
    
    # Count win frequencies
    win_counts = {}
    for w in all_wins:
        win_counts[w] = win_counts.get(w, 0) + 1
    top_wins = sorted(win_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Days with entries vs total days
    cursor.execute("""
        SELECT COUNT(DISTINCT date) as days_active
        FROM life_os_journal WHERE date >= ?
    """, (from_date,))
    days_active = cursor.fetchone()['days_active']
    
    # Streak calculation (consecutive days with entries)
    cursor.execute("""
        SELECT DISTINCT date FROM life_os_journal 
        WHERE date >= ? ORDER BY date DESC
    """, (from_date,))
    dates = [row['date'] for row in cursor.fetchall()]
    
    streak = 0
    today = datetime.now().strftime("%Y-%m-%d")
    check_date = today
    for d in dates:
        if d == check_date:
            streak += 1
            # Previous day
            from datetime import timedelta
            prev = datetime.strptime(check_date, "%Y-%m-%d") - timedelta(days=1)
            check_date = prev.strftime("%Y-%m-%d")
        else:
            break
    
    conn.close()
    
    return {
        "period_days": days,
        "total_entries": total,
        "days_active": days_active,
        "response_rate": round(days_active / max(days, 1) * 100, 1),
        "current_streak": streak,
        "energy_trend": energy_trend,
        "by_message": by_message,
        "top_wins": [{"win": w, "count": c} for w, c in top_wins],
        "avg_energy": round(sum(e.get('avg_energy', 0) or 0 for e in energy_trend) / max(len(energy_trend), 1), 1) if energy_trend else None
    }

@app.post("/api/scheduled-messages/seed-life-os")
async def seed_life_os_messages(request: Request):
    """Seeds all Life Operating System scheduled messages (idempotent)"""
    verify_atlas_key(request)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Clear existing life_os messages to make this idempotent
    cursor.execute("DELETE FROM scheduled_messages WHERE category = 'life_os'")
    
    messages = [
        # Daily messages (Mon-Fri = 1,2,3,4,5)
        ("morning_energy", "Bom dia, Fabio! Qual sua energia hoje (1-5)? Quais sao as 3 coisas mais importantes pra hoje? Circula a UNICA que mais importa.", "08:30", "1,2,3,4,5", "high", "life_os"),
        ("sprint1_done", "Primeiro sprint completo! O que voce entregou nessa primeira sessao de foco?", "10:00", "1,2,3,4,5", "normal", "life_os"),
        ("lunch_break", "Hora do almoco. Come longe do computador. Respira.", "12:00", "1,2,3,4,5", "normal", "life_os"),
        ("wins_journal", "Hora de registrar. Quais 3 coisas voce REALIZOU hoje? (Nao o que faltou -- o que voce FEZ)", "16:30", "1,2,3,4,5", "high", "life_os"),
        ("work_stop", "Voce parou de trabalhar? Lembre-se: seu terapeuta disse pra nao trabalhar fora do horario. O que voce vai fazer agora que NAO e trabalho?", "18:00", "1,2,3,4,5", "high", "life_os"),
        # Daily messages (every day including weekends)
        ("meditation_night", "Meditacao noturna. 15 minutos. Muse Athena. Sem desculpa, Fabio.", "21:00", "1,2,3,4,5,6,7", "normal", "life_os"),
        ("phone_away", "Celular em outro comodo. Roupa da academia separada. Boa noite, Fabio.", "22:00", "1,2,3,4,5,6,7", "normal", "life_os"),
        # Weekly messages
        ("sunday_planning", "Hora do planejamento semanal! Antes de planejar, me conta: quais foram suas 3 VITORIAS essa semana? Celebra antes de cobrar.", "19:00", "7", "high", "life_os"),
        ("wednesday_mba", "MBA check: tem algum deadline essa semana? Algum material pra revisar? Nao deixa pra ultima hora.", "12:00", "3", "normal", "life_os"),
        ("friday_review", "Revisao da semana. O que FUNCIONOU no seu sistema? O que precisa ajustar? Sem julgamento, so dados.", "16:00", "5", "high", "life_os"),
        # Weekend messages
        ("weekend_morning", "Bom dia! Fim de semana e pra descansar e recarregar. Qual o UNICO projeto pessoal que voce quer avancar hoje? (max 4h)", "09:00", "6,7", "normal", "life_os"),
    ]
    
    for name, message, time, days, priority, category in messages:
        cursor.execute("""
            INSERT INTO scheduled_messages (name, message, time, days, priority, category)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, message, time, days, priority, category))
    
    conn.commit()
    count = len(messages)
    conn.close()
    
    return {"message": f"Life OS seeded with {count} scheduled messages", "count": count}

# ============================================
# NOTES ROUTES
# ============================================

@app.get("/api/notes", response_model=List[dict])
async def get_notes(limit: int = 10):
    """Lista notas recentes"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM notes ORDER BY created_at DESC LIMIT ?", (limit,))
    notes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notes

@app.post("/api/notes", response_model=dict)
async def create_note(note: NoteCreate):
    """Cria uma nova nota"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO notes (title, content, meeting_date, tags, project_id)
        VALUES (?, ?, ?, ?, ?)
    """, (note.title, note.content, note.meeting_date, note.tags, note.project_id))
    
    note_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
    new_note = dict(cursor.fetchone())
    conn.close()
    
    return new_note

@app.put("/api/notes/{note_id}", response_model=dict)
async def update_note(note_id: int, note: NoteCreate):
    """Atualiza uma nota"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE notes SET title = ?, content = ?, meeting_date = ?, tags = ?, updated_at = ?
        WHERE id = ?
    """, (note.title, note.content, note.meeting_date, note.tags, datetime.now().isoformat(), note_id))
    
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Note not found")
    
    conn.commit()
    
    cursor.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
    updated_note = dict(cursor.fetchone())
    conn.close()
    
    return updated_note

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int):
    """Deleta uma nota"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Note not found")
    
    conn.commit()
    conn.close()
    return {"message": "Note deleted"}

# ============================================
# TODAY ROUTES (RESUMO DO DIA)
# ============================================

@app.get("/api/today")
async def get_today_summary():
    """Retorna resumo do dia atual"""
    conn = get_db()
    cursor = conn.cursor()
    
    today = date.today().isoformat()
    
    # Tarefas em andamento
    cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE status = 'doing'")
    doing_count = cursor.fetchone()['count']
    
    # Tarefas pendentes
    cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE status = 'todo'")
    todo_count = cursor.fetchone()['count']
    
    # Tarefas concluídas hoje
    cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE status = 'done' AND date(updated_at) = ?", (today,))
    done_today = cursor.fetchone()['count']
    
    # Lembretes de hoje
    cursor.execute("""
        SELECT * FROM reminders 
        WHERE date(due_datetime) = ? AND is_completed = 0
        ORDER BY due_datetime ASC
    """, (today,))
    today_reminders = [dict(row) for row in cursor.fetchall()]
    
    # Eventos do banco local
    cursor.execute("""
        SELECT * FROM events 
        WHERE event_date = ?
        ORDER BY event_time ASC
    """, (today,))
    local_events = [dict(row) for row in cursor.fetchall()]
    
    # Eventos do Google Calendar
    calendar_events = cal_get_today_events()
    
    # Combinar eventos (calendar primeiro, depois locais)
    all_events = calendar_events + local_events
    
    # Tarefas urgentes
    cursor.execute("""
        SELECT * FROM tasks 
        WHERE priority = 'urgent' AND status != 'done'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    urgent_tasks = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "date": today,
        "stats": {
            "todo": todo_count,
            "doing": doing_count,
            "done_today": done_today
        },
        "reminders": today_reminders,
        "events": all_events,
        "calendar_events": calendar_events,
        "urgent_tasks": urgent_tasks
    }

# ============================================
# EVENTS ROUTES
# ============================================

@app.get("/api/events", response_model=List[dict])
async def get_events(date: Optional[str] = None):
    """Lista eventos, opcionalmente filtrados por data"""
    conn = get_db()
    cursor = conn.cursor()
    
    if date:
        cursor.execute("SELECT * FROM events WHERE event_date = ? ORDER BY event_time ASC", (date,))
    else:
        cursor.execute("SELECT * FROM events ORDER BY event_date DESC, event_time ASC")
    
    events = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return events

@app.post("/api/events", response_model=dict)
async def create_event(event: EventCreate):
    """Cria um novo evento"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO events (title, description, event_date, event_time, event_type)
        VALUES (?, ?, ?, ?, ?)
    """, (event.title, event.description, event.event_date, event.event_time, event.event_type))
    
    event_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    new_event = dict(cursor.fetchone())
    conn.close()
    
    return new_event

@app.delete("/api/events/{event_id}")
async def delete_event(event_id: int):
    """Deleta um evento"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    
    conn.commit()
    conn.close()
    return {"message": "Event deleted"}

# ============================================
# PROJECTS ROUTES
# ============================================

@app.get("/api/projects", response_model=List[dict])
async def get_projects(status: Optional[str] = None, category: Optional[str] = None):
    """Lista projetos, opcionalmente filtrados por status ou categoria"""
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM projects"
    params = []
    conditions = []
    
    if status:
        conditions.append("status = ?")
        params.append(status)
    if category:
        conditions.append("category = ?")
        params.append(category)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY priority DESC, updated_at DESC"
    
    cursor.execute(query, params)
    projects = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return projects

@app.post("/api/projects", response_model=dict)
async def create_project(project: ProjectCreate):
    """Cria um novo projeto"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO projects (name, description, status, priority, progress, category, due_date, tags, nova_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (project.name, project.description, project.status, project.priority, 
          project.progress, project.category, project.due_date, project.tags, project.nova_notes))
    
    project_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    new_project = dict(cursor.fetchone())
    conn.close()
    
    return new_project

@app.get("/api/projects/{project_id}", response_model=dict)
async def get_project(project_id: int):
    """Obtém um projeto específico"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    project = cursor.fetchone()
    conn.close()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return dict(project)

@app.put("/api/projects/{project_id}", response_model=dict)
async def update_project(project_id: int, project: ProjectUpdate):
    """Atualiza um projeto"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Verificar se existe
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Atualizar campos fornecidos
    updates = []
    values = []
    for field, value in project.model_dump(exclude_unset=True).items():
        if value is not None:
            updates.append(f"{field} = ?")
            values.append(value)
    
    if updates:
        updates.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(project_id)
        
        cursor.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    updated_project = dict(cursor.fetchone())
    conn.close()
    
    return updated_project

@app.put("/api/projects/{project_id}/progress", response_model=dict)
async def update_project_progress(project_id: int, progress: int):
    """Atualiza apenas o progresso de um projeto (0-100)"""
    if progress < 0 or progress > 100:
        raise HTTPException(status_code=400, detail="Progress must be between 0 and 100")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Auto-complete if progress reaches 100
    status_update = ", status = 'completed'" if progress == 100 else ""
    
    cursor.execute(f"""
        UPDATE projects SET progress = ?, updated_at = ?{status_update} WHERE id = ?
    """, (progress, datetime.now().isoformat(), project_id))
    
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")
    
    conn.commit()
    
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    updated_project = dict(cursor.fetchone())
    conn.close()
    
    return updated_project

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int):
    """Deleta um projeto"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")
    
    conn.commit()
    conn.close()
    return {"message": "Project deleted"}

@app.get("/api/projects/{project_id}/full")
async def get_project_full(project_id: int):
    """Obtém projeto completo com tasks, notes e docs"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Projeto
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    project = cursor.fetchone()
    if not project:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")
    
    project_dict = dict(project)
    
    # Tasks do projeto
    cursor.execute("SELECT * FROM tasks WHERE project_id = ? ORDER BY priority DESC, created_at DESC", (project_id,))
    tasks = [dict(row) for row in cursor.fetchall()]
    
    # Notes do projeto
    cursor.execute("SELECT * FROM notes WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    notes = [dict(row) for row in cursor.fetchall()]
    
    # Docs do projeto
    cursor.execute("SELECT * FROM project_docs WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    docs = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "project": project_dict,
        "tasks": tasks,
        "notes": notes,
        "docs": docs,
        "stats": {
            "total_tasks": len(tasks),
            "tasks_done": len([t for t in tasks if t.get('status') == 'done']),
            "tasks_doing": len([t for t in tasks if t.get('status') == 'doing']),
            "tasks_todo": len([t for t in tasks if t.get('status') == 'todo']),
            "total_notes": len(notes),
            "total_docs": len(docs)
        }
    }

# ============================================
# PROJECT DOCS ROUTES
# ============================================

@app.get("/api/projects/{project_id}/docs")
async def get_project_docs(project_id: int):
    """Lista documentos de um projeto"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM project_docs WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    docs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return docs

@app.post("/api/projects/{project_id}/docs")
async def add_project_doc(project_id: int, title: str, url: str = None, doc_type: str = "link", description: str = None, file_path: str = None):
    """Adiciona documento/link a um projeto"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Garantir que a coluna file_path existe
    try:
        cursor.execute("ALTER TABLE project_docs ADD COLUMN file_path TEXT")
        conn.commit()
    except:
        pass
    
    cursor.execute("""
        INSERT INTO project_docs (project_id, title, url, doc_type, description, file_path)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (project_id, title, url, doc_type, description, file_path))
    
    doc_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM project_docs WHERE id = ?", (doc_id,))
    new_doc = dict(cursor.fetchone())
    conn.close()
    
    return new_doc

# Mapeamento de projeto para slug de pasta
PROJECT_SLUGS = {
    'DAM - Documentação': 'dam',
    'DAM': 'dam',
    'Catalog': 'catalog',
    'CMS': 'cms',
    'MBA Inteli': 'mba',
    'Centro de Controle': 'centro-de-controle',
    'Nova + Atlas': 'nova-atlas'
}

PROJECTS_BASE_PATH = '/root/Nova/projects'

@app.get("/api/projects/{project_id}/files")
async def get_project_files(project_id: int):
    """Lista todos os arquivos de um projeto (escaneando pasta)"""
    import os
    import glob
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM projects WHERE id = ?", (project_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project_name = result[0]
    slug = PROJECT_SLUGS.get(project_name, project_name.lower().replace(' ', '-'))
    project_path = f"{PROJECTS_BASE_PATH}/{slug}"
    
    if not os.path.exists(project_path):
        return {"files": [], "path": project_path, "exists": False}
    
    files = []
    
    # Escanear arquivos .md
    for root, dirs, filenames in os.walk(project_path):
        for filename in filenames:
            if filename.endswith('.md') or filename.endswith('.json'):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, project_path)
                stat = os.stat(full_path)
                
                # Determinar tipo baseado na pasta
                if '/drafts/' in full_path or rel_path.startswith('drafts/'):
                    file_type = 'draft'
                elif '/notes/' in full_path or rel_path.startswith('notes/'):
                    file_type = 'note'
                elif '/docs/' in full_path or rel_path.startswith('docs/'):
                    file_type = 'doc'
                elif filename == 'epic.md':
                    file_type = 'epic'
                else:
                    file_type = 'file'
                
                files.append({
                    "name": filename,
                    "path": rel_path,
                    "full_path": full_path,
                    "type": file_type,
                    "size": stat.st_size,
                    "modified": stat.st_mtime
                })
    
    # Ordenar: épico primeiro, depois por data de modificação
    files.sort(key=lambda x: (x['type'] != 'epic', -x['modified']))
    
    return {"files": files, "path": project_path, "exists": True, "slug": slug}

@app.get("/api/projects/files/{file_path:path}")
async def read_project_file(file_path: str):
    """Lê conteúdo de um arquivo de projeto"""
    import os
    
    # Garantir que está dentro da pasta de projetos
    full_path = f"{PROJECTS_BASE_PATH}/{file_path}"
    
    if not full_path.startswith(PROJECTS_BASE_PATH):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        stat = os.stat(full_path)
        return {
            "content": content,
            "path": file_path,
            "modified": stat.st_mtime,
            "size": stat.st_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}/docs/{doc_id}/content")
async def get_doc_content(project_id: int, doc_id: int):
    """Retorna conteúdo de um documento .md"""
    import os
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM project_docs WHERE id = ? AND project_id = ?", (doc_id, project_id))
    doc = cursor.fetchone()
    conn.close()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = dict(doc)
    file_path = doc.get('file_path')
    
    if not file_path or not os.path.exists(file_path):
        return {"content": None, "error": "Arquivo não encontrado"}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {"content": content, "file_path": file_path, "title": doc['title']}
    except Exception as e:
        return {"content": None, "error": str(e)}

@app.delete("/api/projects/{project_id}/docs/{doc_id}")
async def delete_project_doc(project_id: int, doc_id: int):
    """Remove documento de um projeto"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM project_docs WHERE id = ? AND project_id = ?", (doc_id, project_id))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")
    conn.commit()
    conn.close()
    return {"message": "Document deleted"}

# ============================================
# CALENDAR ROUTES (Google Calendar Integration)
# ============================================

@app.get("/api/calendar/today")
async def get_calendar_today():
    """Retorna eventos de hoje do Google Calendar - retorna array direto para compatibilidade com frontend"""
    events = cal_get_today_events()
    # Retornar array direto (frontend espera isso)
    return events

@app.get("/api/calendar/week")
async def get_calendar_week():
    """Retorna eventos da semana agrupados por dia"""
    events_by_day = cal_get_week_events()
    return {
        "start_date": date.today().isoformat(),
        "events_by_day": events_by_day,
        "total_events": sum(len(evts) for evts in events_by_day.values())
    }

@app.get("/api/calendar/date/{target_date}")
async def get_calendar_date(target_date: str):
    """Retorna eventos de uma data específica (YYYY-MM-DD)"""
    events = cal_get_events_for_date(target_date)
    return {
        "date": target_date,
        "events": events,
        "count": len(events)
    }

@app.get("/api/calendar/upcoming")
async def get_calendar_upcoming(days: int = 7):
    """Retorna próximos eventos"""
    if days > 30:
        days = 30  # Limitar a 30 dias
    events = fetch_calendar_events(days_ahead=days)
    return {
        "days_ahead": days,
        "events": events,
        "count": len(events)
    }

# ============================================
# MBA / ADALOVE ROUTES
# ============================================

# Caminhos para dados do Adalove
ADALOVE_DATA_PATH_LOCAL = "/home/fabio/Documents/Nova/openclaw-workspace/docs/mba/adalove-data.json"
ADALOVE_DATA_PATH_VPS = "/root/Nova/openclaw-workspace/docs/mba/adalove-data.json"
ADALOVE_MATERIAIS_PATH = "/root/Nova/openclaw-workspace/docs/mba/materiais"

def get_adalove_data_path():
    """Retorna o caminho correto para o arquivo de dados do Adalove"""
    if os.path.exists(ADALOVE_DATA_PATH_VPS):
        return ADALOVE_DATA_PATH_VPS
    elif os.path.exists(ADALOVE_DATA_PATH_LOCAL):
        return ADALOVE_DATA_PATH_LOCAL
    return None

@app.get("/api/mba/data")
async def get_mba_data():
    """Retorna dados do Adalove (MBA)"""
    data_path = get_adalove_data_path()
    
    if not data_path or not os.path.exists(data_path):
        raise HTTPException(
            status_code=404, 
            detail="Dados do Adalove não encontrados. Execute a sincronização primeiro."
        )
    
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro: {str(e)}")


@app.get("/api/mba/stats")
async def get_mba_stats():
    """Retorna estatísticas resumidas do MBA para o dashboard"""
    data_path = get_adalove_data_path()
    
    # Valores padrão
    stats = {
        "pendentes": 0,
        "em_andamento": 0,
        "concluidas": 0,
        "proximos_prazos": [],
        "total_atividades": 0
    }
    
    if not data_path or not os.path.exists(data_path):
        # Retornar zeros se não houver dados
        return stats
    
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Calcular estatísticas das turmas
        for turma in data.get('turmas', []):
            for semana in turma.get('semanas', []):
                atividades = semana.get('atividades', {})
                stats["pendentes"] += len(atividades.get('a_fazer', []))
                stats["em_andamento"] += len(atividades.get('fazendo', []))
                stats["concluidas"] += len(atividades.get('feito', []))
                
                # Coletar próximos prazos
                for atividade in atividades.get('a_fazer', []):
                    if atividade.get('prazo'):
                        stats["proximos_prazos"].append({
                            "title": atividade.get('titulo', 'Atividade'),
                            "due_date": atividade.get('prazo'),
                            "turma": turma.get('nome', '')
                        })
        
        stats["total_atividades"] = stats["pendentes"] + stats["em_andamento"] + stats["concluidas"]
        
        # Ordenar próximos prazos e pegar os 5 mais próximos
        stats["proximos_prazos"] = sorted(
            stats["proximos_prazos"], 
            key=lambda x: x.get('due_date', '9999')
        )[:5]
        
        return stats
    except Exception as e:
        print(f"Error loading MBA stats: {e}")
        return stats

@app.post("/api/mba/sync")
async def sync_mba_data():
    """Solicita sincronização dos dados do Adalove
    
    Este endpoint notifica que uma sincronização é necessária.
    A sincronização real é feita pelo Atlas (Cursor) via Playwright.
    """
    # Por enquanto, apenas retorna uma mensagem
    # Futuramente pode enviar uma notificação para a Nova escalar para o Cursor
    return {
        "message": "Sincronização solicitada. O Atlas (Cursor) irá atualizar os dados em breve.",
        "status": "pending",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/mba/materials")
async def list_mba_materials():
    """Lista materiais baixados do Adalove"""
    materials = []
    
    materiais_path = ADALOVE_MATERIAIS_PATH
    if not os.path.exists(ADALOVE_MATERIAIS_PATH):
        # Tentar caminho local
        materiais_path = "/home/fabio/Documents/Nova/openclaw-workspace/docs/mba/materiais"
    
    if not os.path.exists(materiais_path):
        return {"materials": [], "path": materiais_path, "exists": False}
    
    for root, dirs, files in os.walk(materiais_path):
        for filename in files:
            if filename.endswith(('.pdf', '.mp4', '.docx', '.pptx')):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, materiais_path)
                stat = os.stat(full_path)
                
                ext = filename.split('.')[-1].lower()
                file_type = 'pdf' if ext == 'pdf' else \
                           'video' if ext == 'mp4' else \
                           'doc' if ext in ['docx', 'pptx'] else 'file'
                
                materials.append({
                    "name": filename,
                    "path": rel_path,
                    "full_path": full_path,
                    "type": file_type,
                    "size": stat.st_size,
                    "modified": stat.st_mtime
                })
    
    materials.sort(key=lambda x: -x['modified'])
    
    return {"materials": materials, "path": materiais_path, "exists": True}

@app.get("/api/mba/materials/{file_path:path}")
async def download_mba_material(file_path: str):
    """Download de material do MBA"""
    materiais_path = ADALOVE_MATERIAIS_PATH
    if not os.path.exists(ADALOVE_MATERIAIS_PATH):
        materiais_path = "/home/fabio/Documents/Nova/openclaw-workspace/docs/mba/materiais"
    
    full_path = os.path.join(materiais_path, file_path)
    
    if not full_path.startswith(materiais_path):
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Material não encontrado")
    
    return FileResponse(
        path=full_path,
        filename=os.path.basename(file_path),
        media_type='application/octet-stream'
    )

@app.post("/api/mba/data")
async def update_mba_data(data: dict):
    """Atualiza dados do Adalove (usado pelo script de extração)"""
    data_path = ADALOVE_DATA_PATH_VPS
    if not os.path.exists(os.path.dirname(ADALOVE_DATA_PATH_VPS)):
        data_path = ADALOVE_DATA_PATH_LOCAL
    
    # Garantir que o diretório existe
    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    
    try:
        # Adicionar timestamp de sincronização
        data['last_sync'] = datetime.now().isoformat() + 'Z'
        
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return {
            "message": "Dados atualizados com sucesso",
            "path": data_path,
            "timestamp": data['last_sync']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar dados: {str(e)}")

# ============================================
# HEALTH CHECK
# ============================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "centro-de-controle",
        "timestamp": datetime.now().isoformat()
    }

# ============================================
# STATIC FILES (FRONTEND)
# ============================================

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

# Mount static directories for CSS, JS, and assets
if os.path.exists(FRONTEND_DIR):
    css_dir = os.path.join(FRONTEND_DIR, "css")
    js_dir = os.path.join(FRONTEND_DIR, "js")
    assets_dir = os.path.join(FRONTEND_DIR, "assets")
    
    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.exists(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

@app.get("/")
async def serve_frontend():
    """Serve o frontend"""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend not found. API available at /api/"}

@app.get("/project")
async def serve_project_page():
    """Serve a página de detalhes do projeto"""
    project_path = os.path.join(FRONTEND_DIR, "project.html")
    if os.path.exists(project_path):
        return FileResponse(project_path)
    return {"message": "Project page not found"}

@app.get("/files")
async def serve_files_page():
    """Serve a página de arquivos compartilhados"""
    files_path = os.path.join(FRONTEND_DIR, "files.html")
    if os.path.exists(files_path):
        return FileResponse(files_path)
    return {"message": "Files page not found"}

@app.get("/work")
async def serve_work_page():
    """Serve a página de Work Status"""
    work_path = os.path.join(FRONTEND_DIR, "work.html")
    if os.path.exists(work_path):
        return FileResponse(work_path)
    return {"message": "Work page not found"}

@app.get("/mba")
async def serve_mba_page():
    """Serve a página do MBA"""
    mba_path = os.path.join(FRONTEND_DIR, "mba.html")
    if os.path.exists(mba_path):
        return FileResponse(mba_path)
    return {"message": "MBA page not found"}

@app.get("/portfolio")
async def serve_portfolio_page():
    """Serve a página de Portfolio"""
    portfolio_path = os.path.join(FRONTEND_DIR, "portfolio.html")
    if os.path.exists(portfolio_path):
        return FileResponse(portfolio_path)
    return {"message": "Portfolio page not found"}

@app.get("/login")
async def serve_login_page():
    """Serve a página de Login"""
    login_path = os.path.join(FRONTEND_DIR, "login.html")
    if os.path.exists(login_path):
        return FileResponse(login_path)
    return {"message": "Login page not found"}

@app.get("/manifest.json")
async def serve_manifest():
    """Serve PWA manifest"""
    manifest_path = os.path.join(FRONTEND_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        return FileResponse(manifest_path)
    raise HTTPException(status_code=404, detail="Manifest not found")

# ============================================
# FILE UPLOAD/SHARING
# ============================================

UPLOADS_DIR = "/root/Nova/uploads"

# Garantir que pasta existe
os.makedirs(UPLOADS_DIR, exist_ok=True)

@app.get("/api/files")
async def list_uploaded_files():
    """Lista todos os arquivos compartilhados"""
    files = []
    
    if os.path.exists(UPLOADS_DIR):
        for filename in os.listdir(UPLOADS_DIR):
            file_path = os.path.join(UPLOADS_DIR, filename)
            if os.path.isfile(file_path):
                stat = os.stat(file_path)
                
                # Determinar tipo pelo extensão
                ext = filename.split('.')[-1].lower() if '.' in filename else ''
                file_type = 'image' if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp'] else \
                           'pdf' if ext == 'pdf' else \
                           'doc' if ext in ['doc', 'docx', 'md', 'txt'] else \
                           'sheet' if ext in ['xls', 'xlsx', 'csv'] else 'file'
                
                files.append({
                    "name": filename,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "type": file_type,
                    "ext": ext
                })
    
    # Ordenar por data de modificação (mais recente primeiro)
    files.sort(key=lambda x: -x['modified'])
    
    return {"files": files, "total": len(files)}

@app.post("/api/files/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload de arquivo para compartilhamento"""
    
    # Validar tamanho (max 50MB)
    MAX_SIZE = 50 * 1024 * 1024
    
    # Gerar nome único se já existir
    original_name = file.filename
    safe_name = original_name.replace(' ', '_')
    file_path = os.path.join(UPLOADS_DIR, safe_name)
    
    # Se arquivo já existe, adicionar sufixo
    if os.path.exists(file_path):
        name, ext = os.path.splitext(safe_name)
        safe_name = f"{name}_{uuid.uuid4().hex[:6]}{ext}"
        file_path = os.path.join(UPLOADS_DIR, safe_name)
    
    try:
        # Salvar arquivo
        with open(file_path, "wb") as buffer:
            content = await file.read()
            if len(content) > MAX_SIZE:
                raise HTTPException(status_code=413, detail="Arquivo muito grande (max 50MB)")
            buffer.write(content)
        
        stat = os.stat(file_path)
        
        return {
            "message": "Upload realizado com sucesso",
            "filename": safe_name,
            "original_name": original_name,
            "size": stat.st_size,
            "path": file_path
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no upload: {str(e)}")

@app.get("/api/files/download/{filename}")
async def download_file(filename: str):
    """Download de arquivo compartilhado"""
    file_path = os.path.join(UPLOADS_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )

@app.delete("/api/files/{filename}")
async def delete_uploaded_file(filename: str):
    """Remove arquivo compartilhado"""
    file_path = os.path.join(UPLOADS_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    try:
        os.remove(file_path)
        return {"message": "Arquivo removido", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover: {str(e)}")

# ============================================
# WORK PROJECTS (Projetos de Trabalho)
# ============================================

# Work Projects path - detect environment
_LOCAL_WORK_PATH = '/home/fabio/Documents/Nova/openclaw-workspace/docs/trabalho/projetos'
_SERVER_WORK_PATH = '/root/Nova/openclaw-workspace/docs/trabalho/projetos'
WORK_PROJECTS_PATH = _LOCAL_WORK_PATH if os.path.exists(_LOCAL_WORK_PATH) else _SERVER_WORK_PATH

WORK_PROJECTS_MAP = {
    "3tpm": {"folder": "3TPM", "type": "multi"},
    "catalog-admin": {"file": "CATALOG-ADMIN.md", "type": "single"},
    "company-store": {"file": "COMPANY-STORE.md", "type": "single"},
    "cms-dam": {"file": "CMS-DAM-STRATEGY.md", "type": "single"},
    "pocs-ia": {"file": "POCS-IA.md", "type": "single"},
    "autonomy": {"file": "AUTONOMY-AUTOMATION.md", "type": "single"}
}

def parse_markdown_file(file_path: str) -> dict:
    """Extrai resumo, headers e conteudo estruturado de um arquivo .md"""
    import re
    
    if not os.path.exists(file_path):
        return {"error": "File not found", "content": "", "summary": "", "sections": []}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extrair título (primeiro # )
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_match.group(1) if title_match else os.path.basename(file_path).replace('.md', '')
    
    # Extrair resumo (primeiro parágrafo após o título, ignorando metadata)
    # Remove frontmatter e metadata
    clean_content = re.sub(r'^>\s+\*\*.+\*\*.*$', '', content, flags=re.MULTILINE)
    clean_content = re.sub(r'^---$', '', clean_content, flags=re.MULTILINE)
    
    # Pegar primeiro parágrafo substancial
    paragraphs = re.split(r'\n\n+', clean_content)
    summary = ""
    for p in paragraphs:
        p = p.strip()
        # Ignorar headers, listas, tabelas
        if p and not p.startswith('#') and not p.startswith('-') and not p.startswith('|') and not p.startswith('>') and len(p) > 50:
            summary = p[:300] + "..." if len(p) > 300 else p
            break
    
    # Extrair seções (## headers)
    sections = []
    section_matches = re.findall(r'^##\s+(.+)$', content, re.MULTILINE)
    for section_name in section_matches:
        sections.append(section_name.strip())
    
    # Extrair status se existir
    status_match = re.search(r'\*\*Status:\*\*\s*(.+)', content)
    status = status_match.group(1).strip() if status_match else None
    
    # Extrair última atualização
    updated_match = re.search(r'\*\*Ultima atualizacao:\*\*\s*(.+)', content)
    last_updated = updated_match.group(1).strip() if updated_match else None
    
    return {
        "title": title,
        "content": content,
        "summary": summary,
        "sections": sections,
        "status": status,
        "last_updated": last_updated
    }

def get_multi_project_data(project_folder: str) -> dict:
    """Extrai dados de um projeto multi-arquivo (como 3TPM)"""
    import os
    import re
    
    project_path = os.path.join(WORK_PROJECTS_PATH, project_folder)
    
    if not os.path.exists(project_path):
        return {"error": "Project folder not found"}
    
    result = {
        "name": project_folder,
        "type": "multi",
        "path": project_path,
        "overview": {},
        "sections": [],
        "meeting_notes": [],
        "files": []
    }
    
    # Mapear arquivos conhecidos
    file_mapping = {
        "00-contexto-fabio.md": "context",
        "01-definicao.md": "definition",
        "02-historia.md": "history",
        "03-arquitetura.md": "architecture",
        "04-pessoas.md": "people",
        "05-timeline.md": "timeline",
        "06-status.md": "status",
        "07-roadmap.md": "roadmap",
        "README.md": "readme"
    }
    
    section_names = {
        "context": "Contexto",
        "definition": "Definição",
        "history": "História",
        "architecture": "Arquitetura",
        "people": "Pessoas",
        "timeline": "Timeline",
        "status": "Status",
        "roadmap": "Roadmap",
        "readme": "README"
    }
    
    # Processar arquivos principais
    for filename in sorted(os.listdir(project_path)):
        file_path = os.path.join(project_path, filename)
        
        if os.path.isfile(file_path) and filename.endswith('.md'):
            parsed = parse_markdown_file(file_path)
            stat = os.stat(file_path)
            
            section_key = file_mapping.get(filename)
            
            file_info = {
                "name": filename,
                "path": filename,
                "title": parsed["title"],
                "summary": parsed["summary"],
                "sections": parsed["sections"],
                "status": parsed.get("status"),
                "last_updated": parsed.get("last_updated"),
                "modified": stat.st_mtime,
                "section_key": section_key
            }
            
            result["files"].append(file_info)
            
            # Adicionar às seções se mapeado
            if section_key:
                result["sections"].append({
                    "key": section_key,
                    "name": section_names.get(section_key, filename),
                    "file": filename,
                    "summary": parsed["summary"],
                    "status": parsed.get("status")
                })
                
                # Adicionar ao overview
                if section_key == "definition":
                    result["overview"]["definition"] = parsed["summary"]
                elif section_key == "context":
                    result["overview"]["context"] = parsed["summary"]
                elif section_key == "status":
                    result["overview"]["current_status"] = parsed["summary"]
                    result["overview"]["status_raw"] = parsed.get("status")
    
    # Processar notas de reunião
    notes_path = os.path.join(project_path, "notes")
    if os.path.exists(notes_path):
        for filename in sorted(os.listdir(notes_path), reverse=True):  # Mais recentes primeiro
            if filename.endswith('.md'):
                file_path = os.path.join(notes_path, filename)
                parsed = parse_markdown_file(file_path)
                stat = os.stat(file_path)
                
                # Extrair data do nome do arquivo (formato: 2026-02-05-titulo.md)
                date_match = re.match(r'^(\d{4}-\d{2}-\d{2})-(.+)\.md$', filename)
                if date_match:
                    note_date = date_match.group(1)
                    note_title = date_match.group(2).replace('-', ' ').title()
                else:
                    note_date = None
                    note_title = parsed["title"]
                
                result["meeting_notes"].append({
                    "title": note_title,
                    "date": note_date,
                    "file": f"notes/{filename}",
                    "preview": parsed["summary"][:200] if parsed["summary"] else "",
                    "modified": stat.st_mtime
                })
    
    # Processar cases se existir
    cases_path = os.path.join(project_path, "cases")
    if os.path.exists(cases_path):
        result["cases"] = []
        for filename in sorted(os.listdir(cases_path)):
            if filename.endswith('.md'):
                file_path = os.path.join(cases_path, filename)
                parsed = parse_markdown_file(file_path)
                result["cases"].append({
                    "title": parsed["title"],
                    "file": f"cases/{filename}",
                    "summary": parsed["summary"]
                })
    
    return result

def get_single_project_data(project_file: str) -> dict:
    """Extrai dados de um projeto single-file"""
    import os
    
    file_path = os.path.join(WORK_PROJECTS_PATH, project_file)
    
    if not os.path.exists(file_path):
        return {"error": "Project file not found"}
    
    parsed = parse_markdown_file(file_path)
    stat = os.stat(file_path)
    
    return {
        "name": parsed["title"],
        "type": "single",
        "path": file_path,
        "overview": {
            "definition": parsed["summary"],
            "current_status": parsed.get("status")
        },
        "sections": [{"name": s, "summary": ""} for s in parsed["sections"]],
        "content": parsed["content"],
        "meeting_notes": [],
        "modified": stat.st_mtime
    }

@app.get("/api/work-projects")
async def list_work_projects():
    """Lista todos os projetos de trabalho disponíveis"""
    import os
    
    projects = []
    
    for slug, config in WORK_PROJECTS_MAP.items():
        if config["type"] == "multi":
            folder_path = os.path.join(WORK_PROJECTS_PATH, config["folder"])
            exists = os.path.exists(folder_path)
            name = config["folder"]
        else:
            file_path = os.path.join(WORK_PROJECTS_PATH, config["file"])
            exists = os.path.exists(file_path)
            name = config["file"].replace('.md', '')
        
        projects.append({
            "slug": slug,
            "name": name,
            "type": config["type"],
            "exists": exists
        })
    
    return {"projects": projects}

@app.get("/api/work-projects/{slug}")
async def get_work_project(slug: str):
    """Retorna dados interpretados de um projeto de trabalho"""
    
    slug_lower = slug.lower()
    
    if slug_lower not in WORK_PROJECTS_MAP:
        raise HTTPException(status_code=404, detail=f"Work project '{slug}' not found")
    
    config = WORK_PROJECTS_MAP[slug_lower]
    
    if config["type"] == "multi":
        data = get_multi_project_data(config["folder"])
    else:
        data = get_single_project_data(config["file"])
    
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    
    return data

@app.get("/api/work-projects/{slug}/file/{file_path:path}")
async def get_work_project_file(slug: str, file_path: str):
    """Retorna conteúdo de um arquivo específico do projeto"""
    import os
    
    slug_lower = slug.lower()
    
    if slug_lower not in WORK_PROJECTS_MAP:
        raise HTTPException(status_code=404, detail=f"Work project '{slug}' not found")
    
    config = WORK_PROJECTS_MAP[slug_lower]
    
    if config["type"] == "multi":
        base_path = os.path.join(WORK_PROJECTS_PATH, config["folder"])
        full_path = os.path.join(base_path, file_path)
    else:
        full_path = os.path.join(WORK_PROJECTS_PATH, config["file"])
    
    # Verificar que está dentro do projeto
    if not full_path.startswith(WORK_PROJECTS_PATH):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    parsed = parse_markdown_file(full_path)
    stat = os.stat(full_path)
    
    return {
        "title": parsed["title"],
        "content": parsed["content"],
        "summary": parsed["summary"],
        "sections": parsed["sections"],
        "modified": stat.st_mtime
    }

# ============================================
# UPDATES ENDPOINT
# ============================================

@app.get("/api/updates/recent")
async def get_recent_updates(limit: int = 20):
    """
    Retorna atualizações recentes de todas as fontes.
    Combina: tarefas atualizadas, projetos modificados, reuniões, notas, lembretes
    """
    import os
    from datetime import datetime, timedelta
    
    updates = []
    now = datetime.now()
    
    # 1. Tarefas recém-atualizadas
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, status, updated_at, created_at 
            FROM tasks 
            WHERE updated_at >= datetime('now', '-7 days')
            ORDER BY updated_at DESC
            LIMIT 10
        """)
        for row in cursor.fetchall():
            task = dict(row)
            # Determinar tipo de update
            created = datetime.fromisoformat(task['created_at'].replace('Z', ''))
            updated = datetime.fromisoformat(task['updated_at'].replace('Z', ''))
            
            if (updated - created).total_seconds() < 60:
                update_type = "task_created"
                message = f"Nova tarefa criada: {task['title']}"
                icon = "➕"
            elif task['status'] == 'done':
                update_type = "task_completed"
                message = f"Tarefa concluída: {task['title']}"
                icon = "✅"
            else:
                update_type = "task_updated"
                message = f"Tarefa atualizada: {task['title']}"
                icon = "📝"
            
            updates.append({
                "type": update_type,
                "message": message,
                "icon": icon,
                "timestamp": task['updated_at'],
                "entity_type": "task",
                "entity_id": task['id']
            })
        conn.close()
    except Exception as e:
        print(f"Error fetching task updates: {e}")
    
    # 2. Projetos atualizados recentemente
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, status, updated_at
            FROM projects 
            WHERE updated_at >= datetime('now', '-7 days')
            ORDER BY updated_at DESC
            LIMIT 5
        """)
        for row in cursor.fetchall():
            project = dict(row)
            updates.append({
                "type": "project_updated",
                "message": f"Projeto atualizado: {project['name']}",
                "icon": "📊",
                "timestamp": project['updated_at'],
                "entity_type": "project",
                "entity_id": project['id']
            })
        conn.close()
    except Exception as e:
        print(f"Error fetching project updates: {e}")
    
    # 3. Notas de reunião recentes (de work projects)
    try:
        for slug, config in WORK_PROJECTS_MAP.items():
            if config["type"] == "multi":
                notes_path = os.path.join(WORK_PROJECTS_PATH, config["folder"], "notes")
                if os.path.exists(notes_path):
                    for filename in os.listdir(notes_path):
                        if filename.endswith('.md'):
                            # Extrair data do nome do arquivo
                            date_match = re.match(r'^(\d{4}-\d{2}-\d{2})-(.+)\.md$', filename)
                            if date_match:
                                note_date_str = date_match.group(1)
                                note_title = date_match.group(2).replace('-', ' ').title()
                                
                                try:
                                    note_date = datetime.strptime(note_date_str, '%Y-%m-%d')
                                    if (now - note_date).days <= 7:
                                        updates.append({
                                            "type": "meeting_note",
                                            "message": f"Reunião: {note_title} ({config['folder']})",
                                            "icon": "📅",
                                            "timestamp": note_date_str + "T12:00:00",
                                            "entity_type": "meeting",
                                            "entity_id": f"{slug}/{filename}"
                                        })
                                except:
                                    pass
    except Exception as e:
        print(f"Error fetching meeting updates: {e}")
    
    # 4. Lembretes criados/completados
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, is_completed, created_at
            FROM reminders 
            WHERE created_at >= datetime('now', '-7 days')
            ORDER BY created_at DESC
            LIMIT 5
        """)
        for row in cursor.fetchall():
            reminder = dict(row)
            update_type = "reminder_completed" if reminder['is_completed'] else "reminder_created"
            icon = "🔔" if not reminder['is_completed'] else "✓"
            updates.append({
                "type": update_type,
                "message": f"Lembrete: {reminder['title']}",
                "icon": icon,
                "timestamp": reminder['created_at'],
                "entity_type": "reminder",
                "entity_id": reminder['id']
            })
        conn.close()
    except Exception as e:
        print(f"Error fetching reminder updates: {e}")
    
    # 5. Meeting notes from database (synced from Notion)
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, date, project, summary, source, notion_url, synced_at
            FROM meeting_notes
            WHERE date >= date('now', '-7 days') OR synced_at >= datetime('now', '-7 days')
            ORDER BY date DESC
            LIMIT 20
        """)
        for row in cursor.fetchall():
            note = dict(row)
            # Avoid duplicates with file-based meeting notes
            dupe = False
            note_title_lower = note['title'].lower() if note['title'] else ''
            for existing in updates:
                if existing.get('entity_type') == 'meeting' and note_title_lower in existing.get('message', '').lower():
                    dupe = True
                    break
            if not dupe:
                updates.append({
                    "type": "meeting_note",
                    "message": f"Reuniao: {note['title']}" + (f" ({note['project']})" if note['project'] else ""),
                    "icon": "📅",
                    "timestamp": note['date'] or note['synced_at'],
                    "entity_type": "meeting",
                    "entity_id": note['id'],
                    "notion_url": note.get('notion_url', '')
                })
        conn.close()
    except Exception as e:
        print(f"Error fetching meeting_notes from DB: {e}")
    
    # Ordenar por timestamp (mais recente primeiro)
    updates.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Limitar
    updates = updates[:limit]
    
    return {
        "updates": updates,
        "count": len(updates),
        "generated_at": now.isoformat()
    }


# ============================================
# CONFLUENCE ENDPOINTS
# ============================================

@app.get("/api/confluence/sprints")
async def get_confluence_sprints():
    """Lista sprints do Confluence com o atual destacado"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM confluence_sprints 
        ORDER BY sprint_number DESC
    """)
    sprints = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Determinar sprint atual baseado na data
    today = datetime.now().date()
    for sprint in sprints:
        # Simplificado - idealmente parsear as datas
        sprint['is_current'] = bool(sprint.get('is_current'))
    
    return {"sprints": sprints, "count": len(sprints)}


@app.get("/api/confluence/initiatives")
async def get_confluence_initiatives(team: Optional[str] = None):
    """Lista initiatives filtradas por team"""
    conn = get_db()
    cursor = conn.cursor()
    
    if team:
        cursor.execute("""
            SELECT * FROM confluence_initiatives 
            WHERE UPPER(team) = UPPER(?)
            ORDER BY priority, updated_at DESC
        """, (team,))
    else:
        cursor.execute("""
            SELECT * FROM confluence_initiatives 
            ORDER BY team, priority, updated_at DESC
        """)
    
    initiatives = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Agrupar por team
    by_team = {}
    for init in initiatives:
        t = init.get('team', 'UNKNOWN')
        if t not in by_team:
            by_team[t] = []
        by_team[t].append(init)
    
    return {
        "initiatives": initiatives,
        "by_team": by_team,
        "count": len(initiatives)
    }


@app.get("/api/confluence/initiatives/{beesip_id}/epics")
async def get_initiative_epics(beesip_id: str):
    """Lista epics de uma initiative específica"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Buscar initiative
    cursor.execute("SELECT * FROM confluence_initiatives WHERE beesip_id = ?", (beesip_id,))
    initiative = cursor.fetchone()
    
    if not initiative:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Initiative {beesip_id} not found")
    
    # Buscar epics relacionados
    cursor.execute("""
        SELECT * FROM confluence_epics 
        WHERE initiative_beesip = ?
        ORDER BY sprint, status
    """, (beesip_id,))
    epics = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {
        "initiative": dict(initiative),
        "epics": epics,
        "count": len(epics)
    }


@app.get("/api/confluence/epics")
async def get_confluence_epics(sprint: Optional[str] = None, status: Optional[str] = None):
    """Lista todos os epics com filtros opcionais"""
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM confluence_epics WHERE 1=1"
    params = []
    
    if sprint:
        query += " AND sprint = ?"
        params.append(sprint)
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    query += " ORDER BY sprint, initiative_beesip"
    
    cursor.execute(query, params)
    epics = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"epics": epics, "count": len(epics)}


@app.get("/api/confluence/risks")
async def get_confluence_risks():
    """Lista risks ativos"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM confluence_risks 
        WHERE status != 'Done'
        ORDER BY gut_score DESC, priority
    """)
    risks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"risks": risks, "count": len(risks)}


@app.get("/api/confluence/bugs")
async def get_confluence_bugs(team: Optional[str] = None):
    """Lista bugs ativos"""
    conn = get_db()
    cursor = conn.cursor()
    
    if team:
        cursor.execute("""
            SELECT * FROM confluence_bugs 
            WHERE status NOT IN ('Done', 'Closed')
            AND UPPER(team) = UPPER(?)
            ORDER BY priority, updated_at DESC
        """, (team,))
    else:
        cursor.execute("""
            SELECT * FROM confluence_bugs 
            WHERE status NOT IN ('Done', 'Closed')
            ORDER BY priority, team, updated_at DESC
        """)
    
    bugs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"bugs": bugs, "count": len(bugs)}


@app.post("/api/confluence/sync")
async def trigger_confluence_sync():
    """Dispara sincronização manual com o Confluence"""
    from situation_wall_parser import fetch_and_parse
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Registrar início do sync
    cursor.execute("""
        INSERT INTO confluence_sync_status (sync_type, status, started_at)
        VALUES ('manual', 'running', ?)
    """, (datetime.now().isoformat(),))
    sync_id = cursor.lastrowid
    conn.commit()
    
    try:
        # Buscar e parsear dados
        data = fetch_and_parse()
        
        items_synced = 0
        
        # Inserir/atualizar sprints
        for sprint in data.get('sprints', []):
            cursor.execute("""
                INSERT OR REPLACE INTO confluence_sprints 
                (sprint_name, sprint_number, start_date, end_date, release_date, is_current, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                sprint['name'], sprint['number'], sprint['start_date'],
                sprint['end_date'], sprint['release_date'], sprint['is_current'],
                datetime.now().isoformat()
            ))
            items_synced += 1
        
        # Inserir/atualizar initiatives
        for init in data.get('initiatives', []):
            cursor.execute("""
                INSERT OR REPLACE INTO confluence_initiatives
                (beesip_id, title, status, priority, team, kickoff_date, zone_approval, jira_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                init['beesip_id'], init['title'], init['status'], init['priority'],
                init['team'], init.get('kickoff_date'), init.get('zone_approval'),
                init.get('jira_url'), datetime.now().isoformat()
            ))
            items_synced += 1
        
        # Inserir/atualizar epics
        for epic in data.get('epics', []):
            milestones_json = json.dumps(epic.get('milestones')) if epic.get('milestones') else None
            cursor.execute("""
                INSERT OR REPLACE INTO confluence_epics
                (beescad_id, initiative_beesip, title, status, size, sprint, milestones, jira_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                epic['beescad_id'], epic.get('initiative_beesip'), epic['title'],
                epic['status'], epic['size'], epic.get('sprint'), milestones_json,
                epic.get('jira_url'), datetime.now().isoformat()
            ))
            items_synced += 1
        
        # Inserir/atualizar risks
        for risk in data.get('risks', []):
            cursor.execute("""
                INSERT OR REPLACE INTO confluence_risks
                (beescad_id, title, assignee, status, priority, gut_score, jira_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                risk['beescad_id'], risk['title'], risk['assignee'],
                risk['status'], risk['priority'], risk['gut_score'],
                risk.get('jira_url'), datetime.now().isoformat()
            ))
            items_synced += 1
        
        # Inserir/atualizar bugs
        for bug in data.get('bugs', []):
            cursor.execute("""
                INSERT OR REPLACE INTO confluence_bugs
                (beescad_id, title, priority, status, team, jira_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                bug['beescad_id'], bug['title'], bug['priority'],
                bug['status'], bug['team'], bug.get('jira_url'),
                datetime.now().isoformat()
            ))
            items_synced += 1
        
        # Atualizar status do sync
        cursor.execute("""
            UPDATE confluence_sync_status 
            SET status = 'completed', items_synced = ?, completed_at = ?
            WHERE id = ?
        """, (items_synced, datetime.now().isoformat(), sync_id))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "sync_id": sync_id,
            "items_synced": items_synced,
            "data_summary": {
                "sprints": len(data.get('sprints', [])),
                "initiatives": len(data.get('initiatives', [])),
                "epics": len(data.get('epics', [])),
                "risks": len(data.get('risks', [])),
                "bugs": len(data.get('bugs', []))
            }
        }
        
    except Exception as e:
        # Registrar erro
        cursor.execute("""
            UPDATE confluence_sync_status 
            SET status = 'failed', error_message = ?, completed_at = ?
            WHERE id = ?
        """, (str(e), datetime.now().isoformat(), sync_id))
        conn.commit()
        conn.close()
        
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@app.get("/api/confluence/sync/status")
async def get_confluence_sync_status():
    """Retorna status do último sync"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM confluence_sync_status 
        ORDER BY started_at DESC 
        LIMIT 1
    """)
    status = cursor.fetchone()
    conn.close()
    
    if not status:
        return {"status": "never_synced", "message": "No sync has been performed yet"}
    
    return dict(status)


@app.get("/api/confluence/summary")
async def get_confluence_summary():
    """Retorna resumo dos dados do Confluence para o dashboard"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Sprint atual
    cursor.execute("SELECT * FROM confluence_sprints WHERE is_current = 1 LIMIT 1")
    current_sprint = cursor.fetchone()
    if not current_sprint:
        cursor.execute("SELECT * FROM confluence_sprints ORDER BY sprint_number DESC LIMIT 1")
        current_sprint = cursor.fetchone()
    
    # Total de items
    cursor.execute("SELECT COUNT(*) as count FROM confluence_initiatives")
    total_initiatives = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM confluence_epics")
    total_epics = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM confluence_sprints")
    total_sprints = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM confluence_risks WHERE status != 'Done'")
    active_risks = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM confluence_bugs WHERE status NOT IN ('Done', 'Closed')")
    active_bugs = cursor.fetchone()['count']
    
    conn.close()
    
    # Formato simplificado para o frontend
    return {
        "initiatives": total_initiatives,
        "epics": total_epics,
        "sprints": total_sprints,
        "risks": active_risks,
        "bugs": active_bugs,
        "current_sprint": current_sprint['sprint_name'] if current_sprint else None
    }


@app.get("/api/confluence/all")
async def get_confluence_all(team: Optional[str] = None):
    """Returns ALL Confluence data in a single request for fast page load"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Sprints
    cursor.execute("SELECT * FROM confluence_sprints ORDER BY sprint_number DESC")
    sprints = [dict(row) for row in cursor.fetchall()]
    
    # Initiatives
    if team:
        cursor.execute("SELECT * FROM confluence_initiatives WHERE team LIKE ? ORDER BY beesip_id", (f'%{team}%',))
    else:
        cursor.execute("SELECT * FROM confluence_initiatives ORDER BY beesip_id")
    initiatives = [dict(row) for row in cursor.fetchall()]
    
    # Epics
    cursor.execute("SELECT * FROM confluence_epics ORDER BY beescad_id")
    epics = [dict(row) for row in cursor.fetchall()]
    
    # Risks (active only)
    cursor.execute("SELECT * FROM confluence_risks WHERE status != 'Done' ORDER BY gut_score DESC")
    risks = [dict(row) for row in cursor.fetchall()]
    
    # Bugs (active only)
    if team:
        cursor.execute("SELECT * FROM confluence_bugs WHERE status NOT IN ('Done', 'Closed') AND team LIKE ? ORDER BY priority", (f'%{team}%',))
    else:
        cursor.execute("SELECT * FROM confluence_bugs WHERE status NOT IN ('Done', 'Closed') ORDER BY priority")
    bugs = [dict(row) for row in cursor.fetchall()]
    
    # Sync status
    cursor.execute("SELECT * FROM sync_log WHERE source = 'confluence' ORDER BY synced_at DESC LIMIT 1")
    sync_row = cursor.fetchone()
    sync_status = dict(sync_row) if sync_row else None
    
    conn.close()
    
    return {
        "sprints": sprints,
        "initiatives": initiatives,
        "epics": epics,
        "risks": risks,
        "bugs": bugs,
        "sync_status": sync_status,
        "stats": {
            "initiatives": len(initiatives),
            "epics": len(epics),
            "sprints": len(sprints),
            "risks": len(risks),
            "bugs": len(bugs)
        }
    }


# ============================================
# EXPLORE WORK (Jira/Confluence)
# ============================================

class ExploreRequest(BaseModel):
    """Request para explorar item do Jira/Confluence"""
    target: str = Field(..., description="Issue key (BEESIP-123) ou URL")
    save: bool = Field(default=False, description="Salvar documentação?")
    project: str = Field(default="3TPM", description="Projeto para salvar")


# --- Atlas Canonical Memory Mirror Models ---

class DecisionCreate(BaseModel):
    """Create a new decision record (mirrors DECISIONS.md)"""
    date: str = Field(..., description="Decision date YYYY-MM-DD")
    decision_text: str = Field(..., description="What was decided")
    rationale: Optional[str] = Field(None, description="Why it was decided")
    category: str = Field("architecture", description="architecture, workflow, precedence, non-goals")
    conversation_id: Optional[str] = Field(None, description="Optional conversation reference")

class StateSnapshotCreate(BaseModel):
    """Create/update a state snapshot (mirrors STATE.md sections)"""
    section: str = Field(..., description="active_projects, priorities, pending_items, recent_decisions")
    key: str = Field(..., description="Item name e.g. 'Context Engine', 'Centro de Controle'")
    value: str = Field(..., description="Current state/status text")
    status: str = Field("active", description="active, completed, cancelled")


# ============================================
# OBSERVABILITY MODELS
# ============================================

class ConversationTurnCreate(BaseModel):
    """Log a conversation turn"""
    session_id: str = Field(..., description="UUID session identifier")
    turn_number: int = Field(1, description="Turn number in session")
    role: str = Field("user", description="user/atlas/router/writer")
    content_preview: Optional[str] = Field(None, description="First 200 chars, no secrets")
    intent_classified: Optional[str] = Field(None, description="Comma-separated intents")
    tools_called: Optional[str] = Field(None, description="Comma-separated tool names")
    tools_failed: Optional[str] = Field(None, description="Comma-separated failed tools")
    duration_ms: Optional[int] = Field(None, description="Turn duration in ms")

class ToolCallCreate(BaseModel):
    """Log a tool call"""
    session_id: Optional[str] = Field(None, description="Session UUID")
    tool_name: str = Field(..., description="Tool name")
    arguments_preview: Optional[str] = Field(None, description="First 100 chars of args")
    status: str = Field("success", description="success/error/timeout")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    duration_ms: Optional[int] = Field(None, description="Call duration in ms")

class RoutingEvalCreate(BaseModel):
    """Log a routing evaluation"""
    session_id: Optional[str] = Field(None, description="Session UUID")
    query_preview: Optional[str] = Field(None, description="First 200 chars of query")
    intents_classified: Optional[str] = Field(None, description="Comma-separated classified intents")
    intents_expected: Optional[str] = Field(None, description="Ground truth intents if known")
    tools_called: Optional[str] = Field(None, description="Comma-separated tools called")
    tools_succeeded: Optional[str] = Field(None, description="Comma-separated succeeded tools")
    context_tokens_estimate: Optional[int] = Field(None, description="Estimated context tokens")
    accuracy_score: Optional[float] = Field(None, description="Accuracy score 0-1")

class QualityScoreCreate(BaseModel):
    """Log an LLM-as-judge quality score"""
    session_id: Optional[str] = Field(None, description="Session UUID")
    evaluator: str = Field("claude", description="Model name or 'human'")
    dimension: str = Field(..., description="relevance/accuracy/completeness/conciseness")
    score: int = Field(..., ge=1, le=5, description="Score 1-5")
    rationale: Optional[str] = Field(None, description="Evaluation rationale")

class ReportCreate(BaseModel):
    """Log a daily or weekly report"""
    report_date: str = Field(..., description="Report date YYYY-MM-DD")
    report_json: str = Field(..., description="Full structured report as JSON string")
    summary: Optional[str] = Field(None, description="1-2 sentence human-readable summary")


@app.post("/api/explore")
async def explore_work_item(request: ExploreRequest):
    """
    Explora item do Jira ou Confluence
    - target: issue key (BEESIP-123) ou URL do Jira/Confluence
    - save: se True, salva markdown em docs/trabalho/projetos/{project}/notes/
    - project: nome do projeto (3TPM, CATALOG-ADMIN, CMS-DAM, COMPANY-STORE)
    """
    try:
        from explore_work import explore
        result = explore(
            target=request.target,
            save=request.save,
            project=request.project
        )
        return {
            "status": "success",
            "data": result
        }
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"explore_work module not available: {str(e)}"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Exploration failed: {str(e)}")


@app.get("/api/explore/{issue_key}")
async def get_jira_issue_details(
    issue_key: str,
    save: bool = Query(default=False),
    project: str = Query(default="3TPM")
):
    """
    Endpoint GET para explorar issue do Jira
    Ex: GET /api/explore/BEESIP-10009?save=true&project=3TPM
    """
    try:
        from explore_work import explore
        result = explore(
            target=issue_key,
            save=save,
            project=project
        )
        return {
            "status": "success",
            "data": result
        }
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"explore_work module not available: {str(e)}"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Exploration failed: {str(e)}")


@app.get("/api/projects")
async def list_work_projects():
    """Lista projetos disponíveis para documentação"""
    import os
    from pathlib import Path
    
    projects_dir = Path(__file__).parent.parent.parent.parent / "docs" / "trabalho" / "projetos"
    projects = []
    
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                readme_path = project_dir / "README.md"
                notes_dir = project_dir / "notes"
                notes_count = len(list(notes_dir.glob("*.md"))) if notes_dir.exists() else 0
                
                projects.append({
                    "id": project_dir.name,
                    "has_readme": readme_path.exists(),
                    "notes_count": notes_count,
                    "path": str(project_dir)
                })
    
    return {
        "projects": projects,
        "total": len(projects)
    }


# ============================================
# SYNC STATUS (unified)
# ============================================

@app.get("/api/sync/status")
async def get_all_sync_status():
    """Returns sync status for all data sources (reads from sync_log + file checks)"""
    conn = get_db()
    
    def get_latest_sync(source_name):
        """Get latest sync_log entry for a source"""
        try:
            row = conn.execute("""
                SELECT status, items_count, synced_at, error_message
                FROM sync_log
                WHERE source = ?
                ORDER BY synced_at DESC LIMIT 1
            """, (source_name,)).fetchone()
            if row:
                return {
                    "status": row["status"],
                    "last_sync": row["synced_at"],
                    "items": row["items_count"],
                    "error": row["error_message"]
                }
        except:
            pass
        # Fallback: check old confluence_sync_status table
        if source_name == "confluence":
            try:
                row = conn.execute("""
                    SELECT status, completed_at, items_synced 
                    FROM confluence_sync_status 
                    ORDER BY started_at DESC LIMIT 1
                """).fetchone()
                if row:
                    return {
                        "status": row["status"],
                        "last_sync": row["completed_at"],
                        "items": row["items_synced"]
                    }
            except:
                pass
        return {"status": "never_synced", "last_sync": None}
    
    confluence_status = get_latest_sync("confluence")
    notion_status = get_latest_sync("notion")
    mba_status = get_latest_sync("mba")
    
    # Calendar: check CALENDARIO.md modification time
    calendar_status = {"status": "unknown", "last_sync": None}
    cal_paths = [
        "/root/Nova/openclaw-workspace/CALENDARIO.md",
        os.path.expanduser("~/Documents/Nova/openclaw-workspace/CALENDARIO.md")
    ]
    for cal_path in cal_paths:
        if os.path.exists(cal_path):
            mtime = os.path.getmtime(cal_path)
            calendar_status = {
                "status": "ok",
                "last_sync": datetime.fromtimestamp(mtime).isoformat(),
                "source": "CALENDARIO.md"
            }
            break
    
    # MBA: also check file if sync_log is empty
    if mba_status["status"] == "never_synced":
        mba_paths = [
            "/root/Nova/openclaw-workspace/docs/mba/adalove-data.json",
            os.path.expanduser("~/Documents/Nova/openclaw-workspace/docs/mba/adalove-data.json")
        ]
        for mba_path in mba_paths:
            if os.path.exists(mba_path):
                mtime = os.path.getmtime(mba_path)
                mba_status = {
                    "status": "ok",
                    "last_sync": datetime.fromtimestamp(mtime).isoformat()
                }
                break
    
    # Tasks/Projects: always available (local SQLite)
    task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    project_count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    
    # Meeting notes count
    meeting_count = 0
    try:
        meeting_count = conn.execute("SELECT COUNT(*) FROM meeting_notes").fetchone()[0]
    except:
        pass
    
    return {
        "confluence": confluence_status,
        "calendar": calendar_status,
        "mba": mba_status,
        "notion": notion_status,
        "tasks": {"status": "ok", "count": task_count},
        "projects": {"status": "ok", "count": project_count},
        "meetings": {"status": "ok", "count": meeting_count}
    }


@app.post("/api/notion/sync")
async def trigger_notion_sync():
    """Triggers a Notion sync using the sync_notion_vps module."""
    try:
        from sync_notion_vps import sync_notion_meetings, NOTION_TOKEN
        
        if not NOTION_TOKEN:
            return {
                "status": "not_configured",
                "message": "NOTION_TOKEN nao configurado. Adicione ao .env no backend."
            }
        
        import asyncio
        success = await asyncio.to_thread(sync_notion_meetings)
        
        if success:
            # Get count from DB
            conn = get_db()
            count = conn.execute("SELECT COUNT(*) FROM meeting_notes").fetchone()[0]
            conn.close()
            return {
                "status": "ok",
                "meetings_synced": count,
                "synced_at": datetime.now().isoformat()
            }
        else:
            return {"status": "error", "message": "Notion sync failed. Check logs."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/notion/sync/status")
async def get_notion_sync_status():
    """Returns Notion sync status"""
    import os
    notion_token = os.environ.get("NOTION_TOKEN", "")
    
    return {
        "configured": bool(notion_token),
        "status": "ready" if notion_token else "not_configured",
        "message": "Notion sync disponível" if notion_token else "NOTION_TOKEN não configurado"
    }


@app.post("/api/sync/all")
async def trigger_full_sync():
    """Triggers sync for all available data sources"""
    from fastapi.responses import JSONResponse
    results = {}
    
    # 1. Confluence sync - fetch, parse, AND persist to DB
    try:
        from situation_wall_parser import fetch_and_parse
        data = fetch_and_parse()
        if data:
            total = _persist_confluence_data(data)
            log_sync("confluence", "completed", total)
            results["confluence"] = {"status": "ok", "message": f"Confluence synced: {total} items persisted"}
        else:
            results["confluence"] = {"status": "skipped", "message": "No data from Confluence"}
    except Exception as e:
        log_sync("confluence", "error", error_message=str(e))
        results["confluence"] = {"status": "error", "message": str(e)}
    
    # 2. MBA - notify only (external sync)
    results["mba"] = {"status": "external", "message": "MBA sync requires Atlas/Playwright"}
    
    # 3. Calendar - already reads from file, no sync needed
    results["calendar"] = {"status": "ok", "message": "Calendar reads from CALENDARIO.md (always fresh)"}
    
    # 4. Tasks/Projects - local, always fresh
    results["tasks"] = {"status": "ok", "message": "Local data, always available"}
    
    return results


# ============================================
# ATLAS PUSH ENDPOINTS (authenticated)
# ============================================


@app.post("/api/sync/push/meetings")
async def push_meetings(request: Request):
    """Receive enriched meeting data from Atlas MCP"""
    verify_atlas_key(request)
    body = await request.json()
    meetings = body.get("meetings", [])
    
    if not meetings:
        return {"status": "error", "message": "No meetings provided"}
    
    conn = get_db()
    synced = 0
    for m in meetings:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO meeting_notes
                (id, title, date, project, summary, participants, action_items, source, notion_url, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                m.get("id", f"atlas-{datetime.now().timestamp()}"),
                m.get("title", ""),
                m.get("date", ""),
                m.get("project", ""),
                m.get("summary", ""),
                m.get("participants", ""),
                m.get("action_items", ""),
                m.get("source", "atlas"),
                m.get("notion_url", ""),
                datetime.now().isoformat()
            ))
            synced += 1
        except Exception as e:
            print(f"Error pushing meeting: {e}")
    
    conn.commit()
    log_sync("notion", "completed", synced)
    conn.close()
    
    return {"status": "ok", "meetings_synced": synced}


@app.post("/api/sync/push/mba")
async def push_mba(request: Request):
    """Receive MBA/Adalove data from Atlas MCP"""
    verify_atlas_key(request)
    body = await request.json()
    
    # Write to adalove-data.json
    mba_paths = [
        "/root/Nova/openclaw-workspace/docs/mba/adalove-data.json",
        os.path.expanduser("~/Documents/Nova/openclaw-workspace/docs/mba/adalove-data.json")
    ]
    
    written = False
    for mba_path in mba_paths:
        mba_dir = os.path.dirname(mba_path)
        if os.path.exists(mba_dir):
            with open(mba_path, 'w') as f:
                json.dump(body, f, ensure_ascii=False, indent=2)
            written = True
            break
    
    if written:
        log_sync("mba", "completed", body.get("resumo", {}).get("total_pendentes", 0) + 
                 body.get("resumo", {}).get("total_em_andamento", 0) +
                 body.get("resumo", {}).get("total_concluidas", 0))
        return {"status": "ok", "message": "MBA data saved", "path": mba_path}
    else:
        return {"status": "error", "message": "Could not find MBA data directory"}


@app.post("/api/sync/push/work-status")
async def push_work_status(request: Request):
    """Receive parsed Confluence situation wall data from Atlas MCP"""
    verify_atlas_key(request)
    body = await request.json()
    
    try:
        total = _persist_confluence_data(body)
        log_sync("confluence", "completed", total)
        return {"status": "ok", "items_persisted": total}
    except Exception as e:
        log_sync("confluence", "error", error_message=str(e))
        return {"status": "error", "message": str(e)}


@app.post("/api/sync/push/weekly-brief")
async def push_weekly_brief(request: Request):
    """Receive weekly brief data from Atlas MCP"""
    verify_atlas_key(request)
    body = await request.json()
    
    week_start = body.get("week_start", "")
    if not week_start:
        raise HTTPException(400, "week_start is required (YYYY-MM-DD)")
    
    conn = get_db()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO weekly_briefs 
            (week_start, title, week_glance, action_items_urgent, action_items_important,
             decisions, energy_check, full_markdown, generated_at, pushed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            week_start,
            body.get("title", f"Week of {week_start}"),
            body.get("week_glance", ""),
            json.dumps(body.get("action_items_urgent", []), ensure_ascii=False),
            json.dumps(body.get("action_items_important", []), ensure_ascii=False),
            json.dumps(body.get("decisions", []), ensure_ascii=False),
            json.dumps(body.get("energy_check", {}), ensure_ascii=False),
            body.get("full_markdown", ""),
            body.get("generated_at", datetime.now().isoformat()),
            datetime.now().isoformat()
        ))
        conn.commit()
        log_sync("weekly-brief", "completed", 1)
        return {"status": "ok", "week_start": week_start}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.get("/api/weekly-brief")
async def get_weekly_brief():
    """Get the latest weekly brief"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM weekly_briefs ORDER BY week_start DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(404, "No weekly brief available")
    
    brief = dict(row)
    # Parse JSON fields
    for field in ["action_items_urgent", "action_items_important", "decisions", "energy_check"]:
        if brief.get(field) and isinstance(brief[field], str):
            try:
                brief[field] = json.loads(brief[field])
            except:
                pass
    
    return brief


# ============================================
# SIBLING COMMUNICATION (Atlas <-> Nova)
# ============================================

OPENCLAW_HOOK_TOKEN = os.environ.get("OPENCLAW_HOOK_TOKEN", "")
OPENCLAW_GATEWAY = "http://localhost:18789"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "2097306140")


@app.post("/api/sibling/nova")
async def send_to_nova(request: Request):
    """Atlas sends a message to Nova via OpenClaw hooks/agent.
    Triggers a full agent turn -- Nova will think about and respond to the message.
    """
    verify_atlas_key(request)
    body = await request.json()
    message = body.get("message", "")
    
    if not message:
        raise HTTPException(400, "message is required")
    
    if not OPENCLAW_HOOK_TOKEN:
        raise HTTPException(503, "OPENCLAW_HOOK_TOKEN not configured")
    
    # Relay to OpenClaw /hooks/agent
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{OPENCLAW_GATEWAY}/hooks/agent",
                headers={
                    "Authorization": f"Bearer {OPENCLAW_HOOK_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "message": f"[Mensagem do Atlas (irmao)]\n\n{message}",
                    "name": "Atlas",
                    "sessionKey": body.get("session_key", "hook:atlas:main"),
                    "deliver": body.get("deliver", True),
                    "channel": "telegram",
                    "to": TELEGRAM_CHAT_ID
                }
            )
        
        # Also log in sibling_inbox for history
        conn = get_db()
        conn.execute("""
            INSERT INTO sibling_inbox (from_agent, to_agent, message, context, status)
            VALUES ('atlas', 'nova', ?, ?, 'delivered')
        """, (message, json.dumps(body.get("context", {}))))
        conn.commit()
        conn.close()
        
        return {
            "status": "ok",
            "openclaw_status": resp.status_code,
            "delivered": True
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/sibling/nova/message")
async def send_raw_to_nova(request: Request):
    """Atlas sends a raw Telegram message (no agent turn).
    Just drops text into the chat -- Nova sees it as context.
    """
    verify_atlas_key(request)
    body = await request.json()
    message = body.get("message", "")
    
    if not message:
        raise HTTPException(400, "message is required")
    
    # Use openclaw CLI to send a raw message
    import subprocess
    try:
        result = subprocess.run(
            ["openclaw", "message", "send",
             "--channel", "telegram",
             "--target", TELEGRAM_CHAT_ID,
             "--message", f"[Atlas] {message}"],
            capture_output=True, text=True, timeout=15
        )
        
        success = result.returncode == 0
        
        # Log in sibling_inbox
        conn = get_db()
        conn.execute("""
            INSERT INTO sibling_inbox (from_agent, to_agent, message, context, status)
            VALUES ('atlas', 'nova', ?, '{"type": "raw_message"}', ?)
        """, (message, "delivered" if success else "failed"))
        conn.commit()
        conn.close()
        
        return {
            "status": "ok" if success else "error",
            "method": "openclaw_cli",
            "output": result.stdout[:200] if success else result.stderr[:200]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/sibling/atlas")
async def send_to_atlas(request: Request):
    """Nova sends a message to Atlas. Stored in inbox for Atlas to pick up.
    No auth required from Nova (she runs on the same VPS).
    """
    body = await request.json()
    message = body.get("message", "")
    urgency = body.get("urgency", "normal")
    
    if not message:
        raise HTTPException(400, "message is required")
    
    conn = get_db()
    conn.execute("""
        INSERT INTO sibling_inbox (from_agent, to_agent, message, context, status)
        VALUES ('nova', 'atlas', ?, ?, 'pending')
    """, (message, json.dumps({"urgency": urgency, **{k: v for k, v in body.items() if k not in ("message", "urgency")}})))
    conn.commit()
    
    # Get the ID of the inserted message
    cursor = conn.cursor()
    cursor.execute("SELECT last_insert_rowid()")
    msg_id = cursor.fetchone()[0]
    conn.close()
    
    return {
        "status": "ok",
        "message_id": msg_id,
        "note": "Message queued for Atlas. He will read it on next Cursor session."
    }


@app.get("/api/sibling/atlas/inbox")
async def get_atlas_inbox(request: Request):
    """Atlas checks for pending messages from Nova."""
    verify_atlas_key(request)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pending messages
    cursor.execute("""
        SELECT id, from_agent, message, context, status, created_at
        FROM sibling_inbox
        WHERE to_agent = 'atlas' AND status = 'pending'
        ORDER BY created_at ASC
    """)
    
    messages = []
    ids = []
    for row in cursor.fetchall():
        msg = dict(row)
        msg["context"] = json.loads(msg["context"]) if msg["context"] else {}
        messages.append(msg)
        ids.append(msg["id"])
    
    # Mark as read
    if ids:
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"""
            UPDATE sibling_inbox SET status = 'read', read_at = ?
            WHERE id IN ({placeholders})
        """, [datetime.now().isoformat()] + ids)
        conn.commit()
    
    conn.close()
    
    return {
        "messages": messages,
        "count": len(messages),
        "has_urgent": any(m.get("context", {}).get("urgency") == "high" for m in messages)
    }


@app.get("/api/sibling/history")
async def get_sibling_history(request: Request, limit: int = 20):
    """Get recent sibling communication history."""
    verify_atlas_key(request)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, from_agent, to_agent, message, context, status, created_at, read_at
        FROM sibling_inbox
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"history": history, "count": len(history)}


# ============================================
# ATLAS CANONICAL MEMORY MIRROR
# ============================================

@app.get("/api/decisions")
async def list_decisions(
    request: Request,
    category: Optional[str] = None,
    limit: int = 50,
    include_superseded: bool = False,
):
    """List decisions from the canonical memory mirror."""
    verify_atlas_key(request)

    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM atlas_decisions"
    params = []
    conditions = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if not include_superseded:
        conditions.append("superseded_by IS NULL")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    decisions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {"decisions": decisions, "count": len(decisions)}


@app.post("/api/decisions")
async def create_decision(request: Request, decision: DecisionCreate):
    """Record a new decision (mirrors DECISIONS.md append)."""
    verify_atlas_key(request)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO atlas_decisions (date, decision_text, rationale, category, conversation_id, created_by)
        VALUES (?, ?, ?, ?, ?, 'atlas')
    """, (decision.date, decision.decision_text, decision.rationale,
          decision.category, decision.conversation_id))

    decision_id = cursor.lastrowid
    conn.commit()

    cursor.execute("SELECT * FROM atlas_decisions WHERE id = ?", (decision_id,))
    new_decision = dict(cursor.fetchone())
    conn.close()

    return new_decision


@app.post("/api/decisions/{decision_id}/supersede")
async def supersede_decision(request: Request, decision_id: int, superseded_by: int):
    """Mark a decision as superseded by another."""
    verify_atlas_key(request)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE atlas_decisions SET superseded_by = ? WHERE id = ?",
        (superseded_by, decision_id),
    )

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Decision not found")

    conn.commit()
    conn.close()

    return {"message": f"Decision {decision_id} marked as superseded by {superseded_by}"}


@app.get("/api/state-snapshots")
async def list_state_snapshots(
    request: Request,
    section: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    """List state snapshots from the canonical memory mirror."""
    verify_atlas_key(request)

    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM state_snapshots"
    params = []
    conditions = []

    if section:
        conditions.append("section = ?")
        params.append(section)
    if status:
        conditions.append("status = ?")
        params.append(status)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    snapshots = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {"snapshots": snapshots, "count": len(snapshots)}


@app.post("/api/state-snapshots")
async def create_state_snapshot(request: Request, snapshot: StateSnapshotCreate):
    """Create or update a state snapshot (upsert by section+key)."""
    verify_atlas_key(request)

    conn = get_db()
    cursor = conn.cursor()

    # Check if entry exists for this section+key
    cursor.execute(
        "SELECT id FROM state_snapshots WHERE section = ? AND key = ?",
        (snapshot.section, snapshot.key),
    )
    existing = cursor.fetchone()

    if existing:
        # Update existing
        cursor.execute("""
            UPDATE state_snapshots
            SET value = ?, status = ?, updated_by = 'atlas', updated_at = CURRENT_TIMESTAMP
            WHERE section = ? AND key = ?
        """, (snapshot.value, snapshot.status, snapshot.section, snapshot.key))
        snapshot_id = existing["id"]
    else:
        # Insert new
        cursor.execute("""
            INSERT INTO state_snapshots (section, key, value, status, updated_by)
            VALUES (?, ?, ?, ?, 'atlas')
        """, (snapshot.section, snapshot.key, snapshot.value, snapshot.status))
        snapshot_id = cursor.lastrowid

    conn.commit()

    cursor.execute("SELECT * FROM state_snapshots WHERE id = ?", (snapshot_id,))
    result = dict(cursor.fetchone())
    conn.close()

    return result


@app.get("/api/state-snapshots/latest")
async def get_latest_state_snapshots(request: Request):
    """Get the latest state snapshot for each section+key pair."""
    verify_atlas_key(request)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s1.* FROM state_snapshots s1
        INNER JOIN (
            SELECT section, key, MAX(updated_at) as max_updated
            FROM state_snapshots
            GROUP BY section, key
        ) s2 ON s1.section = s2.section AND s1.key = s2.key AND s1.updated_at = s2.max_updated
        ORDER BY s1.section, s1.key
    """)

    snapshots = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {"snapshots": snapshots, "count": len(snapshots)}


# ============================================
# OBSERVABILITY ENDPOINTS — Telemetry Ingestion
# ============================================

@app.post("/api/telemetry/conversation-turn")
async def log_conversation_turn(turn: ConversationTurnCreate, request: Request):
    """Log a conversation turn (fire-and-forget from atlas-mcp)."""
    verify_atlas_key(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO conversation_turns
        (session_id, turn_number, role, content_preview, intent_classified, tools_called, tools_failed, duration_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (turn.session_id, turn.turn_number, turn.role, turn.content_preview,
          turn.intent_classified, turn.tools_called, turn.tools_failed, turn.duration_ms))
    turn_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": turn_id, "status": "logged"}


@app.post("/api/telemetry/tool-call")
async def log_tool_call(tc: ToolCallCreate, request: Request):
    """Log a tool call (fire-and-forget from atlas-mcp)."""
    verify_atlas_key(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tool_calls
        (session_id, tool_name, arguments_preview, status, error_message, duration_ms)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (tc.session_id, tc.tool_name, tc.arguments_preview, tc.status, tc.error_message, tc.duration_ms))
    tc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": tc_id, "status": "logged"}


@app.post("/api/telemetry/routing-eval")
async def log_routing_eval(re_eval: RoutingEvalCreate, request: Request):
    """Log a routing evaluation (fire-and-forget from atlas-mcp)."""
    verify_atlas_key(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO routing_evaluations
        (session_id, query_preview, intents_classified, intents_expected, tools_called,
         tools_succeeded, context_tokens_estimate, accuracy_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (re_eval.session_id, re_eval.query_preview, re_eval.intents_classified,
          re_eval.intents_expected, re_eval.tools_called, re_eval.tools_succeeded,
          re_eval.context_tokens_estimate, re_eval.accuracy_score))
    eval_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": eval_id, "status": "logged"}


@app.post("/api/telemetry/quality-score")
async def log_quality_score(qs: QualityScoreCreate, request: Request):
    """Log an LLM-as-judge quality score."""
    verify_atlas_key(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO quality_scores
        (session_id, evaluator, dimension, score, rationale)
        VALUES (?, ?, ?, ?, ?)
    """, (qs.session_id, qs.evaluator, qs.dimension, qs.score, qs.rationale))
    qs_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": qs_id, "status": "logged"}


# ============================================
# OBSERVABILITY ENDPOINTS — Reports
# ============================================

@app.post("/api/reports/daily")
async def push_daily_report(report: ReportCreate, request: Request):
    """Push a daily evaluation report."""
    verify_atlas_key(request)
    conn = get_db()
    cursor = conn.cursor()
    # Upsert by report_date
    cursor.execute("SELECT id FROM daily_reports WHERE report_date = ?", (report.report_date,))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("""
            UPDATE daily_reports SET report_json = ?, summary = ?, timestamp = CURRENT_TIMESTAMP
            WHERE report_date = ?
        """, (report.report_json, report.summary, report.report_date))
        report_id = existing["id"]
    else:
        cursor.execute("""
            INSERT INTO daily_reports (report_date, report_json, summary) VALUES (?, ?, ?)
        """, (report.report_date, report.report_json, report.summary))
        report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": report_id, "status": "saved"}


@app.post("/api/reports/weekly")
async def push_weekly_report(report: ReportCreate, request: Request):
    """Push a weekly evaluation report."""
    verify_atlas_key(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM weekly_reports WHERE report_date = ?", (report.report_date,))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("""
            UPDATE weekly_reports SET report_json = ?, summary = ?, timestamp = CURRENT_TIMESTAMP
            WHERE report_date = ?
        """, (report.report_json, report.summary, report.report_date))
        report_id = existing["id"]
    else:
        cursor.execute("""
            INSERT INTO weekly_reports (report_date, report_json, summary) VALUES (?, ?, ?)
        """, (report.report_date, report.report_json, report.summary))
        report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": report_id, "status": "saved"}


@app.get("/api/reports/daily")
async def get_daily_reports(days: int = Query(7, ge=1, le=90)):
    """Get recent daily reports."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM daily_reports
        ORDER BY report_date DESC LIMIT ?
    """, (days,))
    reports = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"reports": reports, "count": len(reports)}


@app.get("/api/reports/weekly")
async def get_weekly_reports(weeks: int = Query(4, ge=1, le=52)):
    """Get recent weekly reports."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM weekly_reports
        ORDER BY report_date DESC LIMIT ?
    """, (weeks,))
    reports = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"reports": reports, "count": len(reports)}


# ============================================
# OBSERVABILITY ENDPOINTS — Metrics Aggregation
# ============================================

@app.get("/api/metrics/tools")
async def get_tool_metrics(days: int = Query(7, ge=1, le=90)):
    """Aggregated tool call stats for last N days."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            tool_name,
            COUNT(*) as total_calls,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
            SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) as timeout_count,
            ROUND(AVG(duration_ms), 0) as avg_duration_ms,
            ROUND(100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*), 1) as success_rate
        FROM tool_calls
        WHERE timestamp >= datetime('now', ? || ' days')
        GROUP BY tool_name
        ORDER BY total_calls DESC
    """, (f"-{days}",))
    tools = [dict(r) for r in cursor.fetchall()]

    # Overall stats
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
            ROUND(100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 1) as success_rate,
            ROUND(AVG(duration_ms), 0) as avg_duration_ms
        FROM tool_calls
        WHERE timestamp >= datetime('now', ? || ' days')
    """, (f"-{days}",))
    overall = dict(cursor.fetchone())
    conn.close()
    return {"tools": tools, "overall": overall, "days": days}


@app.get("/api/metrics/routing")
async def get_routing_metrics(days: int = Query(7, ge=1, le=90)):
    """Aggregated routing evaluation stats for last N days."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(*) as total_evals,
            ROUND(AVG(accuracy_score), 3) as avg_accuracy,
            ROUND(AVG(context_tokens_estimate), 0) as avg_context_tokens
        FROM routing_evaluations
        WHERE timestamp >= datetime('now', ? || ' days')
          AND accuracy_score IS NOT NULL
    """, (f"-{days}",))
    stats = dict(cursor.fetchone())

    # Intent distribution
    cursor.execute("""
        SELECT intents_classified, COUNT(*) as count
        FROM routing_evaluations
        WHERE timestamp >= datetime('now', ? || ' days')
          AND intents_classified IS NOT NULL
        GROUP BY intents_classified
        ORDER BY count DESC
        LIMIT 20
    """, (f"-{days}",))
    intents = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"stats": stats, "intent_distribution": intents, "days": days}


@app.get("/api/metrics/quality")
async def get_quality_metrics(days: int = Query(30, ge=1, le=365)):
    """Quality score trends for last N days."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            dimension,
            ROUND(AVG(score), 2) as avg_score,
            COUNT(*) as sample_count,
            MIN(score) as min_score,
            MAX(score) as max_score
        FROM quality_scores
        WHERE timestamp >= datetime('now', ? || ' days')
        GROUP BY dimension
        ORDER BY dimension
    """, (f"-{days}",))
    dimensions = [dict(r) for r in cursor.fetchall()]

    # Overall average
    cursor.execute("""
        SELECT ROUND(AVG(score), 2) as overall_avg, COUNT(*) as total_scores
        FROM quality_scores
        WHERE timestamp >= datetime('now', ? || ' days')
    """, (f"-{days}",))
    overall = dict(cursor.fetchone())
    conn.close()
    return {"dimensions": dimensions, "overall": overall, "days": days}


# ============================================
# RUN
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)

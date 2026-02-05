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

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
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
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

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

@app.get("/mba")
async def serve_mba_page():
    """Serve a página do MBA"""
    mba_path = os.path.join(FRONTEND_DIR, "mba.html")
    if os.path.exists(mba_path):
        return FileResponse(mba_path)
    return {"message": "MBA page not found"}

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


# ============================================
# EXPLORE WORK (Jira/Confluence)
# ============================================

class ExploreRequest(BaseModel):
    """Request para explorar item do Jira/Confluence"""
    target: str = Field(..., description="Issue key (BEESIP-123) ou URL")
    save: bool = Field(default=False, description="Salvar documentação?")
    project: str = Field(default="3TPM", description="Projeto para salvar")


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
# RUN
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)

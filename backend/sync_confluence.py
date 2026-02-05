#!/usr/bin/env python3
"""
Confluence Sync Script
Runs as a standalone script to sync data from Confluence to the database.
Can be triggered manually or via cron.

Usage:
    python sync_confluence.py
    
Cron example (daily at 6 AM):
    0 6 * * * cd /path/to/backend && /path/to/venv/bin/python sync_confluence.py >> /var/log/confluence_sync.log 2>&1
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from pathlib import Path

# Add backend directory to path
BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / '.env')

from confluence_client import ConfluenceClient
from situation_wall_parser import SituationWallParser


# Database path - same as main.py
DB_PATH = BACKEND_DIR / "database.db"


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_confluence_tables():
    """Ensure Confluence tables exist"""
    conn = get_db()
    cursor = conn.cursor()
    
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
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
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


def sync_confluence_data():
    """Main sync function"""
    print(f"[{datetime.now().isoformat()}] Starting Confluence sync...")
    
    # Ensure tables exist
    init_confluence_tables()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Register sync start
    cursor.execute("""
        INSERT INTO confluence_sync_status (sync_type, status, started_at)
        VALUES ('scheduled', 'running', ?)
    """, (datetime.now().isoformat(),))
    sync_id = cursor.lastrowid
    conn.commit()
    
    try:
        # Fetch from Confluence
        print("  Fetching data from Confluence...")
        client = ConfluenceClient()
        page_data = client.get_situation_wall()
        
        print(f"  Parsing page: {page_data['title']} (v{page_data['version']})")
        parser = SituationWallParser(page_data['html_content'])
        data = parser.parse_all()
        
        items_synced = 0
        
        # Sync sprints
        print(f"  Syncing {len(data.get('sprints', []))} sprints...")
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
        
        # Sync initiatives
        print(f"  Syncing {len(data.get('initiatives', []))} initiatives...")
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
        
        # Sync epics
        print(f"  Syncing {len(data.get('epics', []))} epics...")
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
        
        # Sync risks
        print(f"  Syncing {len(data.get('risks', []))} risks...")
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
        
        # Sync bugs
        print(f"  Syncing {len(data.get('bugs', []))} bugs...")
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
        
        # Update sync status
        cursor.execute("""
            UPDATE confluence_sync_status 
            SET status = 'completed', items_synced = ?, completed_at = ?
            WHERE id = ?
        """, (items_synced, datetime.now().isoformat(), sync_id))
        
        conn.commit()
        conn.close()
        
        print(f"[{datetime.now().isoformat()}] Sync completed: {items_synced} items synced")
        print(f"  Summary:")
        print(f"    - Sprints: {len(data.get('sprints', []))}")
        print(f"    - Initiatives: {len(data.get('initiatives', []))}")
        print(f"    - Epics: {len(data.get('epics', []))}")
        print(f"    - Risks: {len(data.get('risks', []))}")
        print(f"    - Bugs: {len(data.get('bugs', []))}")
        
        # Generate context for AIs (WORK-STATUS.md + optional RAG indexing)
        try:
            from generate_work_context import generate_context
            print(f"\n[{datetime.now().isoformat()}] Generating AI context...")
            context_result = generate_context(output_md=True, index_rag=False)
            if context_result.get('md_generated'):
                print(f"  Generated: {context_result.get('md_path')}")
        except Exception as ctx_error:
            print(f"  Warning: Context generation failed: {ctx_error}")
        
        return True
        
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ERROR: {str(e)}")
        
        # Log error
        cursor.execute("""
            UPDATE confluence_sync_status 
            SET status = 'failed', error_message = ?, completed_at = ?
            WHERE id = ?
        """, (str(e), datetime.now().isoformat(), sync_id))
        conn.commit()
        conn.close()
        
        return False


if __name__ == "__main__":
    success = sync_confluence_data()
    sys.exit(0 if success else 1)

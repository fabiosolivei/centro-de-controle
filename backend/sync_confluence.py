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
from situation_wall_parser import SituationWallParser, Risk, Bug
from dataclasses import asdict


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
        
        # ── Parse storage format (XML) for reliable structural data ──
        parser = SituationWallParser(page_data['storage_content'])
        data = parser.parse_all()
        
        # ── Enrich with Jira API (titles, statuses) ──────────────────
        all_keys = []
        all_keys.extend(i["beesip_id"] for i in data["initiatives"])
        all_keys.extend(e["beescad_id"] for e in data["epics"])
        
        jira_enriched = 0
        if all_keys:
            print(f"  Enriching {len(all_keys)} issues from Jira API...")
            try:
                jira_issues = client.get_issues_batch(all_keys)
                parser.enrich_with_jira_data(data, jira_issues)
                jira_enriched = len(jira_issues)
                print(f"    Got {jira_enriched} issue details from Jira")
            except Exception as jira_err:
                print(f"    WARNING: Jira enrichment failed: {jira_err}")
                print(f"    Structural data (keys, teams, priorities) still saved")
        
        # ── Fetch Risks via JQL extracted from storage ───────────────
        risks_jql = data.get("risks_jql")
        if risks_jql:
            print(f"  Fetching risks via JQL...")
            try:
                risk_issues = client.search_jira(
                    risks_jql,
                    fields=["summary", "assignee", "status", "priority", "customfield_13715"]
                )
                for issue in risk_issues:
                    key = issue.get("key", "")
                    fields_data = issue.get("fields", {})
                    status_obj = fields_data.get("status", {})
                    priority_obj = fields_data.get("priority", {})
                    assignee_obj = fields_data.get("assignee", {})
                    gut_field = fields_data.get("customfield_13715")
                    
                    data["risks"].append(asdict(Risk(
                        beescad_id=key,
                        title=fields_data.get("summary", ""),
                        assignee=assignee_obj.get("displayName", "") if assignee_obj else "",
                        status=status_obj.get("name", "") if status_obj else "",
                        priority=priority_obj.get("name", "") if priority_obj else "",
                        gut_score=int(gut_field) if gut_field else 0,
                        jira_url=f"https://ab-inbev.atlassian.net/browse/{key}"
                    )))
                print(f"    Got {len(data['risks'])} risks")
            except Exception as risk_err:
                print(f"    WARNING: Risks fetch failed: {risk_err}")
        
        # ── Fetch Bugs via JQL extracted from storage ────────────────
        bugs_jql = data.get("bugs_jql")
        if bugs_jql:
            print(f"  Fetching bugs via JQL...")
            try:
                bug_issues = client.search_jira(
                    bugs_jql,
                    fields=["summary", "status", "priority", "customfield_13230"]
                )
                for issue in bug_issues:
                    key = issue.get("key", "")
                    fields_data = issue.get("fields", {})
                    status_obj = fields_data.get("status", {})
                    priority_obj = fields_data.get("priority", {})
                    team_field = fields_data.get("customfield_13230")
                    
                    team = ""
                    if isinstance(team_field, list):
                        team = ", ".join(t.get("value", "") for t in team_field if isinstance(t, dict))
                    elif isinstance(team_field, dict):
                        team = team_field.get("value", "")
                    elif isinstance(team_field, str):
                        team = team_field
                    
                    data["bugs"].append(asdict(Bug(
                        beescad_id=key,
                        title=fields_data.get("summary", ""),
                        priority=priority_obj.get("name", "") if priority_obj else "",
                        status=status_obj.get("name", "") if status_obj else "",
                        team=team,
                        jira_url=f"https://ab-inbev.atlassian.net/browse/{key}"
                    )))
                print(f"    Got {len(data['bugs'])} bugs")
            except Exception as bug_err:
                print(f"    WARNING: Bugs fetch failed: {bug_err}")
        
        # ── Quality logging ──────────────────────────────────────────
        inits_with_title = sum(1 for i in data["initiatives"] if i.get("title"))
        epics_with_title = sum(1 for e in data["epics"] if e.get("title"))
        total_inits = len(data["initiatives"])
        total_epics = len(data["epics"])
        print(f"  Parse quality:")
        print(f"    Initiatives with title: {inits_with_title}/{total_inits}")
        print(f"    Epics with title: {epics_with_title}/{total_epics}")
        print(f"    Jira issues enriched: {jira_enriched}")
        
        # ── Clear old data and sync to DB ────────────────────────────
        items_synced = 0
        
        # Clear old data to avoid stale entries
        cursor.execute("DELETE FROM confluence_sprints")
        cursor.execute("DELETE FROM confluence_initiatives")
        cursor.execute("DELETE FROM confluence_epics")
        cursor.execute("DELETE FROM confluence_risks")
        cursor.execute("DELETE FROM confluence_bugs")
        
        # Sync sprints
        print(f"  Syncing {len(data.get('sprints', []))} sprints...")
        for sprint in data.get('sprints', []):
            cursor.execute("""
                INSERT INTO confluence_sprints 
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
                INSERT INTO confluence_initiatives
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
                INSERT INTO confluence_epics
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
                INSERT INTO confluence_risks
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
                INSERT INTO confluence_bugs
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
        
        # Write to unified sync_log
        try:
            log_conn = get_db()
            log_conn.execute("""
                INSERT INTO sync_log (source, status, items_count, synced_at)
                VALUES ('confluence', 'completed', ?, ?)
            """, (items_synced, datetime.now().isoformat()))
            log_conn.commit()
            log_conn.close()
        except Exception:
            pass  # sync_log table may not exist yet
        
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

#!/usr/bin/env python3
"""
Notion Sync (VPS) - Lightweight fetcher for meeting notes from Notion.
Runs standalone via cron. Fetches recent meetings and stores in SQLite.

Usage:
    python3 sync_notion_vps.py

Cron (every 6 hours):
    0 */6 * * * cd /root/Nova/openclaw-workspace/projects/centro-de-controle/backend && python3 sync_notion_vps.py >> /tmp/notion-sync.log 2>&1
"""

import os
import sys
import json
import sqlite3
import httpx
from datetime import datetime, timedelta
from pathlib import Path

# Load .env
BACKEND_DIR = Path(__file__).parent
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    except ImportError:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    os.environ.setdefault(key.strip(), value.strip())

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
MEETING_DB_ID = "2150885e-4cd1-80ea-a1dc-edc72727afa7"  # Meeting Notes database
DB_PATH = BACKEND_DIR / "database.db"
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    # Ensure meeting_notes table exists
    conn.execute("""
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
    # Ensure sync_log table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            items_count INTEGER DEFAULT 0,
            error_message TEXT,
            synced_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def notion_request(method, endpoint, body=None):
    """Make a request to the Notion API"""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    url = f"{NOTION_API}{endpoint}"
    
    with httpx.Client(timeout=15) as client:
        if method == "POST":
            resp = client.post(url, headers=headers, json=body or {})
        else:
            resp = client.get(url, headers=headers)
        
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  Notion API error {resp.status_code}: {resp.text[:200]}")
            return None


def get_page_title(page):
    """Extract title from a Notion page object"""
    props = page.get("properties", {})
    # Try common title property names
    for key in ["Name", "Title", "name", "title", "Nome"]:
        prop = props.get(key, {})
        if prop.get("type") == "title":
            title_arr = prop.get("title", [])
            if title_arr:
                return "".join(t.get("plain_text", "") for t in title_arr)
    # Fallback: find any title-type property
    for key, prop in props.items():
        if prop.get("type") == "title":
            title_arr = prop.get("title", [])
            if title_arr:
                return "".join(t.get("plain_text", "") for t in title_arr)
    return "Untitled"


def get_page_date(page):
    """Extract date from page properties or created_time"""
    props = page.get("properties", {})
    # Try common date property names
    for key in ["Date", "Data", "date", "data", "Created"]:
        prop = props.get(key, {})
        if prop.get("type") == "date" and prop.get("date"):
            return prop["date"].get("start", "")
    # Fallback: use created_time
    return page.get("created_time", "")[:10]


def get_rich_text(page, property_name):
    """Extract rich text property value"""
    props = page.get("properties", {})
    prop = props.get(property_name, {})
    if prop.get("type") == "rich_text":
        texts = prop.get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in texts)
    return ""


def get_page_blocks(page_id):
    """Fetch the content blocks of a page (first level only)"""
    data = notion_request("GET", f"/blocks/{page_id}/children?page_size=100")
    if not data:
        return []
    return data.get("results", [])


def extract_text_from_blocks(blocks):
    """Extract plain text from page blocks"""
    lines = []
    for block in blocks:
        btype = block.get("type", "")
        bdata = block.get(btype, {})
        
        if btype in ("paragraph", "heading_1", "heading_2", "heading_3", "quote", "callout"):
            rich_text = bdata.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if text:
                lines.append(text)
        elif btype == "bulleted_list_item" or btype == "numbered_list_item":
            rich_text = bdata.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if text:
                lines.append(f"- {text}")
        elif btype == "to_do":
            rich_text = bdata.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            checked = bdata.get("checked", False)
            if text:
                lines.append(f"[{'x' if checked else ' '}] {text}")
    
    return "\n".join(lines)


def extract_action_items(text):
    """Extract action items ([ ] and [x] items) from text"""
    items = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("[ ]") or line.startswith("[x]") or line.startswith("- [ ]") or line.startswith("- [x]"):
            items.append(line)
    return "\n".join(items) if items else ""


def extract_participants(text):
    """Extract @mentions from text"""
    import re
    mentions = re.findall(r'@(\w[\w\s]*?)(?:\s|$|,|\.)', text)
    return ", ".join(set(mentions)) if mentions else ""


def sync_notion_meetings():
    """Fetch recent meeting notes from Notion and store in SQLite"""
    if not NOTION_TOKEN:
        print(f"[{datetime.now().isoformat()}] ERROR: NOTION_TOKEN not configured")
        return False
    
    print(f"[{datetime.now().isoformat()}] Starting Notion sync...")
    
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%S")
    
    # Query Meeting Notes database for recent pages
    query_body = {
        "filter": {
            "timestamp": "last_edited_time",
            "last_edited_time": {"after": cutoff}
        },
        "page_size": 50,
        "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}]
    }
    
    data = notion_request("POST", f"/databases/{MEETING_DB_ID}/query", query_body)
    if not data:
        error_msg = "Failed to query Notion database"
        print(f"  ERROR: {error_msg}")
        conn.execute("INSERT INTO sync_log (source, status, error_message, synced_at) VALUES ('notion', 'error', ?, ?)",
                     (error_msg, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return False
    
    pages = data.get("results", [])
    print(f"  Found {len(pages)} recent meeting pages")
    
    synced = 0
    for page in pages:
        page_id = page.get("id", "")
        title = get_page_title(page)
        meeting_date = get_page_date(page)
        notion_url = page.get("url", "")
        
        if not title or title == "Untitled":
            continue
        
        # Fetch page content
        blocks = get_page_blocks(page_id)
        content = extract_text_from_blocks(blocks)
        
        action_items = extract_action_items(content)
        participants = extract_participants(content)
        
        # Truncate summary to first 500 chars
        summary = content[:500] if content else ""
        
        # Determine project from title or content
        project = ""
        project_keywords = {
            "3TPM": ["3tpm", "3-tpm", "third party", "marketplace"],
            "Catalog": ["catalog", "catálogo"],
            "CMS": ["cms", "content management"],
            "DAM": ["dam", "digital asset"],
            "Company Store": ["company", "store", "company store"],
        }
        title_lower = title.lower()
        for proj, keywords in project_keywords.items():
            if any(kw in title_lower for kw in keywords):
                project = proj
                break
        
        try:
            conn.execute("""
                INSERT OR REPLACE INTO meeting_notes 
                (id, title, date, project, summary, participants, action_items, source, notion_url, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'notion', ?, ?)
            """, (
                f"notion-{page_id}",
                title,
                meeting_date,
                project,
                summary,
                participants,
                action_items,
                notion_url,
                datetime.now().isoformat()
            ))
            synced += 1
        except Exception as e:
            print(f"  Error storing meeting '{title}': {e}")
    
    conn.commit()
    
    # Log sync
    conn.execute("""
        INSERT INTO sync_log (source, status, items_count, synced_at)
        VALUES ('notion', 'completed', ?, ?)
    """, (synced, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    print(f"[{datetime.now().isoformat()}] Notion sync completed: {synced} meetings synced")
    return True


if __name__ == "__main__":
    success = sync_notion_meetings()
    sys.exit(0 if success else 1)

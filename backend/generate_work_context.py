#!/usr/bin/env python3
"""
Generate Work Context for AIs (Atlas & Nova)

Creates:
1. WORK-STATUS.md - Compact summary for quick reading
2. RAG indexing - Semantic search for detailed queries

Usage:
    python generate_work_context.py                    # Generate MD only
    python generate_work_context.py --rag              # Generate MD + index to RAG
    python generate_work_context.py --output /path    # Custom output path
"""

import os
import sys
import json
import sqlite3
import httpx
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Paths
BACKEND_DIR = Path(__file__).parent
DB_PATH = BACKEND_DIR / "database.db"

# Default output path
DEFAULT_OUTPUT_DIR = Path("/home/fabio/Documents/Nova/openclaw-workspace/docs/trabalho")

# RAG Server
RAG_URL = os.getenv("RAG_URL", "http://100.126.23.80:8100")


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def fetch_sprints() -> List[Dict]:
    """Fetch sprints from database"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sprint_name, sprint_number, start_date, end_date, release_date, is_current
        FROM confluence_sprints
        ORDER BY sprint_number DESC
    """)
    sprints = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return sprints


def fetch_initiatives() -> List[Dict]:
    """Fetch initiatives from database"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT beesip_id, title, status, priority, team, kickoff_date, zone_approval, jira_url
        FROM confluence_initiatives
        ORDER BY team, beesip_id
    """)
    initiatives = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return initiatives


def fetch_epics() -> List[Dict]:
    """Fetch epics from database"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT beescad_id, initiative_beesip, title, status, size, sprint, jira_url
        FROM confluence_epics
        ORDER BY sprint DESC, beescad_id
    """)
    epics = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return epics


def fetch_risks() -> List[Dict]:
    """Fetch risks from database"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT beescad_id, title, assignee, status, priority, gut_score, jira_url
        FROM confluence_risks
        ORDER BY gut_score DESC
    """)
    risks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return risks


def fetch_bugs() -> List[Dict]:
    """Fetch bugs from database"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT beescad_id, title, priority, status, team, jira_url
        FROM confluence_bugs
        ORDER BY priority, team
    """)
    bugs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return bugs


def get_current_sprint(sprints: List[Dict]) -> Optional[Dict]:
    """Get current sprint"""
    for sprint in sprints:
        if sprint.get('is_current'):
            return sprint
    return sprints[0] if sprints else None


def count_by_team(items: List[Dict]) -> Dict[str, int]:
    """Count items by team"""
    counts = {}
    for item in items:
        team = item.get('team', 'Unknown') or 'Unknown'
        counts[team] = counts.get(team, 0) + 1
    return counts


def generate_markdown(
    sprints: List[Dict],
    initiatives: List[Dict],
    epics: List[Dict],
    risks: List[Dict],
    bugs: List[Dict]
) -> str:
    """Generate WORK-STATUS.md content"""
    
    now = datetime.now()
    current_sprint = get_current_sprint(sprints)
    
    # Count by team
    init_by_team = count_by_team(initiatives)
    
    md = f"""# Work Status - Q1 2026

> **Atualizado:** {now.strftime('%Y-%m-%d %H:%M')}
> **Fonte:** Confluence Situation Wall - Company & Store Management

---

## Sprint Atual

"""
    
    if current_sprint:
        md += f"""**{current_sprint['sprint_name']}**
- Número: Sprint {current_sprint.get('sprint_number', '?')}
- Início: {current_sprint.get('start_date', 'N/A')}
- Fim: {current_sprint.get('end_date', 'N/A')}
- Release: {current_sprint.get('release_date', 'N/A')}

"""
    else:
        md += "Nenhum sprint atual identificado.\n\n"
    
    # All sprints
    if sprints:
        md += "### Timeline de Sprints\n\n"
        md += "| Sprint | Release | Status |\n"
        md += "|--------|---------|--------|\n"
        for s in sprints[:7]:  # Last 7 sprints
            status = "🟢 Atual" if s.get('is_current') else ""
            md += f"| {s['sprint_name']} | {s.get('release_date', 'N/A')} | {status} |\n"
        md += "\n"
    
    # Initiatives
    md += f"""---

## Initiatives ({len(initiatives)})

### Por Team
"""
    for team, count in sorted(init_by_team.items()):
        md += f"- **{team}:** {count} initiatives\n"
    
    md += "\n### Lista Completa\n\n"
    md += "| ID | Título | Status | Team | Priority |\n"
    md += "|----|--------|--------|------|----------|\n"
    
    for init in initiatives:
        title = (init.get('title') or '')[:50]
        if len(init.get('title', '') or '') > 50:
            title += "..."
        md += f"| {init['beesip_id']} | {title} | {init.get('status', 'N/A')} | {init.get('team', 'N/A')} | {init.get('priority', 'N/A')} |\n"
    
    # Epics
    md += f"""
---

## Epics ({len(epics)})

"""
    # Group by sprint
    epics_by_sprint = {}
    for epic in epics:
        sprint = epic.get('sprint') or 'Sem Sprint'
        if sprint not in epics_by_sprint:
            epics_by_sprint[sprint] = []
        epics_by_sprint[sprint].append(epic)
    
    for sprint_name, sprint_epics in sorted(epics_by_sprint.items(), reverse=True):
        md += f"### {sprint_name} ({len(sprint_epics)} epics)\n\n"
        md += "| ID | Título | Status | Size |\n"
        md += "|----|--------|--------|------|\n"
        for epic in sprint_epics[:10]:  # Limit per sprint
            title = (epic.get('title') or '')[:40]
            if len(epic.get('title', '') or '') > 40:
                title += "..."
            md += f"| {epic['beescad_id']} | {title} | {epic.get('status', 'N/A')} | {epic.get('size', 'N/A')} |\n"
        if len(sprint_epics) > 10:
            md += f"| ... | *+{len(sprint_epics) - 10} mais* | | |\n"
        md += "\n"
    
    # Alerts Section
    md += """---

## Alertas

"""
    
    if risks:
        md += f"### Risks Ativos ({len(risks)})\n\n"
        md += "| ID | Título | GUT Score | Priority |\n"
        md += "|----|--------|-----------|----------|\n"
        for risk in risks:
            title = (risk.get('title') or '')[:40]
            md += f"| {risk['beescad_id']} | {title} | {risk.get('gut_score', 'N/A')} | {risk.get('priority', 'N/A')} |\n"
        md += "\n"
    else:
        md += "✅ Nenhum risk ativo\n\n"
    
    if bugs:
        md += f"### Bugs Ativos ({len(bugs)})\n\n"
        md += "| ID | Título | Team | Priority |\n"
        md += "|----|--------|------|----------|\n"
        for bug in bugs:
            title = (bug.get('title') or '')[:40]
            md += f"| {bug['beescad_id']} | {title} | {bug.get('team', 'N/A')} | {bug.get('priority', 'N/A')} |\n"
        md += "\n"
    else:
        md += "✅ Nenhum bug ativo\n\n"
    
    # Quick Reference
    md += f"""---

## Referência Rápida

### Perguntas Comuns

| Pergunta | Resposta |
|----------|----------|
| Qual o sprint atual? | {current_sprint['sprint_name'] if current_sprint else 'N/A'} |
| Próxima release? | {current_sprint.get('release_date', 'N/A') if current_sprint else 'N/A'} |
| Total de initiatives? | {len(initiatives)} |
| Total de epics? | {len(epics)} |
| Risks ativos? | {len(risks)} |
| Bugs ativos? | {len(bugs)} |

### Contagem por Team

| Team | Initiatives |
|------|-------------|
"""
    for team, count in sorted(init_by_team.items()):
        md += f"| {team} | {count} |\n"
    
    md += """
---

## Como Usar Este Documento

**Para Atlas/Nova:**
1. Leia este arquivo para contexto rápido
2. Use `rag_search("sua query")` para buscas detalhadas
3. Use `/api/confluence/*` para dados em tempo real

**Atualização:** Este arquivo é gerado automaticamente pelo sync do Confluence.

---

*Gerado por: generate_work_context.py*
"""
    
    return md


def index_to_rag(content: str, metadata: Dict[str, Any]) -> bool:
    """Index content to RAG server"""
    try:
        # Split into chunks for better retrieval
        chunks = []
        sections = content.split('\n## ')
        
        for i, section in enumerate(sections):
            if not section.strip():
                continue
            
            chunk_text = section if i == 0 else f"## {section}"
            chunks.append({
                "text": chunk_text,
                "metadata": {
                    **metadata,
                    "section": i,
                    "source": "confluence-situation-wall",
                    "type": "work-status"
                }
            })
        
        # Index to RAG
        with httpx.Client(timeout=30.0) as client:
            for chunk in chunks:
                response = client.post(
                    f"{RAG_URL}/documents",
                    json={
                        "text": chunk["text"],
                        "metadata": chunk["metadata"]
                    }
                )
                if response.status_code not in [200, 201]:
                    print(f"  Warning: Failed to index chunk: {response.status_code}")
        
        print(f"  Indexed {len(chunks)} chunks to RAG")
        return True
        
    except Exception as e:
        print(f"  Error indexing to RAG: {e}")
        return False


def generate_context(
    output_md: bool = True,
    index_rag: bool = False,
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Main function to generate work context.
    
    Args:
        output_md: Generate WORK-STATUS.md file
        index_rag: Index content to RAG server
        output_dir: Custom output directory
    
    Returns:
        Dict with generation results
    """
    print(f"[{datetime.now().isoformat()}] Generating work context...")
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "md_generated": False,
        "rag_indexed": False,
        "stats": {}
    }
    
    # Fetch data
    print("  Fetching data from database...")
    try:
        sprints = fetch_sprints()
        initiatives = fetch_initiatives()
        epics = fetch_epics()
        risks = fetch_risks()
        bugs = fetch_bugs()
    except Exception as e:
        print(f"  Error fetching data: {e}")
        results["error"] = str(e)
        return results
    
    results["stats"] = {
        "sprints": len(sprints),
        "initiatives": len(initiatives),
        "epics": len(epics),
        "risks": len(risks),
        "bugs": len(bugs)
    }
    
    print(f"  Found: {len(sprints)} sprints, {len(initiatives)} initiatives, {len(epics)} epics, {len(risks)} risks, {len(bugs)} bugs")
    
    # Generate markdown
    print("  Generating markdown...")
    md_content = generate_markdown(sprints, initiatives, epics, risks, bugs)
    
    # Save markdown file
    if output_md:
        out_dir = output_dir or DEFAULT_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "WORK-STATUS.md"
        
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        print(f"  Saved: {out_file}")
        results["md_generated"] = True
        results["md_path"] = str(out_file)
    
    # Index to RAG
    if index_rag:
        print("  Indexing to RAG...")
        metadata = {
            "generated_at": datetime.now().isoformat(),
            "document_type": "work-status",
            "quarter": "Q1-2026"
        }
        results["rag_indexed"] = index_to_rag(md_content, metadata)
    
    print(f"[{datetime.now().isoformat()}] Context generation complete!")
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate Work Context for AIs")
    parser.add_argument("--rag", action="store_true", help="Index to RAG server")
    parser.add_argument("--output", type=str, help="Custom output directory")
    parser.add_argument("--no-md", action="store_true", help="Skip markdown generation")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output) if args.output else None
    
    results = generate_context(
        output_md=not args.no_md,
        index_rag=args.rag,
        output_dir=output_dir
    )
    
    print(f"\nResults: {json.dumps(results, indent=2)}")

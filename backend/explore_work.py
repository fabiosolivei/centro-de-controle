#!/usr/bin/env python3
"""
Work Explorer - Fetch details from Jira/Confluence

This script enables Atlas and Nova to explore work items and add documentation.

Usage:
    python explore_work.py BEESIP-10009              # Explore Jira issue
    python explore_work.py BEESCAD-1234             # Explore epic
    python explore_work.py "https://..."             # Explore URL (Jira or Confluence)
    python explore_work.py BEESIP-10009 --save      # Save to project docs
    python explore_work.py BEESIP-10009 --project CATALOG  # Save to specific project
"""

import os
import sys
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Add backend to path
BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

from jira_client import JiraClient, parse_atlassian_url
from confluence_client import ConfluenceClient

# Output directories
DOCS_DIR = Path("/home/fabio/Documents/Nova/openclaw-workspace/docs/trabalho")
PROJECTS_DIR = DOCS_DIR / "projetos"
NOTES_DIR = PROJECTS_DIR / "3TPM" / "notes"  # Default project


def explore_jira_issue(issue_key: str) -> Dict[str, Any]:
    """Explore a Jira issue and return structured data"""
    client = JiraClient()
    
    try:
        # Get issue summary
        summary = client.get_issue_summary(issue_key)
        
        # Get linked issues
        linked = client.get_linked_issues(issue_key)
        
        # Get comments (last 5)
        try:
            comments = client.get_issue_comments(issue_key, max_results=5)
        except:
            comments = []
        
        result = {
            "type": "jira_issue",
            "explored_at": datetime.now().isoformat(),
            "issue": summary,
            "linked_issues": linked,
            "comments": comments
        }
        
        return result
        
    finally:
        client.close()


def explore_confluence_page(page_id: str) -> Dict[str, Any]:
    """Explore a Confluence page and return structured data"""
    client = ConfluenceClient()
    
    # Get page metadata
    page = client.get_page(page_id)
    
    # Get page content
    html_content = client.get_page_html(page_id)
    
    # Clean HTML to text
    import re
    text = re.sub(r'<[^>]+>', ' ', html_content)
    text = re.sub(r'\s+', ' ', text).strip()
    
    result = {
        "type": "confluence_page",
        "explored_at": datetime.now().isoformat(),
        "page": {
            "id": page.get("id"),
            "title": page.get("title"),
            "version": page.get("version", {}).get("number"),
            "last_modified": page.get("version", {}).get("createdAt"),
            "url": f"https://ab-inbev.atlassian.net/wiki/spaces/BAM/pages/{page_id}"
        },
        "content_preview": text[:3000] if text else None,
        "content_length": len(text) if text else 0
    }
    
    return result


def generate_markdown(data: Dict[str, Any]) -> str:
    """Generate markdown documentation from explored data"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    if data["type"] == "jira_issue":
        issue = data["issue"]
        
        md = f"""# {issue['key']}: {issue['summary']}

> Explorado em: {now}
> URL: {issue['url']}

## Informações Básicas

| Campo | Valor |
|-------|-------|
| **Status** | {issue.get('status', 'N/A')} |
| **Tipo** | {issue.get('issue_type', 'N/A')} |
| **Prioridade** | {issue.get('priority', 'N/A')} |
| **Assignee** | {issue.get('assignee', 'N/A')} |
| **Reporter** | {issue.get('reporter', 'N/A')} |
| **Criado** | {issue.get('created', 'N/A')[:10] if issue.get('created') else 'N/A'} |
| **Atualizado** | {issue.get('updated', 'N/A')[:10] if issue.get('updated') else 'N/A'} |

"""
        
        if issue.get('labels'):
            md += f"**Labels:** {', '.join(issue['labels'])}\n\n"
        
        if issue.get('components'):
            md += f"**Components:** {', '.join(issue['components'])}\n\n"
        
        if issue.get('description'):
            md += f"""## Descrição

{issue['description']}

"""
        
        # Linked issues
        if data.get('linked_issues'):
            md += "## Issues Relacionadas\n\n"
            md += "| Key | Summary | Status | Relação |\n"
            md += "|-----|---------|--------|----------|\n"
            for link in data['linked_issues']:
                summary = (link.get('summary') or '')[:40]
                md += f"| {link['key']} | {summary}... | {link.get('status', 'N/A')} | {link.get('relationship', '')} |\n"
            md += "\n"
        
        # Comments
        if data.get('comments'):
            md += "## Comentários Recentes\n\n"
            for comment in data['comments'][:3]:
                md += f"**{comment.get('author', 'Unknown')}** ({comment.get('created', '')[:10] if comment.get('created') else ''}):\n"
                md += f"> {comment.get('body', 'No content')}\n\n"
        
        return md
    
    elif data["type"] == "confluence_page":
        page = data["page"]
        
        md = f"""# {page['title']}

> Explorado em: {now}
> URL: {page['url']}

## Metadados

| Campo | Valor |
|-------|-------|
| **ID** | {page['id']} |
| **Versão** | {page.get('version', 'N/A')} |
| **Última modificação** | {page.get('last_modified', 'N/A')[:10] if page.get('last_modified') else 'N/A'} |

## Conteúdo

{data.get('content_preview', 'Sem conteúdo disponível')}

---

*Comprimento total: {data.get('content_length', 0)} caracteres*
"""
        
        return md
    
    return f"# Tipo desconhecido\n\nDados:\n```json\n{json.dumps(data, indent=2, default=str)}\n```"


def save_to_project(
    data: Dict[str, Any], 
    project: str = "3TPM",
    filename: Optional[str] = None
) -> str:
    """Save explored data to project documentation"""
    
    # Determine filename
    if not filename:
        if data["type"] == "jira_issue":
            issue_key = data["issue"]["key"]
            filename = f"{datetime.now().strftime('%Y-%m-%d')}-{issue_key.lower()}.md"
        elif data["type"] == "confluence_page":
            page_id = data["page"]["id"]
            filename = f"{datetime.now().strftime('%Y-%m-%d')}-confluence-{page_id}.md"
        else:
            filename = f"{datetime.now().strftime('%Y-%m-%d')}-explored.md"
    
    # Determine output directory
    project_dir = PROJECTS_DIR / project
    if project_dir.exists():
        notes_dir = project_dir / "notes"
        notes_dir.mkdir(exist_ok=True)
        output_path = notes_dir / filename
    else:
        # Fallback to general notes
        output_path = DOCS_DIR / "notes" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Generate markdown
    markdown = generate_markdown(data)
    
    # Save
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown)
    
    return str(output_path)


def explore(
    target: str,
    save: bool = False,
    project: str = "3TPM"
) -> Dict[str, Any]:
    """
    Main exploration function.
    
    Args:
        target: Jira issue key (BEESIP-123) or URL
        save: Whether to save to project docs
        project: Project to save to (default: 3TPM)
    
    Returns:
        Explored data with optional save path
    """
    print(f"[{datetime.now().isoformat()}] Exploring: {target}")
    
    # Determine type
    if target.startswith("http"):
        parsed = parse_atlassian_url(target)
        if parsed["type"] == "jira":
            data = explore_jira_issue(parsed["id"])
        elif parsed["type"] == "confluence":
            data = explore_confluence_page(parsed["id"])
        else:
            raise ValueError(f"Unknown URL type: {target}")
    elif re.match(r'^[A-Z]+-\d+$', target):
        # Jira issue key
        data = explore_jira_issue(target)
    else:
        raise ValueError(f"Unknown target format: {target}")
    
    print(f"  Type: {data['type']}")
    
    # Save if requested
    if save:
        save_path = save_to_project(data, project=project)
        data["saved_to"] = save_path
        print(f"  Saved to: {save_path}")
    
    return data


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Explore Jira/Confluence items")
    parser.add_argument("target", help="Jira issue key (BEESIP-123) or URL")
    parser.add_argument("--save", action="store_true", help="Save to project docs")
    parser.add_argument("--project", default="3TPM", help="Project to save to")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    try:
        data = explore(args.target, save=args.save, project=args.project)
        
        if args.json:
            print(json.dumps(data, indent=2, default=str))
        else:
            print("\n" + generate_markdown(data))
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

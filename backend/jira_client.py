#!/usr/bin/env python3
"""
Jira REST API Client
Handles authentication and API calls to Atlassian Jira Cloud

Uses the same credentials as Confluence (Atlassian Cloud API Token)
"""

import os
import re
import base64
import httpx
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
BACKEND_DIR = Path(__file__).parent
load_dotenv(BACKEND_DIR / '.env')


class JiraClient:
    """Synchronous Jira REST API client"""
    
    def __init__(self):
        self.email = os.getenv("CONFLUENCE_EMAIL")  # Same credentials
        self.api_token = os.getenv("CONFLUENCE_API_TOKEN")
        self.base_url = os.getenv("JIRA_BASE_URL", "https://ab-inbev.atlassian.net")
        
        if not self.email or not self.api_token:
            raise ValueError("CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN must be set in .env")
        
        # Basic auth
        credentials = f"{self.email}:{self.api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        
        self.headers = {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        self.client = httpx.Client(timeout=30.0)
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to Jira API"""
        url = f"{self.base_url}{endpoint}"
        response = self.client.request(method=method, url=url, headers=self.headers, **kwargs)
        response.raise_for_status()
        return response.json()
    
    def get_issue(self, issue_key: str, expand: str = None) -> Dict[str, Any]:
        """
        Get issue details by key (e.g., BEESIP-123, BEESCAD-456)
        
        Args:
            issue_key: Jira issue key
            expand: Fields to expand (e.g., "changelog,renderedFields")
        
        Returns:
            Issue details including fields, status, description, etc.
        """
        params = {}
        if expand:
            params["expand"] = expand
        
        return self._request("GET", f"/rest/api/3/issue/{issue_key}", params=params)
    
    def get_issue_summary(self, issue_key: str) -> Dict[str, Any]:
        """Get a clean summary of an issue"""
        issue = self.get_issue(issue_key, expand="renderedFields")
        fields = issue.get("fields", {})
        
        # Extract clean description
        description = ""
        if fields.get("description"):
            desc = fields["description"]
            if isinstance(desc, dict):
                # ADF format - extract text
                description = self._extract_text_from_adf(desc)
            else:
                description = str(desc)
        
        # Extract rendered description if available
        rendered = issue.get("renderedFields", {})
        if rendered.get("description"):
            description = self._clean_html(rendered["description"])
        
        return {
            "key": issue.get("key"),
            "summary": fields.get("summary"),
            "status": fields.get("status", {}).get("name"),
            "priority": fields.get("priority", {}).get("name") if fields.get("priority") else None,
            "issue_type": fields.get("issuetype", {}).get("name"),
            "description": description[:2000] if description else None,  # Limit length
            "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
            "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
            "created": fields.get("created"),
            "updated": fields.get("updated"),
            "labels": fields.get("labels", []),
            "components": [c.get("name") for c in fields.get("components", [])],
            "url": f"{self.base_url}/browse/{issue.get('key')}"
        }
    
    def get_issue_comments(self, issue_key: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Get comments for an issue"""
        response = self._request("GET", f"/rest/api/3/issue/{issue_key}/comment", 
                                 params={"maxResults": max_results})
        
        comments = []
        for comment in response.get("comments", []):
            body = comment.get("body", {})
            text = self._extract_text_from_adf(body) if isinstance(body, dict) else str(body)
            
            comments.append({
                "author": comment.get("author", {}).get("displayName"),
                "created": comment.get("created"),
                "body": text[:500] if text else None  # Limit length
            })
        
        return comments
    
    def get_linked_issues(self, issue_key: str) -> List[Dict[str, Any]]:
        """Get issues linked to this issue"""
        issue = self.get_issue(issue_key)
        fields = issue.get("fields", {})
        
        linked = []
        for link in fields.get("issuelinks", []):
            if link.get("outwardIssue"):
                linked_issue = link["outwardIssue"]
                linked.append({
                    "key": linked_issue.get("key"),
                    "summary": linked_issue.get("fields", {}).get("summary"),
                    "status": linked_issue.get("fields", {}).get("status", {}).get("name"),
                    "relationship": link.get("type", {}).get("outward")
                })
            elif link.get("inwardIssue"):
                linked_issue = link["inwardIssue"]
                linked.append({
                    "key": linked_issue.get("key"),
                    "summary": linked_issue.get("fields", {}).get("summary"),
                    "status": linked_issue.get("fields", {}).get("status", {}).get("name"),
                    "relationship": link.get("type", {}).get("inward")
                })
        
        return linked
    
    def search_issues(self, jql: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Search issues using JQL
        
        Args:
            jql: JQL query string
            max_results: Maximum results to return
        
        Returns:
            List of issue summaries
        """
        # Try API v2 first, then v3
        try:
            response = self._request("GET", "/rest/api/2/search", params={
                "jql": jql,
                "maxResults": max_results,
                "fields": "summary,status,priority,issuetype,assignee,updated"
            })
        except:
            response = self._request("GET", "/rest/api/3/search", params={
                "jql": jql,
                "maxResults": max_results,
                "fields": "summary,status,priority,issuetype,assignee,updated"
            })
        
        issues = []
        for issue in response.get("issues", []):
            fields = issue.get("fields", {})
            issues.append({
                "key": issue.get("key"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "priority": fields.get("priority", {}).get("name") if fields.get("priority") else None,
                "type": fields.get("issuetype", {}).get("name"),
                "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
                "updated": fields.get("updated"),
                "url": f"{self.base_url}/browse/{issue.get('key')}"
            })
        
        return issues
    
    def get_initiative_with_epics(self, initiative_key: str) -> Dict[str, Any]:
        """
        Get an initiative (BEESIP) with all its linked epics
        """
        # Get the initiative
        initiative = self.get_issue_summary(initiative_key)
        
        # Search for epics linked to this initiative
        jql = f'"Parent Link" = {initiative_key} OR "Initiative Link" = {initiative_key}'
        try:
            epics = self.search_issues(jql, max_results=100)
        except:
            # Fallback: get linked issues
            epics = self.get_linked_issues(initiative_key)
        
        return {
            "initiative": initiative,
            "epics": epics,
            "epic_count": len(epics)
        }
    
    def test_connection(self) -> bool:
        """Test if the connection works"""
        try:
            response = self._request("GET", "/rest/api/3/myself")
            return "accountId" in response
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
    
    def _extract_text_from_adf(self, adf: Dict) -> str:
        """Extract plain text from Atlassian Document Format"""
        if not adf or not isinstance(adf, dict):
            return ""
        
        text_parts = []
        
        def extract_recursive(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    text_parts.append(node.get("text", ""))
                for child in node.get("content", []):
                    extract_recursive(child)
            elif isinstance(node, list):
                for item in node:
                    extract_recursive(item)
        
        extract_recursive(adf)
        return " ".join(text_parts)
    
    def _clean_html(self, html: str) -> str:
        """Remove HTML tags and clean up text"""
        if not html:
            return ""
        # Simple HTML tag removal
        import re
        clean = re.sub(r'<[^>]+>', ' ', html)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()
    
    def close(self):
        """Close the HTTP client"""
        self.client.close()


def parse_atlassian_url(url: str) -> Dict[str, str]:
    """
    Parse an Atlassian URL to extract type and ID
    
    Supports:
    - Jira issues: /browse/BEESIP-123
    - Confluence pages: /wiki/spaces/XXX/pages/123456/Title
    
    Returns:
        Dict with 'type' ('jira' or 'confluence') and 'id'
    """
    # Jira issue pattern
    jira_match = re.search(r'/browse/([A-Z]+-\d+)', url)
    if jira_match:
        return {"type": "jira", "id": jira_match.group(1)}
    
    # Confluence page pattern
    confluence_match = re.search(r'/wiki/spaces/[^/]+/pages/(\d+)', url)
    if confluence_match:
        return {"type": "confluence", "id": confluence_match.group(1)}
    
    # Confluence page by ID only
    confluence_id_match = re.search(r'/pages/(\d+)', url)
    if confluence_id_match:
        return {"type": "confluence", "id": confluence_id_match.group(1)}
    
    return {"type": "unknown", "id": None}


# CLI for testing
if __name__ == "__main__":
    import sys
    import json
    
    client = JiraClient()
    
    if len(sys.argv) > 1:
        issue_key = sys.argv[1]
        
        print(f"\n=== Issue: {issue_key} ===\n")
        
        try:
            summary = client.get_issue_summary(issue_key)
            print(json.dumps(summary, indent=2, default=str))
            
            print(f"\n=== Linked Issues ===\n")
            linked = client.get_linked_issues(issue_key)
            for link in linked[:5]:
                print(f"  - {link['key']}: {link['summary'][:50]}... ({link['status']})")
            
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Testing connection...")
        if client.test_connection():
            print("Connection successful!")
        else:
            print("Connection failed!")
    
    client.close()

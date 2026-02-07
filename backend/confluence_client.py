#!/usr/bin/env python3
"""
Confluence REST API Client
Handles authentication and API calls to Atlassian Confluence Cloud
"""

import os
import base64
import httpx
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class ConfluenceClient:
    """Client for Confluence REST API v2"""
    
    def __init__(self):
        self.email = os.getenv("CONFLUENCE_EMAIL")
        self.api_token = os.getenv("CONFLUENCE_API_TOKEN")
        self.base_url = os.getenv("CONFLUENCE_BASE_URL", "https://ab-inbev.atlassian.net/wiki")
        self.page_id = os.getenv("CONFLUENCE_PAGE_ID", "5444239480")
        
        if not self.email or not self.api_token:
            raise ValueError("CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN must be set in .env")
        
        # Create Basic Auth header
        credentials = f"{self.email}:{self.api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        
        self.headers = {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        self.client = httpx.Client(timeout=30.0)
    
    def __del__(self):
        """Cleanup HTTP client"""
        if hasattr(self, 'client'):
            self.client.close()
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an API request"""
        url = f"{self.base_url}{endpoint}"
        
        response = self.client.request(
            method=method,
            url=url,
            headers=self.headers,
            **kwargs
        )
        
        response.raise_for_status()
        return response.json()
    
    def get_page(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        """Get page metadata"""
        pid = page_id or self.page_id
        return self._request("GET", f"/api/v2/pages/{pid}")
    
    def get_page_body(self, page_id: Optional[str] = None, format: str = "storage") -> str:
        """
        Get page body content
        
        Args:
            page_id: Page ID (uses default if not provided)
            format: Body format - 'storage' (raw), 'atlas_doc_format', 'view' (rendered HTML)
        
        Returns:
            Page body content as string
        """
        pid = page_id or self.page_id
        
        # API v2 includes body in page response with body-format parameter
        response = self._request(
            "GET", 
            f"/api/v2/pages/{pid}",
            params={"body-format": format}
        )
        
        return response.get("body", {}).get(format, {}).get("value", "")
    
    def get_page_html(self, page_id: Optional[str] = None) -> str:
        """Get page body as rendered HTML (view format)"""
        return self.get_page_body(page_id, format="view")
    
    def get_page_storage(self, page_id: Optional[str] = None) -> str:
        """Get page body in storage format (Confluence XML)"""
        return self.get_page_body(page_id, format="storage")
    
    # ── Jira REST API methods ──────────────────────────────────────────
    
    @property
    def jira_base_url(self) -> str:
        """Derive Jira base URL from Confluence URL (same Atlassian site)"""
        # https://ab-inbev.atlassian.net/wiki -> https://ab-inbev.atlassian.net
        return self.base_url.replace("/wiki", "")
    
    def _jira_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a Jira REST API request"""
        url = f"{self.jira_base_url}{endpoint}"
        response = self.client.request(
            method=method,
            url=url,
            headers=self.headers,
            **kwargs
        )
        response.raise_for_status()
        return response.json()
    
    def search_jira(self, jql: str, fields: List[str] = None, max_results: int = 100) -> List[Dict[str, Any]]:
        """
        Execute a JQL search against the Jira REST API.
        
        Uses /rest/api/3/search/jql (the new endpoint, as /rest/api/3/search is 410 Gone).
        
        Args:
            jql: JQL query string
            fields: List of fields to return (e.g. ["summary", "status", "priority"])
            max_results: Maximum number of results
            
        Returns:
            List of issue dicts with key and requested fields
        """
        if fields is None:
            fields = ["summary", "status", "priority", "assignee"]
        
        payload = {
            "jql": jql,
            "fields": fields,
            "maxResults": max_results
        }
        
        try:
            data = self._jira_request("POST", "/rest/api/3/search/jql", json=payload)
            return data.get("issues", [])
        except Exception as e:
            print(f"Jira search failed: {e}")
            return []
    
    def get_issues_batch(self, keys: List[str], fields: List[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Batch-fetch issue details by keys.
        
        Args:
            keys: List of Jira issue keys (e.g. ["BEESIP-10009", "BEESCAD-20981"])
            fields: Fields to retrieve
            
        Returns:
            Dict mapping issue key -> {summary, status, priority, ...}
        """
        if not keys:
            return {}
        
        if fields is None:
            fields = ["summary", "status", "priority", "assignee", "issuetype"]
        
        result = {}
        
        # Jira has a limit on JQL length, batch in groups of 50
        batch_size = 50
        for i in range(0, len(keys), batch_size):
            batch = keys[i:i + batch_size]
            jql = f"key in ({','.join(batch)})"
            
            issues = self.search_jira(jql, fields=fields, max_results=batch_size)
            
            for issue in issues:
                key = issue.get("key", "")
                fields_data = issue.get("fields", {})
                
                # Normalize status and priority to simple strings
                status_obj = fields_data.get("status", {})
                priority_obj = fields_data.get("priority", {})
                assignee_obj = fields_data.get("assignee", {})
                issuetype_obj = fields_data.get("issuetype", {})
                
                result[key] = {
                    "summary": fields_data.get("summary", ""),
                    "status": status_obj.get("name", "") if status_obj else "",
                    "priority": priority_obj.get("name", "") if priority_obj else "",
                    "assignee": assignee_obj.get("displayName", "") if assignee_obj else "",
                    "issuetype": issuetype_obj.get("name", "") if issuetype_obj else "",
                }
        
        return result
    
    # ── Confluence page methods ──────────────────────────────────────
    
    def test_connection(self) -> bool:
        """Test if the API connection works"""
        try:
            page = self.get_page()
            return "id" in page
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
    
    def get_situation_wall(self) -> Dict[str, Any]:
        """
        Get the Situation Wall page with full content
        
        Returns:
            Dict with page metadata and body content
        """
        page = self.get_page()
        html_content = self.get_page_html()
        storage_content = self.get_page_storage()
        
        return {
            "id": page.get("id"),
            "title": page.get("title"),
            "version": page.get("version", {}).get("number"),
            "last_modified": page.get("version", {}).get("createdAt"),
            "html_content": html_content,
            "storage_content": storage_content
        }


class AsyncConfluenceClient:
    """Async client for Confluence REST API v2"""
    
    def __init__(self):
        self.email = os.getenv("CONFLUENCE_EMAIL")
        self.api_token = os.getenv("CONFLUENCE_API_TOKEN")
        self.base_url = os.getenv("CONFLUENCE_BASE_URL", "https://ab-inbev.atlassian.net/wiki")
        self.page_id = os.getenv("CONFLUENCE_PAGE_ID", "5444239480")
        
        if not self.email or not self.api_token:
            raise ValueError("CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN must be set in .env")
        
        credentials = f"{self.email}:{self.api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        
        self.headers = {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an async API request"""
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self.headers,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
    
    async def get_page(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        """Get page metadata"""
        pid = page_id or self.page_id
        return await self._request("GET", f"/api/v2/pages/{pid}")
    
    async def get_page_body(self, page_id: Optional[str] = None, format: str = "storage") -> str:
        """Get page body content"""
        pid = page_id or self.page_id
        response = await self._request(
            "GET", 
            f"/api/v2/pages/{pid}",
            params={"body-format": format}
        )
        return response.get("body", {}).get(format, {}).get("value", "")
    
    async def get_page_html(self, page_id: Optional[str] = None) -> str:
        """Get page body as rendered HTML"""
        return await self.get_page_body(page_id, format="view")
    
    async def get_page_storage(self, page_id: Optional[str] = None) -> str:
        """Get page body in storage format (Confluence XML)"""
        return await self.get_page_body(page_id, format="storage")
    
    # ── Jira REST API methods (async) ────────────────────────────────
    
    @property
    def jira_base_url(self) -> str:
        """Derive Jira base URL from Confluence URL"""
        return self.base_url.replace("/wiki", "")
    
    async def _jira_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an async Jira REST API request"""
        url = f"{self.jira_base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self.headers,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
    
    async def search_jira(self, jql: str, fields: List[str] = None, max_results: int = 100) -> List[Dict[str, Any]]:
        """Execute a JQL search against the Jira REST API (async)."""
        if fields is None:
            fields = ["summary", "status", "priority", "assignee"]
        
        payload = {
            "jql": jql,
            "fields": fields,
            "maxResults": max_results
        }
        
        try:
            data = await self._jira_request("POST", "/rest/api/3/search/jql", json=payload)
            return data.get("issues", [])
        except Exception as e:
            print(f"Jira search failed: {e}")
            return []
    
    async def get_issues_batch(self, keys: List[str], fields: List[str] = None) -> Dict[str, Dict[str, Any]]:
        """Batch-fetch issue details by keys (async)."""
        if not keys:
            return {}
        
        if fields is None:
            fields = ["summary", "status", "priority", "assignee", "issuetype"]
        
        result = {}
        batch_size = 50
        for i in range(0, len(keys), batch_size):
            batch = keys[i:i + batch_size]
            jql = f"key in ({','.join(batch)})"
            issues = await self.search_jira(jql, fields=fields, max_results=batch_size)
            
            for issue in issues:
                key = issue.get("key", "")
                fields_data = issue.get("fields", {})
                status_obj = fields_data.get("status", {})
                priority_obj = fields_data.get("priority", {})
                assignee_obj = fields_data.get("assignee", {})
                issuetype_obj = fields_data.get("issuetype", {})
                
                result[key] = {
                    "summary": fields_data.get("summary", ""),
                    "status": status_obj.get("name", "") if status_obj else "",
                    "priority": priority_obj.get("name", "") if priority_obj else "",
                    "assignee": assignee_obj.get("displayName", "") if assignee_obj else "",
                    "issuetype": issuetype_obj.get("name", "") if issuetype_obj else "",
                }
        
        return result
    
    # ── Situation Wall ───────────────────────────────────────────────
    
    async def get_situation_wall(self) -> Dict[str, Any]:
        """Get the Situation Wall page with full content"""
        page = await self.get_page()
        html_content = await self.get_page_html()
        storage_content = await self.get_page_storage()
        
        return {
            "id": page.get("id"),
            "title": page.get("title"),
            "version": page.get("version", {}).get("number"),
            "last_modified": page.get("version", {}).get("createdAt"),
            "html_content": html_content,
            "storage_content": storage_content
        }


# Quick test
if __name__ == "__main__":
    client = ConfluenceClient()
    
    print("Testing Confluence connection...")
    if client.test_connection():
        print("✓ Connection successful!")
        
        page = client.get_page()
        print(f"✓ Page title: {page.get('title')}")
        print(f"✓ Page version: {page.get('version', {}).get('number')}")
    else:
        print("✗ Connection failed!")

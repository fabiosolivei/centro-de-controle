#!/usr/bin/env python3
"""
Confluence REST API Client
Handles authentication and API calls to Atlassian Confluence Cloud
"""

import os
import base64
import httpx
from typing import Optional, Dict, Any
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
    
    async def get_situation_wall(self) -> Dict[str, Any]:
        """Get the Situation Wall page with full content"""
        page = await self.get_page()
        html_content = await self.get_page_html()
        
        return {
            "id": page.get("id"),
            "title": page.get("title"),
            "version": page.get("version", {}).get("number"),
            "last_modified": page.get("version", {}).get("createdAt"),
            "html_content": html_content
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

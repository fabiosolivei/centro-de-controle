#!/usr/bin/env python3
"""
Situation Wall Parser v2
Extracts structured data from the Confluence Situation Wall page
using the storage format (XML) for reliable parsing.

The storage format contains structured macros with explicit parameters,
avoiding the broken regex-on-HTML approach that produced garbage data.
"""

import re
import json
import html
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime

from confluence_client import ConfluenceClient


@dataclass
class Sprint:
    """Sprint information"""
    name: str
    number: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    release_date: Optional[str] = None
    is_current: bool = False


@dataclass
class Initiative:
    """Initiative (BEESIP) information"""
    beesip_id: str
    title: str
    status: str
    priority: str
    team: str
    category: str = ""
    kickoff_date: Optional[str] = None
    zone_approval: Optional[str] = None
    jira_url: Optional[str] = None


@dataclass
class Epic:
    """Epic (BEESCAD) linked to an Initiative"""
    beescad_id: str
    initiative_beesip: Optional[str] = None
    title: str = ""
    status: str = ""
    size: str = ""
    sprint: Optional[str] = None
    milestones: Optional[Dict[str, str]] = None
    jira_url: Optional[str] = None


@dataclass
class Risk:
    """Risk item"""
    beescad_id: str
    title: str
    assignee: str
    status: str
    priority: str
    gut_score: int
    jira_url: Optional[str] = None


@dataclass
class Bug:
    """Bug item"""
    beescad_id: str
    title: str
    priority: str
    status: str
    team: str
    jira_url: Optional[str] = None


# ── Emoji to priority mapping ──────────────────────────────────────

EMOJI_PRIORITY_MAP = {
    ":high:": "High",
    ":medium:": "Medium",
    ":low:": "Low",
    ":block_1:": "Block 1",
    ":block_2:": "Block 2",
    ":critical:": "Critical",
}

# ── Size patterns ──────────────────────────────────────────────────

VALID_SIZES = {"XXS", "XS", "S", "M", "L", "XL", "XXL"}


class SituationWallParser:
    """
    Parser for the Situation Wall Confluence page.
    
    Uses the storage format (Confluence XML) for reliable extraction
    of structural data. Issue titles are enriched separately via Jira API.
    """
    
    TEAMS_OF_INTEREST = ["CATALOG", "CONTENT", "CMS", "DAM", "PIM", "COMPANY"]
    
    # Regex patterns for extracting data from storage XML
    MACRO_PATTERN = re.compile(
        r'<ac:structured-macro[^>]*?ac:name="(\w+)"[^>]*>(.*?)</ac:structured-macro>',
        re.DOTALL
    )
    PARAM_PATTERN = re.compile(
        r'<ac:parameter ac:name="(\w+)">([^<]*)</ac:parameter>'
    )
    EMOJI_PATTERN = re.compile(
        r'ac:emoji-shortname="([^"]+)"'
    )
    ROW_PATTERN = re.compile(
        r'<tr[^>]*>(.*?)</tr>',
        re.DOTALL
    )
    CELL_PATTERN = re.compile(
        r'<t[hd][^>]*>(.*?)</t[hd]>',
        re.DOTALL
    )
    TAG_PATTERN = re.compile(r'<[^>]+>')
    
    def __init__(self, storage_content: str):
        """
        Initialize parser with Confluence storage format content.
        
        Args:
            storage_content: The page body in storage format (XML)
        """
        self.storage = storage_content
        self._jql_risks: Optional[str] = None
        self._jql_bugs: Optional[str] = None
    
    def _extract_macros(self, xml_text: str) -> List[Dict[str, Any]]:
        """Extract all structured macros from an XML snippet."""
        results = []
        for match in self.MACRO_PATTERN.finditer(xml_text):
            macro_type = match.group(1)
            content = match.group(2)
            params = dict(self.PARAM_PATTERN.findall(content))
            results.append({"type": macro_type, "params": params})
        return results
    
    def _extract_emojis(self, xml_text: str) -> List[str]:
        """Extract emoji shortnames from an XML snippet."""
        return self.EMOJI_PATTERN.findall(xml_text)
    
    def _clean_text(self, xml_text: str) -> str:
        """Remove XML tags and clean whitespace, decode HTML entities."""
        text = self.TAG_PATTERN.sub(' ', xml_text)
        text = html.unescape(text)
        return ' '.join(text.split()).strip()
    
    def _extract_cells(self, row_xml: str) -> List[str]:
        """Extract table cells from a row."""
        return self.CELL_PATTERN.findall(row_xml)
    
    def _emoji_to_priority(self, emojis: List[str]) -> str:
        """Convert emoji shortnames to priority string."""
        for emoji in emojis:
            if emoji in EMOJI_PRIORITY_MAP:
                return EMOJI_PRIORITY_MAP[emoji]
        return "Medium"
    
    def _extract_size_from_text(self, text: str) -> str:
        """Extract epic size (XXS, S, M, L, etc.) from cell text."""
        # Size appears as first word before the BEESCAD key
        words = text.split()
        for word in words:
            clean = word.strip().upper()
            if clean in VALID_SIZES:
                return clean
        return ""
    
    def _find_section(self, start_marker: str, end_marker: str) -> Optional[str]:
        """Find a section of storage content between two markers."""
        match = re.search(
            re.escape(start_marker) + r'(.*?)' + re.escape(end_marker),
            self.storage, re.DOTALL
        )
        if match:
            return match.group(1)
        
        # Try case-insensitive with simpler markers
        match = re.search(
            start_marker + r'(.*?)' + end_marker,
            self.storage, re.DOTALL | re.IGNORECASE
        )
        return match.group(1) if match else None
    
    # ── Sprint parsing ─────────────────────────────────────────────
    
    def parse_sprints(self) -> List[Sprint]:
        """Extract sprint information from the Common/Q1 Official Releases section."""
        sprints = []
        
        # Get clean text from storage
        text = self._clean_text(self.storage)
        
        # Pattern: Sprint 185: January 26 - February 06 → → Release: 18 de fev. de 2026
        sprint_pattern = r'Sprint (\d+):\s*([A-Za-z]+\s+\d+)\s*[-–]\s*([A-Za-z]+\s+\d+)'
        
        for match in re.finditer(sprint_pattern, text):
            sprint_num = int(match.group(1))
            start = match.group(2)
            end = match.group(3)
            
            # Try to find release date
            release_date = None
            release_match = re.search(
                rf'Sprint {sprint_num}.*?Release[:\s]+(\d+\s+de\s+\w+\.?\s+de\s+\d+)',
                text, re.IGNORECASE
            )
            if release_match:
                release_date = release_match.group(1)
            
            # Current sprint detection: arrow_right emoji appears directly
            # before the current sprint in the storage XML.
            # Match within a small window (500 chars) to avoid false positives.
            is_current = False
            arrow_match = re.search(r'arrow_right', self.storage)
            if arrow_match:
                # Check if this sprint number appears within 500 chars after the arrow
                nearby = self.storage[arrow_match.start():arrow_match.start() + 500]
                if re.search(rf'Sprint {sprint_num}', nearby):
                    is_current = True
            
            sprints.append(Sprint(
                name=f"Sprint {sprint_num}",
                number=sprint_num,
                start_date=start,
                end_date=end,
                release_date=release_date,
                is_current=is_current
            ))
        
        return sprints
    
    # ── Initiative parsing (from EXECUTION PRIORITIES section) ─────
    
    def parse_initiatives(self) -> List[Initiative]:
        """
        Extract initiatives from the Q4 EXECUTION PRIORITIES section.
        
        Each initiative row in the priorities table has:
        - status macro -> team name (CATALOG, CONTENT)
        - emoticon -> priority (:high:, :medium:, :block_1:)
        - jira macro -> issue key (BEESIP-xxxxx)
        - trailing text -> category ([Delivery], [cross-quarter])
        """
        initiatives = []
        seen_ids = set()
        
        # Find the EXECUTION PRIORITIES section (before END-TO-END table)
        section = self._find_section(
            r'EXECUTION PRIORITIES',
            r'END-TO-END'
        )
        if not section:
            print("  WARNING: Could not find EXECUTION PRIORITIES section")
            return initiatives
        
        # Parse each table row in this section
        rows = self.ROW_PATTERN.findall(section)
        
        for row in rows:
            cells = self._extract_cells(row)
            if not cells:
                continue
            
            # The initiative data is in the first cell
            cell = cells[0]
            
            # Skip if no BEESIP key
            macros = self._extract_macros(cell)
            jira_macros = [m for m in macros if m["type"] == "jira"]
            if not jira_macros:
                continue
            
            beesip_id = jira_macros[0]["params"].get("key", "")
            if not beesip_id or not beesip_id.startswith("BEESIP-"):
                continue
            if beesip_id in seen_ids:
                continue
            seen_ids.add(beesip_id)
            
            # Team from status macro
            status_macros = [m for m in macros if m["type"] == "status"]
            team = status_macros[0]["params"].get("title", "UNKNOWN") if status_macros else "UNKNOWN"
            
            # Priority from emoji
            emojis = self._extract_emojis(cell)
            priority = self._emoji_to_priority(emojis)
            
            # Category from trailing text (e.g., "[Delivery]", "[cross-quarter]")
            # Text after the last </ac:structured-macro>
            parts = cell.split('</ac:structured-macro>')
            trailing = self._clean_text(parts[-1]) if parts else ""
            category = ""
            cat_match = re.search(r'\[([^\]]+)\]', trailing)
            if cat_match:
                category = cat_match.group(1).strip()
            
            initiatives.append(Initiative(
                beesip_id=beesip_id,
                title="",  # Filled by Jira API enrichment
                status="",  # Filled by Jira API enrichment
                priority=priority,
                team=team.upper(),
                category=category,
                jira_url=f"https://ab-inbev.atlassian.net/browse/{beesip_id}"
            ))
        
        return initiatives
    
    # ── Epic parsing (from END-TO-END EXECUTION PLAN table) ───────
    
    def parse_epics(self) -> List[Epic]:
        """
        Extract epics from the END-TO-END EXECUTION PLAN table.
        
        Each table row has 13 cells:
        - Cell 0: Row number
        - Cell 1: Initiative (jira macro with key, emoji for priority)
        - Cell 2: Epic (size letter + jira macro with key)
        - Cells 3-10: Milestone checkpoints
        - Cell 11: Team (status macro)
        - Cell 12: Comments
        """
        epics = []
        seen_ids = set()
        
        # Find the END-TO-END section
        plan_section = re.search(
            r'END-TO-END EXECUTION PLAN(.*)',
            self.storage, re.DOTALL
        )
        if not plan_section:
            print("  WARNING: Could not find END-TO-END EXECUTION PLAN section")
            return epics
        
        plan_text = plan_section.group(1)
        rows = self.ROW_PATTERN.findall(plan_text)
        
        for row in rows:
            cells = self._extract_cells(row)
            if len(cells) < 3:
                continue
            
            # Cell 1: Initiative key
            init_macros = self._extract_macros(cells[1])
            init_jira = [m for m in init_macros if m["type"] == "jira"]
            initiative_key = None
            if init_jira:
                key = init_jira[0]["params"].get("key", "")
                if key.startswith("BEESIP-"):
                    initiative_key = key
            
            # Cell 2: Epic key + size
            epic_macros = self._extract_macros(cells[2])
            epic_jira = [m for m in epic_macros if m["type"] == "jira"]
            if not epic_jira:
                continue
            
            beescad_id = epic_jira[0]["params"].get("key", "")
            if not beescad_id or not beescad_id.startswith("BEESCAD-"):
                continue
            if beescad_id in seen_ids:
                continue
            seen_ids.add(beescad_id)
            
            # Size from text before the BEESCAD key
            epic_text = self._clean_text(cells[2])
            size = self._extract_size_from_text(epic_text)
            
            # Sprint reference from milestone cells (cells 3-10)
            sprint = None
            for cell_idx in range(3, min(11, len(cells))):
                cell_text = self._clean_text(cells[cell_idx])
                sp_match = re.search(r'\[?SP-(\d+)\]?', cell_text)
                if sp_match:
                    sprint = f"SP-{sp_match.group(1)}"
                    break
            
            # Team from cell 11 (if available)
            team = ""
            if len(cells) > 11:
                team_macros = self._extract_macros(cells[11])
                team_status = [m for m in team_macros if m["type"] == "status"]
                if team_status:
                    team = team_status[0]["params"].get("title", "")
            
            # Comments from cell 12 (if available)
            comments = ""
            if len(cells) > 12:
                comments = self._clean_text(cells[12])
            
            epics.append(Epic(
                beescad_id=beescad_id,
                initiative_beesip=initiative_key,
                title="",  # Filled by Jira API enrichment
                status="",  # Filled by Jira API enrichment
                size=size,
                sprint=sprint,
                milestones={"comments": comments} if comments else None,
                jira_url=f"https://ab-inbev.atlassian.net/browse/{beescad_id}"
            ))
        
        return epics
    
    # ── JQL extraction for Risks and Bugs ─────────────────────────
    
    def extract_risks_jql(self) -> Optional[str]:
        """Extract the JQL query for risks from the RISKS/BLOCKERS Jira macro."""
        if self._jql_risks is not None:
            return self._jql_risks
        
        match = re.search(
            r'RISKS.*?<ac:parameter ac:name="jqlQuery">([^<]+)</ac:parameter>',
            self.storage, re.DOTALL | re.IGNORECASE
        )
        if match:
            self._jql_risks = html.unescape(match.group(1)).strip()
            return self._jql_risks
        return None
    
    def extract_bugs_jql(self) -> Optional[str]:
        """Extract the JQL query for bugs from the BUGS Jira macro."""
        if self._jql_bugs is not None:
            return self._jql_bugs
        
        match = re.search(
            r'BUGS.*?<ac:parameter ac:name="jqlQuery">([^<]+)</ac:parameter>',
            self.storage, re.DOTALL | re.IGNORECASE
        )
        if match:
            self._jql_bugs = html.unescape(match.group(1)).strip()
            return self._jql_bugs
        return None
    
    # ── Empty stubs for risks/bugs (filled by Jira API) ──────────
    
    def parse_risks(self) -> List[Risk]:
        """
        Risks are rendered from a JQL macro - cannot parse from storage.
        Use extract_risks_jql() + Jira API to get actual data.
        Returns empty list (populated by sync script via Jira API).
        """
        return []
    
    def parse_bugs(self) -> List[Bug]:
        """
        Bugs are rendered from a JQL macro - cannot parse from storage.
        Use extract_bugs_jql() + Jira API to get actual data.
        Returns empty list (populated by sync script via Jira API).
        """
        return []
    
    # ── Main parse method ─────────────────────────────────────────
    
    def parse_all(self) -> Dict[str, Any]:
        """Parse all data from the storage format."""
        initiatives = self.parse_initiatives()
        epics = self.parse_epics()
        sprints = self.parse_sprints()
        
        return {
            "sprints": [asdict(s) for s in sprints],
            "initiatives": [asdict(i) for i in initiatives],
            "epics": [asdict(e) for e in epics],
            "risks": [],  # Populated via Jira API
            "bugs": [],   # Populated via Jira API
            "risks_jql": self.extract_risks_jql(),
            "bugs_jql": self.extract_bugs_jql(),
            "parsed_at": datetime.now().isoformat()
        }
    
    def enrich_with_jira_data(self, data: Dict[str, Any], jira_issues: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Enrich parsed data with titles/statuses from Jira API.
        
        Args:
            data: Output from parse_all()
            jira_issues: Dict mapping issue key -> {summary, status, priority, ...}
                         (from ConfluenceClient.get_issues_batch())
        
        Returns:
            Enriched data dict
        """
        enriched_count = 0
        
        for init in data.get("initiatives", []):
            key = init["beesip_id"]
            if key in jira_issues:
                jira = jira_issues[key]
                init["title"] = jira.get("summary", init["title"])
                init["status"] = jira.get("status", init["status"])
                # Keep the page priority (manual) over Jira priority
                enriched_count += 1
        
        for epic in data.get("epics", []):
            key = epic["beescad_id"]
            if key in jira_issues:
                jira = jira_issues[key]
                epic["title"] = jira.get("summary", epic["title"])
                epic["status"] = jira.get("status", epic["status"])
                enriched_count += 1
        
        data["enrichment"] = {
            "jira_issues_fetched": len(jira_issues),
            "items_enriched": enriched_count,
            "enriched_at": datetime.now().isoformat()
        }
        
        return data
    
    def filter_by_teams(self, data: Dict[str, Any], teams: List[str] = None) -> Dict[str, Any]:
        """Filter parsed data by teams of interest."""
        if teams is None:
            teams = self.TEAMS_OF_INTEREST
        
        teams_upper = [t.upper() for t in teams]
        
        return {
            "sprints": data["sprints"],
            "initiatives": [
                i for i in data["initiatives"]
                if i["team"].upper() in teams_upper
            ],
            "epics": data["epics"],
            "risks": [
                r for r in data["risks"]
                if any(t in r.get("title", "").upper() for t in teams_upper)
            ],
            "bugs": [
                b for b in data["bugs"]
                if b.get("team", "").upper() in teams_upper
                or any(t in b.get("title", "").upper() for t in teams_upper)
            ],
            "parsed_at": data["parsed_at"],
            "filtered_by": teams
        }


def fetch_and_parse() -> Dict[str, Any]:
    """Fetch page from Confluence and parse it (using storage format)."""
    client = ConfluenceClient()
    
    print("Fetching Situation Wall from Confluence...")
    page_data = client.get_situation_wall()
    
    print(f"Parsing page: {page_data['title']} (v{page_data['version']})")
    parser = SituationWallParser(page_data['storage_content'])
    
    data = parser.parse_all()
    
    # Collect all issue keys for Jira enrichment
    all_keys = []
    all_keys.extend(i["beesip_id"] for i in data["initiatives"])
    all_keys.extend(e["beescad_id"] for e in data["epics"])
    
    if all_keys:
        print(f"Enriching {len(all_keys)} issues from Jira API...")
        jira_issues = client.get_issues_batch(all_keys)
        print(f"  Got {len(jira_issues)} issue details from Jira")
        parser.enrich_with_jira_data(data, jira_issues)
    
    # Fetch risks via JQL
    risks_jql = data.get("risks_jql")
    if risks_jql:
        print(f"Fetching risks via JQL...")
        risk_issues = client.search_jira(
            risks_jql,
            fields=["summary", "assignee", "status", "priority", "customfield_13715"]
        )
        for issue in risk_issues:
            key = issue.get("key", "")
            fields = issue.get("fields", {})
            status_obj = fields.get("status", {})
            priority_obj = fields.get("priority", {})
            assignee_obj = fields.get("assignee", {})
            gut_field = fields.get("customfield_13715")
            
            data["risks"].append(asdict(Risk(
                beescad_id=key,
                title=fields.get("summary", ""),
                assignee=assignee_obj.get("displayName", "") if assignee_obj else "",
                status=status_obj.get("name", "") if status_obj else "",
                priority=priority_obj.get("name", "") if priority_obj else "",
                gut_score=int(gut_field) if gut_field else 0,
                jira_url=f"https://ab-inbev.atlassian.net/browse/{key}"
            )))
        print(f"  Got {len(data['risks'])} risks")
    
    # Fetch bugs via JQL
    bugs_jql = data.get("bugs_jql")
    if bugs_jql:
        print(f"Fetching bugs via JQL...")
        bug_issues = client.search_jira(
            bugs_jql,
            fields=["summary", "status", "priority", "customfield_13230"]
        )
        for issue in bug_issues:
            key = issue.get("key", "")
            fields = issue.get("fields", {})
            status_obj = fields.get("status", {})
            priority_obj = fields.get("priority", {})
            team_field = fields.get("customfield_13230")
            
            # Team field can be a list of objects or a string
            team = ""
            if isinstance(team_field, list):
                team = ", ".join(t.get("value", "") for t in team_field if isinstance(t, dict))
            elif isinstance(team_field, dict):
                team = team_field.get("value", "")
            elif isinstance(team_field, str):
                team = team_field
            
            data["bugs"].append(asdict(Bug(
                beescad_id=key,
                title=fields.get("summary", ""),
                priority=priority_obj.get("name", "") if priority_obj else "",
                status=status_obj.get("name", "") if status_obj else "",
                team=team,
                jira_url=f"https://ab-inbev.atlassian.net/browse/{key}"
            )))
        print(f"  Got {len(data['bugs'])} bugs")
    
    # Add metadata
    data["page_title"] = page_data["title"]
    data["page_version"] = page_data["version"]
    data["page_last_modified"] = page_data["last_modified"]
    
    return data


if __name__ == "__main__":
    data = fetch_and_parse()
    
    print(f"\n=== Parsed Data Summary ===")
    print(f"Sprints: {len(data['sprints'])}")
    print(f"Initiatives: {len(data['initiatives'])}")
    print(f"Epics: {len(data['epics'])}")
    print(f"Risks: {len(data['risks'])}")
    print(f"Bugs: {len(data['bugs'])}")
    
    if data.get("enrichment"):
        e = data["enrichment"]
        print(f"\nJira enrichment: {e['items_enriched']}/{e['jira_issues_fetched']} issues enriched")
    
    print("\n=== Initiatives ===")
    for init in data['initiatives']:
        print(f"  {init['beesip_id']}: [{init['team']}] {init['title'][:80]} ({init['status']}) [{init['priority']}]")
    
    print("\n=== Epics ===")
    for epic in data['epics'][:10]:
        print(f"  {epic['beescad_id']}: {epic['title'][:60]} (size={epic['size']}, init={epic.get('initiative_beesip', '?')})")
    
    print("\n=== Risks ===")
    for risk in data['risks']:
        print(f"  {risk['beescad_id']}: {risk['title'][:60]} (GUT={risk['gut_score']})")
    
    print("\n=== Bugs ===")
    for bug in data['bugs']:
        print(f"  {bug['beescad_id']}: {bug['title'][:60]} ({bug['status']})")
    
    # Save to file for debugging
    with open("situation_wall_data.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\nData saved to situation_wall_data.json")

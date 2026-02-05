#!/usr/bin/env python3
"""
Situation Wall Parser
Extracts structured data from the Confluence Situation Wall page
"""

import re
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from bs4 import BeautifulSoup

from confluence_client import ConfluenceClient


@dataclass
class Sprint:
    """Sprint information"""
    name: str  # e.g., "Sprint 185"
    number: int  # e.g., 185
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    release_date: Optional[str] = None
    is_current: bool = False


@dataclass
class Initiative:
    """Initiative (BEESIP) information"""
    beesip_id: str  # e.g., "BEESIP-10009"
    title: str
    status: str  # "In Implementation", "In Analysis", etc.
    priority: str  # "High", "Medium", "Block 1"
    team: str  # "CATALOG", "CONTENT", etc.
    kickoff_date: Optional[str] = None
    zone_approval: Optional[str] = None
    jira_url: Optional[str] = None


@dataclass
class Epic:
    """Epic (BEESCAD) linked to an Initiative"""
    beescad_id: str  # e.g., "BEESCAD-20494"
    initiative_beesip: Optional[str] = None
    title: str = ""
    status: str = ""
    size: str = ""  # "XXS", "M", "L", etc.
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


class SituationWallParser:
    """Parser for the Situation Wall Confluence page"""
    
    # Teams of interest
    TEAMS_OF_INTEREST = ["CATALOG", "CONTENT", "CMS", "DAM", "PIM", "COMPANY"]
    
    def __init__(self, html_content: str):
        self.soup = BeautifulSoup(html_content, 'html.parser')
        self.raw_html = html_content
    
    def parse_all(self) -> Dict[str, Any]:
        """Parse all data from the page"""
        return {
            "sprints": [asdict(s) for s in self.parse_sprints()],
            "initiatives": [asdict(i) for i in self.parse_initiatives()],
            "epics": [asdict(e) for e in self.parse_epics()],
            "risks": [asdict(r) for r in self.parse_risks()],
            "bugs": [asdict(b) for b in self.parse_bugs()],
            "parsed_at": datetime.now().isoformat()
        }
    
    def parse_sprints(self) -> List[Sprint]:
        """Extract sprint information from the page"""
        sprints = []
        
        # Look for sprint patterns in the text
        # Format: "Sprint 185: January 26 - February 06 → → Release: 18 de fev. de 2026"
        sprint_pattern = r'Sprint (\d+):\s*([A-Za-z]+\s+\d+)\s*-\s*([A-Za-z]+\s+\d+)'
        
        text = self.soup.get_text()
        
        for match in re.finditer(sprint_pattern, text):
            sprint_num = int(match.group(1))
            start = match.group(2)
            end = match.group(3)
            
            # Try to find release date nearby
            release_date = None
            release_match = re.search(
                rf'Sprint {sprint_num}.*?Release[:\s]+(\d+\s+de\s+\w+\.?\s+de\s+\d+|\w+\s+\d+)',
                text,
                re.IGNORECASE
            )
            if release_match:
                release_date = release_match.group(1)
            
            # Determine if current (has arrow indicator or is current date range)
            is_current = False
            current_marker = re.search(rf':arrow_right:.*Sprint {sprint_num}', text)
            if current_marker:
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
    
    def parse_initiatives(self) -> List[Initiative]:
        """Extract initiatives (BEESIP) from the page"""
        initiatives = []
        seen_ids = set()
        
        # Find all BEESIP links/references
        beesip_pattern = r'(BEESIP-\d+)[:\s]*\[?([^\]]+)\]?'
        
        # Also look for priority indicators
        text = self.raw_html
        
        for match in re.finditer(beesip_pattern, text):
            beesip_id = match.group(1)
            
            if beesip_id in seen_ids:
                continue
            seen_ids.add(beesip_id)
            
            title = match.group(2).strip()
            # Clean up title
            title = re.sub(r'<[^>]+>', '', title)  # Remove HTML tags
            title = title.split(' In ')[0].strip()  # Remove status suffix
            
            # Determine team from context
            team = self._extract_team_from_context(text, beesip_id)
            
            # Determine priority
            priority = self._extract_priority_from_context(text, beesip_id)
            
            # Determine status
            status = self._extract_status_from_context(text, beesip_id)
            
            initiatives.append(Initiative(
                beesip_id=beesip_id,
                title=title,
                status=status,
                priority=priority,
                team=team,
                jira_url=f"https://ab-inbev.atlassian.net/browse/{beesip_id}"
            ))
        
        return initiatives
    
    def parse_epics(self) -> List[Epic]:
        """Extract epics (BEESCAD) from the page"""
        epics = []
        seen_ids = set()
        
        # Find all BEESCAD links/references
        beescad_pattern = r'(BEESCAD-\d+)[:\s]*\[?([^\]<]+)'
        
        text = self.raw_html
        
        for match in re.finditer(beescad_pattern, text):
            beescad_id = match.group(1)
            
            if beescad_id in seen_ids:
                continue
            seen_ids.add(beescad_id)
            
            title = match.group(2).strip()
            title = re.sub(r'<[^>]+>', '', title)
            title = title.split(' In ')[0].strip()
            title = title.split(' Ready ')[0].strip()
            title = title.split(' Backlog')[0].strip()
            
            # Extract status
            status = self._extract_status_from_context(text, beescad_id)
            
            # Extract size if present
            size = ""
            size_match = re.search(rf'(XXS|XS|S|M|L|XL|XXL)\s+{beescad_id}', text)
            if size_match:
                size = size_match.group(1)
            
            # Find linked initiative
            initiative = self._find_linked_initiative(text, beescad_id)
            
            # Find sprint
            sprint = self._extract_sprint_from_context(text, beescad_id)
            
            epics.append(Epic(
                beescad_id=beescad_id,
                initiative_beesip=initiative,
                title=title,
                status=status,
                size=size,
                sprint=sprint,
                jira_url=f"https://ab-inbev.atlassian.net/browse/{beescad_id}"
            ))
        
        return epics
    
    def parse_risks(self) -> List[Risk]:
        """Extract risks from the RISKS/BLOCKERS section"""
        risks = []
        
        # Find the risks section - look for RISKS/BLOCKERS table
        # The risks are typically in a JIRA macro table with specific columns
        
        # Find rows in the risks table
        risk_pattern = r'(BEESCAD-\d+).*?href="([^"]+)"[^>]*>[^<]*</a>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>(\d+)</td>'
        
        text = self.raw_html
        
        # Simpler approach - find risks section and extract
        risks_section = re.search(r'RISKS/BLOCKERS.*?(?=BUGS|$)', text, re.DOTALL | re.IGNORECASE)
        if risks_section:
            section_text = risks_section.group(0)
            
            # Find BEESCAD entries with their data
            beescad_matches = re.findall(r'(BEESCAD-\d+)', section_text)
            
            for beescad_id in set(beescad_matches):
                # Try to extract title
                title_match = re.search(
                    rf'{beescad_id}[^>]*>.*?<[^>]*>([^<]+)',
                    section_text
                )
                title = title_match.group(1) if title_match else ""
                
                # Extract other fields
                assignee = self._extract_field_near(section_text, beescad_id, "assignee")
                status = self._extract_status_from_context(section_text, beescad_id)
                priority = self._extract_priority_from_context(section_text, beescad_id)
                
                # GUT score
                gut_match = re.search(rf'{beescad_id}.*?(\d+)\s*$', section_text, re.MULTILINE)
                gut_score = int(gut_match.group(1)) if gut_match else 0
                
                risks.append(Risk(
                    beescad_id=beescad_id,
                    title=title,
                    assignee=assignee,
                    status=status,
                    priority=priority,
                    gut_score=gut_score,
                    jira_url=f"https://ab-inbev.atlassian.net/browse/{beescad_id}"
                ))
        
        return risks
    
    def parse_bugs(self) -> List[Bug]:
        """Extract bugs from the BUGS section"""
        bugs = []
        
        text = self.raw_html
        
        # Find bugs section
        bugs_section = re.search(r'BUGS.*?(?=SPRINT|CATALOG|$)', text, re.DOTALL | re.IGNORECASE)
        if bugs_section:
            section_text = bugs_section.group(0)
            
            beescad_matches = re.findall(r'(BEESCAD-\d+)', section_text)
            
            for beescad_id in set(beescad_matches):
                # Extract title
                title_match = re.search(
                    rf'{beescad_id}.*?\[([^\]]+)\]',
                    section_text
                )
                title = title_match.group(1) if title_match else ""
                
                status = self._extract_status_from_context(section_text, beescad_id)
                priority = self._extract_priority_from_context(section_text, beescad_id)
                team = self._extract_team_from_context(section_text, beescad_id)
                
                bugs.append(Bug(
                    beescad_id=beescad_id,
                    title=title,
                    priority=priority,
                    status=status,
                    team=team,
                    jira_url=f"https://ab-inbev.atlassian.net/browse/{beescad_id}"
                ))
        
        return bugs
    
    def _extract_team_from_context(self, text: str, issue_id: str) -> str:
        """Extract team name from context around an issue ID"""
        # Look for team indicators near the issue
        pattern = rf'({"|".join(self.TEAMS_OF_INTEREST)}).*?{issue_id}|{issue_id}.*?({"|".join(self.TEAMS_OF_INTEREST)})'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return (match.group(1) or match.group(2)).upper()
        return "UNKNOWN"
    
    def _extract_priority_from_context(self, text: str, issue_id: str) -> str:
        """Extract priority from context"""
        # Look for priority indicators
        priorities = ["High", "Medium", "Low", "Block 1", "Block 2", "Critical"]
        for priority in priorities:
            if re.search(rf'{priority}.*?{issue_id}|{issue_id}.*?{priority}', text, re.IGNORECASE):
                return priority
        return "Medium"
    
    def _extract_status_from_context(self, text: str, issue_id: str) -> str:
        """Extract status from context"""
        statuses = [
            "In Implementation", "In Analysis", "In UAT Tests", 
            "Ready for UAT Tests", "Ready for Prod", "Ready for High Level Solution",
            "Backlog", "Done", "In Monitoring", "In Progress"
        ]
        for status in statuses:
            if re.search(rf'{issue_id}.*?{status}', text, re.IGNORECASE):
                return status
        return "Unknown"
    
    def _extract_sprint_from_context(self, text: str, issue_id: str) -> Optional[str]:
        """Extract sprint number from context"""
        match = re.search(rf'{issue_id}.*?\[SP-(\d+)\]', text, re.IGNORECASE)
        if match:
            return f"SP-{match.group(1)}"
        return None
    
    def _find_linked_initiative(self, text: str, beescad_id: str) -> Optional[str]:
        """Find the BEESIP initiative linked to a BEESCAD epic"""
        # Look for BEESIP near the BEESCAD
        match = re.search(rf'(BEESIP-\d+).*?{beescad_id}|{beescad_id}.*?(BEESIP-\d+)', text)
        if match:
            return match.group(1) or match.group(2)
        return None
    
    def _extract_field_near(self, text: str, issue_id: str, field: str) -> str:
        """Generic field extraction"""
        # This is a placeholder - real implementation would be more sophisticated
        return ""
    
    def filter_by_teams(self, data: Dict[str, Any], teams: List[str] = None) -> Dict[str, Any]:
        """Filter parsed data by teams of interest"""
        if teams is None:
            teams = self.TEAMS_OF_INTEREST
        
        teams_upper = [t.upper() for t in teams]
        
        filtered = {
            "sprints": data["sprints"],  # Sprints are shared
            "initiatives": [
                i for i in data["initiatives"] 
                if i["team"].upper() in teams_upper
            ],
            "epics": data["epics"],  # Keep all epics for now
            "risks": [
                r for r in data["risks"]
                if any(t in r.get("title", "").upper() for t in teams_upper)
            ],
            "bugs": [
                b for b in data["bugs"]
                if b["team"].upper() in teams_upper or any(t in b.get("title", "").upper() for t in teams_upper)
            ],
            "parsed_at": data["parsed_at"],
            "filtered_by": teams
        }
        
        return filtered


def fetch_and_parse() -> Dict[str, Any]:
    """Fetch page from Confluence and parse it"""
    client = ConfluenceClient()
    
    print("Fetching Situation Wall from Confluence...")
    page_data = client.get_situation_wall()
    
    print(f"Parsing page: {page_data['title']} (v{page_data['version']})")
    parser = SituationWallParser(page_data['html_content'])
    
    data = parser.parse_all()
    
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
    
    print("\n=== Initiatives by Team ===")
    teams = {}
    for init in data['initiatives']:
        team = init['team']
        if team not in teams:
            teams[team] = []
        teams[team].append(init['beesip_id'])
    
    for team, items in sorted(teams.items()):
        print(f"  {team}: {len(items)} - {', '.join(items[:3])}...")
    
    # Save to file for debugging
    with open("situation_wall_data.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    print("\n✓ Data saved to situation_wall_data.json")

"""
Calendar integration module - fetch events from multiple sources:
1. CALENDARIO.md (atualizado pela Nova) - PRINCIPAL
2. Google Calendar iCal (fallback)
"""
import os
import re
import requests
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
from pathlib import Path

try:
    from icalendar import Calendar
    ICAL_AVAILABLE = True
except ImportError:
    ICAL_AVAILABLE = False
    print("⚠️ icalendar not installed. iCal sync disabled.")

# Caminho do arquivo da Nova
CALENDARIO_MD_PATHS = [
    "/root/Nova/openclaw-workspace/CALENDARIO.md",
    "/root/.openclaw/workspace/CALENDARIO.md",
    os.path.expanduser("~/Documents/Nova/openclaw-workspace/CALENDARIO.md")
]


def get_calendario_md_path() -> Optional[str]:
    """Encontra o arquivo CALENDARIO.md da Nova"""
    for path in CALENDARIO_MD_PATHS:
        if os.path.exists(path):
            return path
    return None


def parse_calendario_md() -> List[Dict]:
    """
    Parseia o CALENDARIO.md da Nova e extrai eventos
    Formato esperado:
    | Hora | Evento | Local |
    | 09:30 | [Catalog] Daily Standup | Zoom |
    """
    path = get_calendario_md_path()
    if not path:
        return []
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        events = []
        current_date = None
        today = date.today()
        
        # Encontrar seções de dias (### Terça 3/fev, ### Quarta 4/fev, etc)
        day_pattern = r'###\s+(\w+)\s+(\d+)/(\w+)(?:\s+\(HOJE\))?'
        table_row_pattern = r'\|\s*(\d{2}:\d{2})\s*\|\s*([^|]+)\s*\|(?:\s*([^|]*)\s*\|)?'
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            # Detectar cabeçalho de dia
            day_match = re.match(day_pattern, line)
            if day_match:
                day_name, day_num, month_name = day_match.groups()
                
                # Converter mês
                months = {'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
                         'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12}
                month_num = months.get(month_name.lower(), today.month)
                
                try:
                    current_date = date(today.year, month_num, int(day_num))
                except ValueError:
                    current_date = None
                continue
            
            # Detectar linha de evento em tabela
            if current_date:
                row_match = re.match(table_row_pattern, line)
                if row_match:
                    time_str, title, location = row_match.groups()
                    title = title.strip()
                    location = location.strip() if location else ''
                    
                    # Limpar formatação markdown
                    title = re.sub(r'\*\*([^*]+)\*\*', r'\1', title)  # Remove **bold**
                    
                    events.append({
                        'title': title,
                        'date': current_date.isoformat(),
                        'time': time_str,
                        'location': location,
                        'source': 'calendario_md',
                        'datetime_sort': f"{current_date.isoformat()}T{time_str}"
                    })
        
        # Ordenar por datetime
        events.sort(key=lambda x: x['datetime_sort'])
        return events
        
    except Exception as e:
        print(f"Error parsing CALENDARIO.md: {e}")
        return []


def get_calendar_url() -> Optional[str]:
    """Get calendar URL from environment or openclaw config"""
    url = os.environ.get('GCAL_ICAL_URL')
    if not url:
        try:
            import json
            config_paths = [
                '/root/.openclaw/openclaw.json',
                os.path.expanduser('~/.openclaw/openclaw.json')
            ]
            for config_path in config_paths:
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        url = config.get('env', {}).get('GCAL_ICAL_URL') or config.get('GCAL_ICAL_URL')
                        if url:
                            break
        except Exception as e:
            print(f"Error reading config: {e}")
    return url


def fetch_calendar_events(days_ahead: int = 7) -> List[Dict]:
    """Fetch events from Google Calendar for the next N days"""
    if not ICAL_AVAILABLE:
        return []
    
    url = get_calendar_url()
    if not url:
        return []
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        cal = Calendar.from_ical(response.content)
        events = []
        
        now = datetime.now()
        end_date = now + timedelta(days=days_ahead)
        
        for component in cal.walk():
            if component.name == "VEVENT":
                dtstart = component.get('dtstart')
                if dtstart:
                    event_date = dtstart.dt
                    
                    # Handle date vs datetime
                    if hasattr(event_date, 'date'):
                        event_datetime = event_date
                        event_date_only = event_date.date()
                    else:
                        event_datetime = datetime.combine(event_date, datetime.min.time())
                        event_date_only = event_date
                    
                    # Check if event is within range
                    if now.date() <= event_date_only <= end_date.date():
                        summary = str(component.get('summary', 'Sem título'))
                        location = str(component.get('location', '')) if component.get('location') else ''
                        description = str(component.get('description', '')) if component.get('description') else ''
                        
                        # Format time
                        if hasattr(dtstart.dt, 'hour'):
                            event_time = dtstart.dt.strftime('%H:%M')
                        else:
                            event_time = 'Dia todo'
                        
                        events.append({
                            'title': summary,
                            'date': event_date_only.isoformat(),
                            'time': event_time,
                            'location': location,
                            'description': description,
                            'datetime_sort': event_datetime.isoformat() if hasattr(event_datetime, 'isoformat') else str(event_datetime)
                        })
        
        # Sort by datetime
        events.sort(key=lambda x: x['datetime_sort'])
        return events
        
    except Exception as e:
        print(f"Error fetching calendar: {e}")
        return []


def get_today_events() -> List[Dict]:
    """
    Get today's events - prioriza CALENDARIO.md da Nova
    """
    today = datetime.now().date().isoformat()
    
    # 1. Tentar CALENDARIO.md primeiro (fonte principal)
    calendario_events = parse_calendario_md()
    today_events = [e for e in calendario_events if e['date'] == today]
    
    if today_events:
        return today_events
    
    # 2. Fallback para iCal
    ical_events = fetch_calendar_events(days_ahead=1)
    return [e for e in ical_events if e['date'] == today]


def get_week_events() -> Dict[str, List[Dict]]:
    """
    Get this week's events grouped by day
    Prioriza CALENDARIO.md da Nova
    """
    # 1. Tentar CALENDARIO.md primeiro
    calendario_events = parse_calendario_md()
    
    if calendario_events:
        grouped = {}
        for event in calendario_events:
            event_date = event['date']
            if event_date not in grouped:
                grouped[event_date] = []
            grouped[event_date].append(event)
        return grouped
    
    # 2. Fallback para iCal
    ical_events = fetch_calendar_events(days_ahead=7)
    grouped = {}
    for event in ical_events:
        event_date = event['date']
        if event_date not in grouped:
            grouped[event_date] = []
        grouped[event_date].append(event)
    
    return grouped


def get_events_for_date(target_date: str) -> List[Dict]:
    """Get events for a specific date (YYYY-MM-DD format)"""
    # 1. Tentar CALENDARIO.md primeiro
    calendario_events = parse_calendario_md()
    date_events = [e for e in calendario_events if e['date'] == target_date]
    
    if date_events:
        return date_events
    
    # 2. Fallback para iCal
    all_events = fetch_calendar_events(days_ahead=14)
    return [e for e in all_events if e['date'] == target_date]


if __name__ == "__main__":
    # Test
    print("Testing calendar integration...")
    print(f"Calendar URL found: {bool(get_calendar_url())}")
    print(f"\nToday's events ({datetime.now().date()}):")
    for e in get_today_events():
        print(f"  {e['time']} - {e['title']}")
    
    print(f"\nWeek events:")
    for date, evts in sorted(get_week_events().items()):
        print(f"\n  {date}:")
        for e in evts:
            print(f"    {e['time']} - {e['title'][:50]}")

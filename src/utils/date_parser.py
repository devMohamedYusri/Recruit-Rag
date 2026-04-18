import re
from datetime import datetime
from typing import List, Optional

def parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse a variety of date strings like 'Jan 2020', '2020/01', 'March 2019', '10/2021', 'Present'.
    Returns None if unparseable.
    """
    if not date_str or not isinstance(date_str, str):
        return None
        
    date_str = date_str.lower().strip()
    
    if any(p in date_str for p in ['present', 'current', 'now', 'till now', 'until now']):
        return datetime.now()
        
    # Standardize months
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    # 1. Try MM/YYYY or MM-YYYY (common in resumes)
    match = re.search(r'\b(0?[1-9]|1[0-2])[-/](\d{4})\b', date_str)
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        return datetime(year, month, 1)

    # 2. Try YYYY-MM or YYYY/MM
    match = re.search(r'\b(\d{4})[-/](0?[1-9]|1[0-2])\b', date_str)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        return datetime(year, month, 1)

    # 3. Try DD/MM/YYYY
    match = re.search(r'\b(0?[1-9]|[12]\d|3[01])[-/](0?[1-9]|1[0-2])[-/](\d{4})\b', date_str)
    if match:
        year = int(match.group(3))
        month = int(match.group(2))
        return datetime(year, month, 1)

    # 4. Try Month YYYY or YYYY Month
    for month_name, month_val in months.items():
        if month_name in date_str:
            match = re.search(r'(\d{4})', date_str)
            if match:
                return datetime(int(match.group(1)), month_val, 1)
                
    # 5. Fallback to just Year (e.g. "2019")
    match = re.search(r'\b(\d{4})\b', date_str)
    if match:
        return datetime(int(match.group(1)), 1, 1)
        
    return None

def calculate_total_experience(work_history: List[dict]) -> float:
    """
    Calculate total years of experience from work history.
    Handles overlapping dates by summing simplified durations (naive).
    Returns years as float.
    """
    total_days = 0
    if not isinstance(work_history, list):
        return 0.0
        
    for job in work_history:
        if not isinstance(job, dict):
            continue
            
        dates = job.get('dates', '')
        if not dates or not isinstance(dates, str):
            continue
            
        parts = re.split(r'[-–—to]+', dates)
        if len(parts) >= 2:
            start_date = parse_date(parts[0])
            end_date = parse_date(parts[1])
        elif len(parts) == 1:
            start_date = parse_date(parts[0])
            end_date = start_date # Minimum 1 month if only one date
        else:
            continue
            
        if start_date and end_date:
            # Ensure end is after start
            if end_date < start_date:
                start_date, end_date = end_date, start_date
            
            diff = (end_date - start_date).days
            total_days += max(diff, 30) # Minimum 1 month impact if parsed
            
    return round(total_days / 365.25, 1)

def calculate_relevant_experience(work_history: List[dict], jd_domain_synonyms: List[str]) -> float:
    """
    Calculate relevant years of experience, filtered by domain match and weighted by recency.
    """
    if not isinstance(work_history, list):
        return 0.0
        
    from utils.domain_resolver import resolve_domain
    total_weighted_days = 0.0
    now = datetime.now()
    
    for job in work_history:
        if not isinstance(job, dict):
            continue
            
        job_domain = job.get('industry_domain', "Unknown")
        
        # 1. Filter: Must match JD domains - Fallback to True if no synonyms provided
        if jd_domain_synonyms and not resolve_domain(job_domain, jd_domain_synonyms):
            continue
            
        # 2. Extract Duration
        dates = job.get('dates', '')
        if not dates or not isinstance(dates, str):
            continue
            
        parts = re.split(r'[-–—to]+', dates)
        start_date, end_date = None, None
        if len(parts) >= 2:
            start_date = parse_date(parts[0])
            end_date = parse_date(parts[1])
        elif len(parts) == 1:
            start_date = parse_date(parts[0])
            end_date = start_date
            
        if start_date and end_date:
            if end_date < start_date:
                start_date, end_date = end_date, start_date
                
            diff_days = max((end_date - start_date).days, 30)
            
            # 3. Recency Weighting
            years_ago = (now - end_date).days / 365.25
            if years_ago < 2.0:
                weight = 1.0
            elif years_ago < 5.0:
                weight = 0.75
            else:
                weight = 0.50
                
            total_weighted_days += (diff_days * weight)
            
    return round(total_weighted_days / 365.25, 1)

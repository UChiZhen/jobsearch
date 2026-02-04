"""
Utility functions for Job Radar.
"""

import re
import hashlib
from typing import Optional


def generate_job_id(org_name: str, job_title: str, location: str,
                    requisition_id: Optional[str] = None) -> str:
    """
    Generate a stable job_id.
    
    Priority:
    1. Use requisition_id if available (from page)
    2. Otherwise generate from org + title + location (normalized)
    
    Args:
        org_name: Organization name
        job_title: Job title
        location: Location string (will be normalized)
        requisition_id: Optional requisition/job ID from the page
    
    Returns:
        Stable job_id string
    """
    if requisition_id:
        # Clean the requisition ID
        clean_req = normalize_text(requisition_id)
        org_prefix = normalize_text(org_name)[:30]
        return f"{org_prefix}_{clean_req}"
    
    # Generate from components
    org_part = normalize_text(org_name)
    title_part = normalize_text(job_title)
    location_part = normalize_location(location)
    
    return f"{org_part}_{title_part}_{location_part}"


def normalize_text(text: str) -> str:
    """
    Normalize text for ID generation.
    - Lowercase
    - Remove special characters
    - Replace spaces with underscores
    - Collapse multiple underscores
    """
    if not text:
        return "unknown"
    
    text = text.lower().strip()
    # Remove special characters except spaces and alphanumerics
    text = re.sub(r'[^\w\s]', '', text)
    # Replace spaces with underscores
    text = re.sub(r'\s+', '_', text)
    # Collapse multiple underscores
    text = re.sub(r'_+', '_', text)
    # Remove leading/trailing underscores
    text = text.strip('_')
    
    return text or "unknown"


def normalize_location(location: str) -> str:
    """
    Normalize location for stable ID generation.
    
    Priorities:
    1. Extract country if present
    2. Extract city if present
    3. Handle remote/hybrid
    
    Common mappings for stability:
    - "San Francisco" -> "san_francisco"
    - "SF" -> "san_francisco"
    - "NYC" -> "new_york"
    - "Remote" -> "remote"
    """
    if not location:
        return "location_unknown"
    
    location = location.lower().strip()
    
    # Common abbreviation mappings
    abbreviations = {
        "sf": "san_francisco",
        "nyc": "new_york",
        "ny": "new_york",
        "la": "los_angeles",
        "dc": "washington_dc",
        "chi": "chicago",
        "uk": "united_kingdom",
        "uae": "united_arab_emirates",
        "hk": "hong_kong",
        "sg": "singapore",
    }
    
    # Check for abbreviations
    for abbrev, full in abbreviations.items():
        if re.search(rf'\b{abbrev}\b', location):
            return full
    
    # Handle remote
    if "remote" in location:
        # Try to extract country
        countries = ["united states", "us", "usa", "canada", "uk", "united kingdom"]
        for country in countries:
            if country in location:
                return f"remote_{normalize_text(country)}"
        return "remote"
    
    # Standard normalization
    return normalize_text(location)[:50]  # Limit length


def compute_content_hash(text: str) -> str:
    """
    Compute MD5 hash of content for change detection.
    
    Args:
        text: Raw text content
    
    Returns:
        MD5 hex digest
    """
    if not text:
        return hashlib.md5(b"").hexdigest()
    
    # Normalize whitespace before hashing for stability
    normalized = re.sub(r'\s+', ' ', text.strip())
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()


def truncate_text(text: str, max_chars: int = 12000) -> str:
    """
    Truncate text to max characters while trying to preserve sentence boundaries.
    
    Args:
        text: Input text
        max_chars: Maximum characters (default 12k for ~3k tokens)
    
    Returns:
        Truncated text
    """
    if not text or len(text) <= max_chars:
        return text
    
    # Try to break at sentence boundary
    truncated = text[:max_chars]
    
    # Find last sentence ending
    last_period = truncated.rfind('. ')
    if last_period > max_chars * 0.8:  # Only if we're not losing too much
        truncated = truncated[:last_period + 1]
    
    return truncated + "\n\n[Content truncated...]"


def estimate_tokens(text: str, chars_per_token: float = 4.0) -> int:
    """
    Estimate token count from character count.
    
    Args:
        text: Input text
        chars_per_token: Average characters per token (default 4)
    
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    return int(len(text) / chars_per_token)


def format_datetime(dt_str: str) -> str:
    """Format datetime string for display."""
    if not dt_str:
        return "N/A"
    
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str

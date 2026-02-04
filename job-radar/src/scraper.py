"""
Web scraper for Job Radar.
Fetches career pages and extracts main text content.
Uses trafilatura for content extraction (no LLM).
"""

import requests
from typing import Optional, Tuple
from datetime import datetime

import trafilatura

from .config import get_config
from .utils import compute_content_hash, truncate_text


class Scraper:
    """Web scraper for career pages."""
    
    def __init__(self):
        config = get_config()
        self.timeout = config.scraper.timeout
        self.max_retries = config.scraper.max_retries
        self.user_agent = config.scraper.user_agent
        self.max_chars = config.gemini.max_input_chars
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
    
    def fetch_page(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetch a page and extract main text content.
        
        Args:
            url: URL to fetch
        
        Returns:
            Tuple of (raw_html, extracted_text) or (None, None) on error
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            raw_html = response.text
            
            # Extract main content using trafilatura
            extracted = trafilatura.extract(
                raw_html,
                include_links=True,
                include_tables=True,
                include_comments=False,
                output_format='txt'
            )
            
            return raw_html, extracted
            
        except requests.RequestException as e:
            print(f"❌ Error fetching {url}: {e}")
            return None, None
    
    def fetch_and_process(self, url: str) -> dict:
        """
        Fetch a page and return processed result with metadata.
        
        Returns:
            dict with keys:
            - success: bool
            - url: str
            - raw_text: str (truncated)
            - content_hash: str
            - char_count: int
            - token_estimate: int
            - fetched_at: str
            - error: Optional[str]
        """
        result = {
            "success": False,
            "url": url,
            "raw_text": None,
            "content_hash": None,
            "char_count": 0,
            "token_estimate": 0,
            "fetched_at": datetime.utcnow().isoformat(),
            "error": None,
        }
        
        raw_html, extracted_text = self.fetch_page(url)
        
        if extracted_text is None:
            result["error"] = "Failed to fetch or extract content"
            return result
        
        # Truncate to max chars
        truncated = truncate_text(extracted_text, self.max_chars)
        
        # Compute hash
        content_hash = compute_content_hash(truncated)
        
        result.update({
            "success": True,
            "raw_text": truncated,
            "content_hash": content_hash,
            "char_count": len(truncated),
            "token_estimate": len(truncated) // 4,
        })
        
        return result


# Module-level scraper instance
_scraper: Optional[Scraper] = None


def get_scraper() -> Scraper:
    """Get or create the singleton scraper instance."""
    global _scraper
    if _scraper is None:
        _scraper = Scraper()
    return _scraper

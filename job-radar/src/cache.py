"""
Cache manager for Job Radar.
Manages page content caching to avoid redundant LLM calls.
"""

from typing import Optional, Tuple

from .database import get_db
from .utils import compute_content_hash


class CacheManager:
    """Manages content caching for LLM call optimization."""
    
    def __init__(self):
        self.db = get_db()
    
    def check_cache(self, url: str, new_content: str) -> Tuple[bool, Optional[str]]:
        """
        Check if content has changed since last cache.
        
        Args:
            url: Page URL
            new_content: Newly fetched content
        
        Returns:
            Tuple of (needs_llm_call, cached_hash)
            - needs_llm_call: True if content changed or not cached
            - cached_hash: Previous hash if cached, None otherwise
        """
        new_hash = compute_content_hash(new_content)
        cached = self.db.get_cached_page(url)
        
        if cached is None:
            return True, None
        
        cached_hash = cached.get("content_hash")
        if cached_hash == new_hash:
            return False, cached_hash
        
        return True, cached_hash
    
    def update_cache(self, url: str, content: str):
        """
        Update cache with new content.
        
        Args:
            url: Page URL
            content: Content to cache
        """
        content_hash = compute_content_hash(content)
        self.db.cache_page(url, content_hash, content)
    
    def get_cached_content(self, url: str) -> Optional[str]:
        """
        Get cached content for a URL.
        
        Args:
            url: Page URL
        
        Returns:
            Cached content or None
        """
        cached = self.db.get_cached_page(url)
        if cached:
            return cached.get("raw_text")
        return None


# Singleton cache manager
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get or create the singleton cache manager."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

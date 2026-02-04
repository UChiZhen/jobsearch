"""
Gemini API wrapper for Job Radar.
Implements rate limiting, retry with exponential backoff, and usage logging.
"""

import time
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

import google.generativeai as genai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from .config import get_config
from .database import get_db


@dataclass
class RateLimitState:
    """Tracks rate limit state."""
    requests_this_minute: int = 0
    requests_today: int = 0
    minute_start: datetime = None
    day_start: datetime = None
    
    def __post_init__(self):
        now = datetime.utcnow()
        if self.minute_start is None:
            self.minute_start = now
        if self.day_start is None:
            self.day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)


class GeminiClient:
    """
    Gemini API client with rate limiting and retry logic.
    
    Features:
    - Rate limiting (RPM/RPD)
    - Exponential backoff on 429 errors
    - Usage logging to database
    - Dry-run mode support
    """
    
    def __init__(self, dry_run: bool = False):
        config = get_config()
        self.dry_run = dry_run
        self.model_name = config.gemini.model
        self.rpm_limit = config.gemini.rpm_limit
        self.rpd_limit = config.gemini.rpd_limit
        self.max_input_chars = config.gemini.max_input_chars
        self.chars_per_token = config.gemini.chars_per_token
        
        # Initialize Gemini
        if not dry_run:
            genai.configure(api_key=config.gemini.api_key)
            self.model = genai.GenerativeModel(self.model_name)
        else:
            self.model = None
        
        # Rate limiting state
        self._rate_state = RateLimitState()
        self._lock = Lock()
        
        # Database for logging
        self.db = get_db()
        
        # Stats for this session
        self.stats = {
            "calls_made": 0,
            "calls_skipped_cache": 0,
            "total_input_chars": 0,
            "total_output_chars": 0,
            "total_tokens_est": 0,
            "errors": 0,
        }
    
    def _check_rate_limits(self) -> bool:
        """Check if we're within rate limits. Returns True if OK to proceed."""
        with self._lock:
            now = datetime.utcnow()
            
            # Reset minute counter if needed
            if (now - self._rate_state.minute_start).total_seconds() >= 60:
                self._rate_state.requests_this_minute = 0
                self._rate_state.minute_start = now
            
            # Reset daily counter if needed (midnight UTC)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if self._rate_state.day_start < today_start:
                self._rate_state.requests_today = 0
                self._rate_state.day_start = today_start
            
            # Check limits
            if self._rate_state.requests_this_minute >= self.rpm_limit:
                return False
            if self._rate_state.requests_today >= self.rpd_limit:
                return False
            
            return True
    
    def _wait_for_rate_limit(self):
        """Wait until rate limits allow another request."""
        while not self._check_rate_limits():
            with self._lock:
                now = datetime.utcnow()
                # Calculate wait time until next minute
                seconds_until_minute = 60 - (now - self._rate_state.minute_start).total_seconds()
                wait_time = max(1, min(seconds_until_minute, 10))
            
            print(f"   ⏳ Rate limit reached, waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
    
    def _increment_counters(self):
        """Increment rate limit counters after a successful call."""
        with self._lock:
            self._rate_state.requests_this_minute += 1
            self._rate_state.requests_today += 1
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    def _call_api(self, prompt: str) -> str:
        """
        Make the actual API call with retry logic.
        
        Retries on:
        - 429 (rate limit)
        - 500/503 (server errors)
        """
        response = self.model.generate_content(prompt)
        
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            raise ValueError(f"Prompt blocked: {response.prompt_feedback.block_reason}")
        
        if not response.text:
            raise ValueError("Empty response from API")
        
        return response.text
    
    def generate(
        self,
        prompt: str,
        run_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate content using Gemini API.
        
        Args:
            prompt: The prompt to send
            run_id: Optional run ID for logging
            job_id: Optional job ID for logging
        
        Returns:
            Dict with:
            - success: bool
            - text: str (response text)
            - input_chars: int
            - output_chars: int
            - tokens_est: int
            - latency_ms: int
            - error: Optional[str]
        """
        input_chars = len(prompt)
        
        result = {
            "success": False,
            "text": None,
            "input_chars": input_chars,
            "output_chars": 0,
            "tokens_est": input_chars // 4,
            "latency_ms": 0,
            "error": None,
        }
        
        # Dry-run mode: don't call API
        if self.dry_run:
            result["success"] = True
            result["text"] = "[DRY-RUN: API not called]"
            self.stats["calls_skipped_cache"] += 1
            return result
        
        # Wait for rate limits
        self._wait_for_rate_limit()
        
        # Make the call
        start_time = time.time()
        try:
            response_text = self._call_api(prompt)
            latency_ms = int((time.time() - start_time) * 1000)
            
            output_chars = len(response_text)
            tokens_est = (input_chars + output_chars) // 4
            
            result.update({
                "success": True,
                "text": response_text,
                "output_chars": output_chars,
                "tokens_est": tokens_est,
                "latency_ms": latency_ms,
            })
            
            # Update counters
            self._increment_counters()
            self.stats["calls_made"] += 1
            self.stats["total_input_chars"] += input_chars
            self.stats["total_output_chars"] += output_chars
            self.stats["total_tokens_est"] += tokens_est
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            result["latency_ms"] = latency_ms
            result["error"] = str(e)
            self.stats["errors"] += 1
        
        # Log to database
        if run_id:
            self.db.log_usage(
                run_id=run_id,
                job_id=job_id,
                model=self.model_name,
                input_chars=result["input_chars"],
                output_chars=result["output_chars"],
                latency_ms=result["latency_ms"],
                success=result["success"],
                error=result["error"],
            )
        
        return result
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return len(text) // int(self.chars_per_token)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        return {
            **self.stats,
            "requests_this_minute": self._rate_state.requests_this_minute,
            "requests_today": self._rate_state.requests_today,
        }


# Singleton client
_gemini_client: Optional[GeminiClient] = None


def get_gemini_client(dry_run: bool = False) -> GeminiClient:
    """Get or create the Gemini client."""
    global _gemini_client
    if _gemini_client is None or _gemini_client.dry_run != dry_run:
        _gemini_client = GeminiClient(dry_run=dry_run)
    return _gemini_client

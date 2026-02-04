"""
Configuration management for Job Radar.
Loads environment variables and user profile.
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv


# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class GeminiConfig:
    """Gemini API configuration with rate limits."""
    api_key: str
    model: str = "gemini-3-flash-preview"  # Latest flash model
    rpm_limit: int = 360  # Requests per minute (Premium tier)
    rpd_limit: int = 10000  # Requests per day
    tpm_limit: int = 4_000_000  # Tokens per minute
    max_input_chars: int = 12000  # Truncate input to avoid token explosion
    chars_per_token: float = 4.0  # Approximation for estimation


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "job_radar.db")


@dataclass
class ScraperConfig:
    """Web scraper configuration."""
    timeout: int = 30  # seconds
    max_retries: int = 3
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


@dataclass
class Config:
    """Main configuration container."""
    gemini: GeminiConfig
    database: DatabaseConfig
    scraper: ScraperConfig
    user_profile: dict
    project_root: Path = PROJECT_ROOT
    
    @classmethod
    def load(cls) -> "Config":
        """Load configuration from environment and files."""
        # Gemini API key is required
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment. Please set it in .env file.")
        
        # Load user profile
        profile_path = PROJECT_ROOT / "config" / "user_profile.yaml"
        if profile_path.exists():
            with open(profile_path, "r") as f:
                user_profile = yaml.safe_load(f)
        else:
            user_profile = {}
        
        # Database path from env or default
        db_path_str = os.getenv("DATABASE_PATH")
        if db_path_str:
            db_path = PROJECT_ROOT / db_path_str
        else:
            db_path = PROJECT_ROOT / "data" / "job_radar.db"
        
        return cls(
            gemini=GeminiConfig(api_key=api_key),
            database=DatabaseConfig(path=db_path),
            scraper=ScraperConfig(),
            user_profile=user_profile,
        )


# Singleton config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the singleton config instance."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config

"""
Database operations for Job Radar.
Handles SQLite connections and CRUD operations.
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from datetime import datetime
import uuid

from .config import get_config


# SQL Schema
SCHEMA = """
-- organizations: 组织种子表
CREATE TABLE IF NOT EXISTS organizations (
    org_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    career_url TEXT,
    location TEXT,
    industry TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- job_postings: 岗位事实表
CREATE TABLE IF NOT EXISTS job_postings (
    job_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    source TEXT NOT NULL,
    job_title TEXT,
    location TEXT,
    country TEXT,
    city TEXT,
    job_url TEXT,
    post_date TEXT,
    fit_score INTEGER,
    recommended_action TEXT,
    top_reasons TEXT,
    risks TEXT,
    resume_angle TEXT,
    keywords TEXT,
    content_hash TEXT,
    raw_text TEXT,
    status TEXT DEFAULT 'new',
    next_step_date TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES organizations(org_id)
);

-- push_log: 运行账本
CREATE TABLE IF NOT EXISTS push_log (
    run_id TEXT PRIMARY KEY,
    run_datetime TEXT NOT NULL,
    run_mode TEXT NOT NULL,
    source TEXT,
    orgs_scanned INTEGER DEFAULT 0,
    urls_scanned INTEGER DEFAULT 0,
    jobs_new INTEGER DEFAULT 0,
    jobs_updated INTEGER DEFAULT 0,
    jobs_unchanged INTEGER DEFAULT 0,
    apply_now_count INTEGER DEFAULT 0,
    save_for_weekly_count INTEGER DEFAULT 0,
    archive_count INTEGER DEFAULT 0,
    llm_calls INTEGER DEFAULT 0,
    llm_tokens_est INTEGER DEFAULT 0,
    email_sent INTEGER DEFAULT 0,
    email_error TEXT,
    duration_seconds REAL,
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- run_job_changes: bridge 表
CREATE TABLE IF NOT EXISTS run_job_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    recommended_action TEXT,
    content_hash TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES push_log(run_id),
    FOREIGN KEY (job_id) REFERENCES job_postings(job_id)
);

-- usage_log: LLM 调用日志
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    job_id TEXT,
    model TEXT,
    input_chars INTEGER,
    output_chars INTEGER,
    tokens_est INTEGER,
    latency_ms INTEGER,
    success INTEGER,
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- page_cache: 正文缓存
CREATE TABLE IF NOT EXISTS page_cache (
    url TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    raw_text TEXT,
    fetched_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_job_postings_org ON job_postings(org_id);
CREATE INDEX IF NOT EXISTS idx_job_postings_status ON job_postings(status);
CREATE INDEX IF NOT EXISTS idx_job_postings_hash ON job_postings(content_hash);
CREATE INDEX IF NOT EXISTS idx_run_job_changes_run ON run_job_changes(run_id);
CREATE INDEX IF NOT EXISTS idx_usage_log_run ON usage_log(run_id);
CREATE INDEX IF NOT EXISTS idx_page_cache_hash ON page_cache(content_hash);
"""


class Database:
    """SQLite database wrapper with context manager support."""
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = get_config().database.path
        self.db_path = db_path
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def init_schema(self):
        """Initialize database schema."""
        with self.connection() as conn:
            conn.executescript(SCHEMA)
        print(f"✅ Database initialized at {self.db_path}")
    
    def get_tables(self) -> List[str]:
        """Get list of all tables."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            return [row[0] for row in cursor.fetchall()]
    
    # ==================== Organizations ====================
    
    def upsert_organization(self, org: Dict[str, Any]) -> str:
        """Insert or update an organization. Returns org_id."""
        org_id = org.get("org_id") or self._generate_org_id(org["name"])
        
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO organizations (org_id, name, career_url, location, industry, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(org_id) DO UPDATE SET
                    name = excluded.name,
                    career_url = excluded.career_url,
                    location = excluded.location,
                    industry = excluded.industry
            """, (
                org_id,
                org["name"],
                org.get("career_url"),
                org.get("location"),
                org.get("industry"),
                org.get("is_active", 1),
            ))
        return org_id
    
    def get_active_organizations(self, limit: Optional[int] = None) -> List[Dict]:
        """Get all active organizations."""
        with self.connection() as conn:
            query = "SELECT * FROM organizations WHERE is_active = 1"
            if limit:
                query += f" LIMIT {limit}"
            cursor = conn.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    
    def _generate_org_id(self, name: str) -> str:
        """Generate a stable org_id from name."""
        import re
        # Lowercase, remove special chars, replace spaces with underscores
        org_id = name.lower()
        org_id = re.sub(r'[^\w\s]', '', org_id)
        org_id = re.sub(r'\s+', '_', org_id.strip())
        return org_id
    
    # ==================== Job Postings ====================
    
    def get_job_by_id(self, job_id: str) -> Optional[Dict]:
        """Get a job posting by ID."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM job_postings WHERE job_id = ?", (job_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_job_by_content_hash(self, content_hash: str) -> Optional[Dict]:
        """Get a job posting by content hash."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM job_postings WHERE content_hash = ?", (content_hash,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def upsert_job(self, job: Dict[str, Any]) -> tuple[str, str]:
        """
        Insert or update a job posting.
        Returns (job_id, change_type) where change_type is 'new', 'updated', or 'unchanged'.
        """
        job_id = job["job_id"]
        now = datetime.utcnow().isoformat()
        
        existing = self.get_job_by_id(job_id)
        
        if existing is None:
            # New job
            change_type = "new"
            with self.connection() as conn:
                conn.execute("""
                    INSERT INTO job_postings (
                        job_id, org_id, source, job_title, location, country, city,
                        job_url, post_date, fit_score, recommended_action,
                        top_reasons, risks, resume_angle, keywords,
                        content_hash, raw_text, status, first_seen_at, last_seen_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id, job.get("org_id"), job.get("source", "career_site"),
                    job.get("job_title"), job.get("location"), job.get("country"), job.get("city"),
                    job.get("job_url"), job.get("post_date"), job.get("fit_score"),
                    job.get("recommended_action"), job.get("top_reasons"), job.get("risks"),
                    job.get("resume_angle"), job.get("keywords"), job.get("content_hash"),
                    job.get("raw_text"), "new", now, now, now, now
                ))
        else:
            # Check if content changed
            if existing.get("content_hash") == job.get("content_hash"):
                change_type = "unchanged"
                # Just update last_seen_at
                with self.connection() as conn:
                    conn.execute(
                        "UPDATE job_postings SET last_seen_at = ? WHERE job_id = ?",
                        (now, job_id)
                    )
            else:
                change_type = "updated"
                with self.connection() as conn:
                    conn.execute("""
                        UPDATE job_postings SET
                            job_title = ?, location = ?, country = ?, city = ?,
                            post_date = ?, fit_score = ?, recommended_action = ?,
                            top_reasons = ?, risks = ?, resume_angle = ?, keywords = ?,
                            content_hash = ?, raw_text = ?, last_seen_at = ?, updated_at = ?
                        WHERE job_id = ?
                    """, (
                        job.get("job_title"), job.get("location"), job.get("country"), job.get("city"),
                        job.get("post_date"), job.get("fit_score"), job.get("recommended_action"),
                        job.get("top_reasons"), job.get("risks"), job.get("resume_angle"),
                        job.get("keywords"), job.get("content_hash"), job.get("raw_text"),
                        now, now, job_id
                    ))
        
        return job_id, change_type
    
    # ==================== Push Log ====================
    
    def create_run(self, run_mode: str = "real", source: str = "career_site") -> str:
        """Create a new run entry. Returns run_id."""
        run_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO push_log (run_id, run_datetime, run_mode, source)
                VALUES (?, ?, ?, ?)
            """, (run_id, now, run_mode, source))
        
        return run_id
    
    def update_run(self, run_id: str, stats: Dict[str, Any]):
        """Update run statistics."""
        set_clauses = ", ".join(f"{k} = ?" for k in stats.keys())
        values = list(stats.values()) + [run_id]
        
        with self.connection() as conn:
            conn.execute(
                f"UPDATE push_log SET {set_clauses} WHERE run_id = ?",
                values
            )
    
    def get_run(self, run_id: str) -> Optional[Dict]:
        """Get a run by ID."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM push_log WHERE run_id = ?", (run_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ==================== Run Job Changes (Bridge) ====================
    
    def add_run_job_change(self, run_id: str, job_id: str, change_type: str,
                           recommended_action: Optional[str] = None,
                           content_hash: Optional[str] = None):
        """Record a job change for a run."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO run_job_changes (run_id, job_id, change_type, recommended_action, content_hash)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, job_id, change_type, recommended_action, content_hash))
    
    def get_run_job_changes(self, run_id: str) -> List[Dict]:
        """Get all job changes for a run."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM run_job_changes WHERE run_id = ?", (run_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def aggregate_run_stats(self, run_id: str) -> Dict[str, int]:
        """Aggregate stats from run_job_changes for verification."""
        with self.connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    SUM(CASE WHEN change_type = 'new' THEN 1 ELSE 0 END) as jobs_new,
                    SUM(CASE WHEN change_type = 'updated' THEN 1 ELSE 0 END) as jobs_updated,
                    SUM(CASE WHEN change_type = 'unchanged' THEN 1 ELSE 0 END) as jobs_unchanged,
                    SUM(CASE WHEN recommended_action = 'apply_now' THEN 1 ELSE 0 END) as apply_now_count,
                    SUM(CASE WHEN recommended_action = 'save_for_weekly' THEN 1 ELSE 0 END) as save_for_weekly_count,
                    SUM(CASE WHEN recommended_action = 'archive' THEN 1 ELSE 0 END) as archive_count
                FROM run_job_changes WHERE run_id = ?
            """, (run_id,))
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    # ==================== Usage Log ====================
    
    def log_usage(self, run_id: str, job_id: Optional[str], model: str,
                  input_chars: int, output_chars: int, latency_ms: int,
                  success: bool, error: Optional[str] = None):
        """Log an LLM API call."""
        tokens_est = (input_chars + output_chars) // 4
        
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO usage_log (run_id, job_id, model, input_chars, output_chars,
                                       tokens_est, latency_ms, success, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, job_id, model, input_chars, output_chars, tokens_est,
                  latency_ms, 1 if success else 0, error))
    
    # ==================== Page Cache ====================
    
    def get_cached_page(self, url: str) -> Optional[Dict]:
        """Get cached page content."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM page_cache WHERE url = ?", (url,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def cache_page(self, url: str, content_hash: str, raw_text: str):
        """Cache a page."""
        now = datetime.utcnow().isoformat()
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO page_cache (url, content_hash, raw_text, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    raw_text = excluded.raw_text,
                    fetched_at = excluded.fetched_at
            """, (url, content_hash, raw_text, now))
    
    def is_content_changed(self, url: str, new_hash: str) -> bool:
        """Check if page content has changed since last cache."""
        cached = self.get_cached_page(url)
        if cached is None:
            return True
        return cached.get("content_hash") != new_hash


# Singleton database instance
_db: Optional[Database] = None


def get_db() -> Database:
    """Get or create the singleton database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db

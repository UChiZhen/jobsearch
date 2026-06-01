"""
Job extraction and scoring for Job Radar.
Uses Gemini API to extract structured job data and compute fit scores.
"""

import json
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from .llm import get_gemini_client
from .config import get_config
from .utils import generate_job_id, truncate_text


# Extraction prompt template
EXTRACTION_PROMPT = """You are a job posting analyzer. Extract structured information from the career page content below.

USER PROFILE:
- Education: {education}
- Skills: {skills}
- Target Geography: {geography}
- Target Org Types: {org_types}
- Preferred Levels: {job_levels}
- Excluded Keywords (seniority): {excluded_keywords}

ORGANIZATION: {org_name}
CAREER PAGE URL: {career_url}

PAGE CONTENT:
---
{page_content}
---

INSTRUCTIONS:
1. Extract ALL job postings visible on this page
2. For each job, provide the structured data below
3. If no jobs found, return an empty jobs array
4. Be conservative with fit scores - only score high if there's a genuine match

OUTPUT FORMAT (JSON):
{{
  "jobs": [
    {{
      "requisition_id": "string or null - job/requisition ID from page if present",
      "job_title": "string - exact job title",
      "location": "string - full location text",
      "country": "string - standardized country name",
      "city": "string - city name or 'Remote'",
      "post_date": "string - YYYY-MM-DD format or null if not found",
      "job_url": "string - direct URL to job posting if available, else null",
      "fit_score": 0-100,
      "recommended_action": "apply_now | save_for_weekly | archive",
      "top_reasons": "string - 2-3 bullet points why this job matches or doesn't match",
      "risks": "string - potential concerns or mismatches",
      "resume_angle": "string - how to tailor resume for this role",
      "keywords": "string - comma-separated relevant keywords for tracking"
    }}
  ],
  "page_summary": "string - brief summary of what this careers page contains"
}}

SCORING GUIDELINES:
- 85-100: Strong match - right level, geography, org type, relevant skills. Action: apply_now
- 70-84: Good match - most criteria met, minor gaps. Action: save_for_weekly
- 50-69: Partial match - some relevant aspects but significant gaps. Action: save_for_weekly
- 0-49: Poor match - wrong level (senior/VP), wrong geography, irrelevant role. Action: archive

IMPORTANT:
- If job title contains excluded keywords (senior, director, VP, manager, lead, principal, partner), set fit_score < 50 and recommended_action = archive
- Fellowship/internship positions should be scored based on timeline alignment with 2026 graduation
- Always extract the actual job URL if visible, otherwise use null

Respond ONLY with valid JSON, no markdown formatting."""


@dataclass
class ExtractedJob:
    """Represents an extracted job posting."""
    job_id: str
    org_id: str
    source: str
    job_title: str
    location: str
    country: str
    city: str
    job_url: Optional[str]
    post_date: Optional[str]
    fit_score: int
    recommended_action: str
    top_reasons: str
    risks: str
    resume_angle: str
    keywords: str
    content_hash: str
    raw_text: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "org_id": self.org_id,
            "source": self.source,
            "job_title": self.job_title,
            "location": self.location,
            "country": self.country,
            "city": self.city,
            "job_url": self.job_url,
            "post_date": self.post_date,
            "fit_score": self.fit_score,
            "recommended_action": self.recommended_action,
            "top_reasons": self.top_reasons,
            "risks": self.risks,
            "resume_angle": self.resume_angle,
            "keywords": self.keywords,
            "content_hash": self.content_hash,
            "raw_text": self.raw_text,
        }


class JobExtractor:
    """Extracts and scores job postings from career pages."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.llm = get_gemini_client(dry_run=dry_run)
        self.config = get_config()
        self.user_profile = self.config.user_profile
    
    def _build_prompt(self, org_name: str, career_url: str, page_content: str) -> str:
        """Build the extraction prompt with user profile context."""
        profile = self.user_profile
        
        # Extract user profile fields with defaults
        background = profile.get("background", {})
        positioning = profile.get("positioning", {})
        geography = profile.get("geography", {})
        org_types = profile.get("organization_types", [])
        job_prefs = profile.get("job_preferences", {})
        excluded = profile.get("excluded_keywords", [])
        
        return EXTRACTION_PROMPT.format(
            education=f"{background.get('degree', 'MPP')} from {background.get('school', 'University of Chicago')}, graduating {background.get('graduation_date', '2026-06')}",
            skills=", ".join(background.get("skills", ["data analysis", "impact measurement"])),
            geography=", ".join(geography.get("preferred", ["United States"])),
            org_types=", ".join(org_types[:10]),  # Limit to 10 for prompt length
            job_levels=", ".join(job_prefs.get("level", ["entry-level", "analyst"])),
            excluded_keywords=", ".join(excluded),
            org_name=org_name,
            career_url=career_url,
            page_content=truncate_text(page_content, self.config.gemini.max_input_chars),
        )
    
    def _ensure_string(self, value) -> str:
        """Convert value to string, handling lists from LLM responses."""
        if value is None:
            return ""
        if isinstance(value, list):
            return "; ".join(str(item) for item in value)
        return str(value)
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM response JSON."""
        # Try to extract JSON from response
        try:
            # Handle potential markdown code blocks
            if "```json" in response_text:
                match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)
            elif "```" in response_text:
                match = re.search(r'```\s*(.*?)\s*```', response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)
            
            return json.loads(response_text.strip())
        except json.JSONDecodeError as e:
            print(f"   ⚠️ Failed to parse JSON: {e}")
            return {"jobs": [], "page_summary": "Failed to parse response", "error": str(e)}
    
    def extract_jobs(
        self,
        org_id: str,
        org_name: str,
        career_url: str,
        page_content: str,
        content_hash: str,
        run_id: Optional[str] = None,
    ) -> List[ExtractedJob]:
        """
        Extract jobs from a career page.
        
        Args:
            org_id: Organization ID
            org_name: Organization name
            career_url: Career page URL
            page_content: Page text content
            content_hash: Content hash for caching
            run_id: Optional run ID for logging
        
        Returns:
            List of ExtractedJob objects
        """
        # Build prompt
        prompt = self._build_prompt(org_name, career_url, page_content)
        
        # Dry-run: return placeholder
        if self.dry_run:
            print(f"   🔍 [DRY-RUN] Would extract jobs from {len(page_content)} chars")
            return []
        
        # Call LLM
        result = self.llm.generate(prompt, run_id=run_id)
        
        if not result["success"]:
            print(f"   ❌ LLM error: {result['error']}")
            return []
        
        # Parse response
        parsed = self._parse_response(result["text"])
        jobs_data = parsed.get("jobs", [])
        
        if not jobs_data:
            print(f"   📭 No jobs found on page")
            return []
        
        # Convert to ExtractedJob objects
        extracted_jobs = []
        for job_data in jobs_data:
            try:
                # Generate stable job_id
                job_id = generate_job_id(
                    org_name=org_name,
                    job_title=job_data.get("job_title", "Unknown"),
                    location=job_data.get("location", "Unknown"),
                    requisition_id=job_data.get("requisition_id"),
                )
                
                job = ExtractedJob(
                    job_id=job_id,
                    org_id=org_id,
                    source="career_site",
                    job_title=job_data.get("job_title", "Unknown Title"),
                    location=job_data.get("location", ""),
                    country=job_data.get("country", ""),
                    city=job_data.get("city", ""),
                    job_url=job_data.get("job_url") or career_url,
                    post_date=job_data.get("post_date"),
                    fit_score=int(job_data.get("fit_score", 0)),
                    recommended_action=job_data.get("recommended_action", "archive"),
                    top_reasons=self._ensure_string(job_data.get("top_reasons", "")),
                    risks=self._ensure_string(job_data.get("risks", "")),
                    resume_angle=self._ensure_string(job_data.get("resume_angle", "")),
                    keywords=self._ensure_string(job_data.get("keywords", "")),
                    content_hash=content_hash,
                    raw_text=truncate_text(page_content, 5000),  # Store truncated version
                )
                extracted_jobs.append(job)
                
            except Exception as e:
                print(f"   ⚠️ Error processing job: {e}")
                continue
        
        print(f"   ✓ Extracted {len(extracted_jobs)} jobs")
        return extracted_jobs


# Singleton extractor
_extractor: Optional[JobExtractor] = None


def get_job_extractor(dry_run: bool = False) -> JobExtractor:
    """Get or create the job extractor."""
    global _extractor
    if _extractor is None or _extractor.dry_run != dry_run:
        _extractor = JobExtractor(dry_run=dry_run)
    return _extractor

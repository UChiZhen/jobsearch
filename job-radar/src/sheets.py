"""
Google Sheets integration for Job Radar.
Handles reading Organizations and writing Job Results.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import get_config


# Google Sheets API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
]


class SheetsClient:
    """Google Sheets client for reading/writing job radar data."""
    
    def __init__(self, spreadsheet_id: Optional[str] = None):
        config = get_config()
        self.config_dir = config.project_root / "config"
        self.credentials_path = self.config_dir / "credentials.json"
        self.token_path = self.config_dir / "token.json"
        self.spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEET_ID")
        self._service = None
    
    def _get_credentials(self) -> Credentials:
        """Get or refresh OAuth credentials."""
        creds = None
        
        # Load existing token
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        
        # Refresh or create new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Credentials not found at {self.credentials_path}"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save token
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
        
        return creds
    
    def authenticate(self) -> bool:
        """Authenticate with Google Sheets API."""
        try:
            creds = self._get_credentials()
            self._service = build('sheets', 'v4', credentials=creds)
            print("✅ Google Sheets API authenticated")
            return True
        except Exception as e:
            print(f"❌ Sheets authentication failed: {e}")
            return False
    
    def _ensure_authenticated(self):
        """Ensure we have an authenticated service."""
        if not self._service:
            if not self.authenticate():
                raise RuntimeError("Failed to authenticate with Google Sheets")
    
    # ==================== Read Operations ====================
    
    def read_organizations(self, sheet_name: str = "Organizations") -> List[Dict]:
        """
        Read organizations from the Google Sheet.
        
        Expected columns: Organizations, Website, Locations, Relevant Industry
        
        Returns:
            List of organization dicts
        """
        self._ensure_authenticated()
        
        try:
            result = self._service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A:J"  # Read columns A-J
            ).execute()
            
            values = result.get('values', [])
            if not values:
                print(f"   ⚠️ No data found in {sheet_name}")
                return []
            
            # First row is header
            headers = values[0]
            orgs = []
            
            for row in values[1:]:
                # Pad row to match headers length
                row = row + [''] * (len(headers) - len(row))
                
                org = dict(zip(headers, row))
                
                # Map to our schema
                mapped = {
                    "name": org.get("Organizations", ""),
                    "career_url": org.get("Website", ""),
                    "location": org.get("Locations", ""),
                    "industry": org.get("Relevant Industry", ""),
                }
                
                # Only include if has name and career URL
                if mapped["name"] and mapped["career_url"]:
                    orgs.append(mapped)
            
            print(f"   ✓ Read {len(orgs)} organizations from Sheets")
            return orgs
            
        except HttpError as e:
            print(f"   ❌ Error reading sheet: {e}")
            return []
    
    # ==================== Write Operations ====================
    
    def write_job_results(
        self,
        jobs: List[Dict],
        sheet_name: str = "Job Results",
        clear_first: bool = False
    ) -> bool:
        """
        Write job results to the Google Sheet.
        
        Args:
            jobs: List of job dicts to write
            sheet_name: Target sheet name
            clear_first: Whether to clear existing data first
        
        Returns:
            True if successful
        """
        self._ensure_authenticated()
        
        if not jobs:
            print("   ⚠️ No jobs to write")
            return True
        
        try:
            # Ensure sheet exists
            self._ensure_sheet_exists(sheet_name)
            
            # Clear if requested
            if clear_first:
                self._service.spreadsheets().values().clear(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!A:Z"
                ).execute()
            
            # Prepare data
            headers = [
                "Job ID", "Organization", "Job Title", "Location",
                "Fit Score", "Recommended Action", "Top Reasons",
                "Risks", "Resume Angle", "Job URL", "Extracted At"
            ]
            
            rows = [headers]
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            for job in jobs:
                rows.append([
                    job.get("job_id", ""),
                    job.get("org_name", job.get("org_id", "")),
                    job.get("job_title", ""),
                    job.get("location", ""),
                    str(job.get("fit_score", 0)),
                    job.get("recommended_action", ""),
                    job.get("top_reasons", "")[:500],  # Limit length
                    job.get("risks", "")[:300],
                    job.get("resume_angle", "")[:300],
                    job.get("job_url", ""),
                    now,
                ])
            
            # Write data
            body = {'values': rows}
            self._service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption='RAW',
                body=body
            ).execute()
            
            print(f"   ✓ Wrote {len(jobs)} jobs to {sheet_name}")
            return True
            
        except HttpError as e:
            print(f"   ❌ Error writing to sheet: {e}")
            return False
    
    def append_job_results(
        self,
        jobs: List[Dict],
        sheet_name: str = "Job Results"
    ) -> bool:
        """
        Append new job results to the Google Sheet (without clearing).
        
        Args:
            jobs: List of job dicts to append
            sheet_name: Target sheet name
        
        Returns:
            True if successful
        """
        self._ensure_authenticated()
        
        if not jobs:
            return True
        
        try:
            # Ensure sheet exists
            self._ensure_sheet_exists(sheet_name)
            
            # Prepare data (no headers for append)
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            rows = []
            
            for job in jobs:
                rows.append([
                    job.get("job_id", ""),
                    job.get("org_name", job.get("org_id", "")),
                    job.get("job_title", ""),
                    job.get("location", ""),
                    str(job.get("fit_score", 0)),
                    job.get("recommended_action", ""),
                    job.get("top_reasons", "")[:500],
                    job.get("risks", "")[:300],
                    job.get("resume_angle", "")[:300],
                    job.get("job_url", ""),
                    now,
                ])
            
            # Append data
            body = {'values': rows}
            self._service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A:K",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            print(f"   ✓ Appended {len(jobs)} jobs to {sheet_name}")
            return True
            
        except HttpError as e:
            print(f"   ❌ Error appending to sheet: {e}")
            return False
    
    def _ensure_sheet_exists(self, sheet_name: str):
        """Ensure a sheet tab exists, create if not."""
        try:
            # Get existing sheets
            spreadsheet = self._service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            existing_sheets = [s['properties']['title'] for s in spreadsheet.get('sheets', [])]
            
            if sheet_name not in existing_sheets:
                # Create the sheet
                request = {
                    'addSheet': {
                        'properties': {'title': sheet_name}
                    }
                }
                self._service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={'requests': [request]}
                ).execute()
                print(f"   ✓ Created sheet tab: {sheet_name}")
                
        except HttpError as e:
            # Sheet might already exist, ignore
            pass
    
    def get_spreadsheet_url(self) -> str:
        """Get the URL of the spreadsheet."""
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"


# Singleton client
_sheets_client: Optional[SheetsClient] = None


def get_sheets_client(spreadsheet_id: Optional[str] = None) -> SheetsClient:
    """Get or create the Sheets client."""
    global _sheets_client
    if _sheets_client is None:
        _sheets_client = SheetsClient(spreadsheet_id)
    return _sheets_client

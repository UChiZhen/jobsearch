"""
Gmail API integration for Job Radar.
Handles OAuth authentication and email sending.
"""

import os
import base64
from pathlib import Path
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import get_config


# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',  # For reading user profile
]


class GmailClient:
    """Gmail API client for sending job radar reports."""
    
    def __init__(self):
        config = get_config()
        self.config_dir = config.project_root / "config"
        self.credentials_path = self.config_dir / "credentials.json"
        self.token_path = self.config_dir / "token.json"
        self._service = None
        self._user_email = None
    
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
                        f"Gmail credentials not found at {self.credentials_path}. "
                        "Please download from Google Cloud Console."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save token for next run
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
        
        return creds
    
    def authenticate(self) -> bool:
        """
        Authenticate with Gmail API.
        Will open browser for OAuth flow on first run.
        
        Returns:
            True if authentication successful
        """
        try:
            creds = self._get_credentials()
            self._service = build('gmail', 'v1', credentials=creds)
            
            # Get user email
            profile = self._service.users().getProfile(userId='me').execute()
            self._user_email = profile.get('emailAddress')
            
            print(f"✅ Gmail authenticated as: {self._user_email}")
            return True
            
        except Exception as e:
            print(f"❌ Gmail authentication failed: {e}")
            return False
    
    @property
    def user_email(self) -> Optional[str]:
        """Get authenticated user's email."""
        return self._user_email
    
    def send_email(self, to: str, subject: str, body_html: str, 
                   body_text: Optional[str] = None) -> dict:
        """
        Send an email via Gmail API.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body_html: HTML body content
            body_text: Optional plain text body (fallback)
        
        Returns:
            dict with 'success' and 'message_id' or 'error'
        """
        if not self._service:
            if not self.authenticate():
                return {"success": False, "error": "Authentication failed"}
        
        try:
            # Create message
            message = MIMEMultipart('alternative')
            message['to'] = to
            message['from'] = self._user_email
            message['subject'] = subject
            
            # Add plain text part
            if body_text:
                part1 = MIMEText(body_text, 'plain')
                message.attach(part1)
            
            # Add HTML part
            part2 = MIMEText(body_html, 'html')
            message.attach(part2)
            
            # Encode and send
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            body = {'raw': raw}
            
            sent_message = self._service.users().messages().send(
                userId='me', body=body
            ).execute()
            
            return {
                "success": True,
                "message_id": sent_message['id'],
                "thread_id": sent_message.get('threadId')
            }
            
        except HttpError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def send_job_radar_report(self, jobs_data: dict) -> dict:
        """
        Send the weekly job radar report.
        
        Args:
            jobs_data: Dict with job information including:
                - new_jobs: list of new jobs
                - apply_now: list of jobs to apply immediately
                - save_for_weekly: list of jobs to review
                - run_stats: run statistics
        
        Returns:
            Send result dict
        """
        subject = self._build_subject(jobs_data)
        body_html = self._build_html_report(jobs_data)
        body_text = self._build_text_report(jobs_data)
        
        return self.send_email(
            to=self._user_email,  # Send to self
            subject=subject,
            body_html=body_html,
            body_text=body_text
        )
    
    def _build_subject(self, jobs_data: dict) -> str:
        """Build email subject line."""
        apply_now = len(jobs_data.get('apply_now', []))
        new_jobs = len(jobs_data.get('new_jobs', []))
        
        if apply_now > 0:
            return f"🚨 Job Radar: {apply_now} jobs to apply NOW + {new_jobs} new"
        elif new_jobs > 0:
            return f"📋 Job Radar: {new_jobs} new jobs this week"
        else:
            return "📊 Job Radar: Weekly scan complete (no new jobs)"
    
    def _build_html_report(self, jobs_data: dict) -> str:
        """Build HTML email body."""
        apply_now = jobs_data.get('apply_now', [])
        save_for_weekly = jobs_data.get('save_for_weekly', [])
        stats = jobs_data.get('run_stats', {})
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                          color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
                .section { background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
                .job-card { background: white; padding: 15px; border-radius: 8px; 
                            margin-bottom: 10px; border-left: 4px solid #667eea; }
                .job-card.urgent { border-left-color: #e74c3c; }
                .score { display: inline-block; padding: 2px 8px; border-radius: 12px; 
                         font-size: 12px; font-weight: bold; }
                .score-high { background: #d4edda; color: #155724; }
                .score-medium { background: #fff3cd; color: #856404; }
                .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
                .stat-box { background: white; padding: 15px; border-radius: 8px; text-align: center; }
                .stat-number { font-size: 24px; font-weight: bold; color: #667eea; }
                a { color: #667eea; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin:0;">🎯 Impact Finance Job Radar</h1>
                    <p style="margin:10px 0 0;">Weekly Report</p>
                </div>
        """
        
        # Stats section
        html += f"""
                <div class="section">
                    <h2>📊 This Week's Scan</h2>
                    <div class="stats">
                        <div class="stat-box">
                            <div class="stat-number">{stats.get('orgs_scanned', 0)}</div>
                            <div>Organizations</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">{stats.get('jobs_new', 0)}</div>
                            <div>New Jobs</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">{len(apply_now)}</div>
                            <div>Apply Now!</div>
                        </div>
                    </div>
                </div>
        """
        
        # Apply Now section
        if apply_now:
            html += """
                <div class="section">
                    <h2>🚨 Apply Now (High Priority)</h2>
            """
            for job in apply_now:
                html += self._job_card_html(job, urgent=True)
            html += "</div>"
        
        # Save for Weekly section
        if save_for_weekly:
            html += """
                <div class="section">
                    <h2>📋 Worth Reviewing</h2>
            """
            for job in save_for_weekly:
                html += self._job_card_html(job, urgent=False)
            html += "</div>"
        
        html += """
            </div>
        </body>
        </html>
        """
        return html
    
    def _job_card_html(self, job: dict, urgent: bool = False) -> str:
        """Build HTML for a single job card."""
        urgent_class = "urgent" if urgent else ""
        score = job.get('fit_score', 0)
        score_class = "score-high" if score >= 80 else "score-medium"
        
        return f"""
            <div class="job-card {urgent_class}">
                <h3 style="margin:0 0 5px;">{job.get('job_title', 'Unknown Title')}</h3>
                <p style="margin:0 0 5px; color: #666;">
                    {job.get('org_name', '')} • {job.get('location', '')}
                </p>
                <span class="score {score_class}">Fit: {score}%</span>
                <p style="margin:10px 0 5px; font-size: 14px;">{job.get('top_reasons', '')[:200]}</p>
                <a href="{job.get('job_url', '#')}" target="_blank">View Job →</a>
            </div>
        """
    
    def _build_text_report(self, jobs_data: dict) -> str:
        """Build plain text email body."""
        apply_now = jobs_data.get('apply_now', [])
        save_for_weekly = jobs_data.get('save_for_weekly', [])
        stats = jobs_data.get('run_stats', {})
        
        lines = [
            "=== Impact Finance Job Radar ===",
            "",
            f"Organizations scanned: {stats.get('orgs_scanned', 0)}",
            f"New jobs found: {stats.get('jobs_new', 0)}",
            f"Apply now: {len(apply_now)}",
            "",
        ]
        
        if apply_now:
            lines.append("--- APPLY NOW ---")
            for job in apply_now:
                lines.append(f"• {job.get('job_title')} @ {job.get('org_name')}")
                lines.append(f"  Location: {job.get('location')}")
                lines.append(f"  Fit Score: {job.get('fit_score')}%")
                lines.append(f"  URL: {job.get('job_url')}")
                lines.append("")
        
        if save_for_weekly:
            lines.append("--- WORTH REVIEWING ---")
            for job in save_for_weekly:
                lines.append(f"• {job.get('job_title')} @ {job.get('org_name')}")
                lines.append(f"  Fit Score: {job.get('fit_score')}%")
                lines.append(f"  URL: {job.get('job_url')}")
                lines.append("")
        
        return "\n".join(lines)


# Singleton client
_gmail_client: Optional[GmailClient] = None


def get_gmail_client() -> GmailClient:
    """Get or create the singleton Gmail client."""
    global _gmail_client
    if _gmail_client is None:
        _gmail_client = GmailClient()
    return _gmail_client

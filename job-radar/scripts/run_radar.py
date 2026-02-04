#!/usr/bin/env python3
"""
Main entry point for Job Radar.
Runs the job scanning pipeline with LLM extraction and Google Sheets integration.
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.database import get_db
from src.scraper import get_scraper
from src.cache import get_cache_manager
from src.job_extractor import get_job_extractor
from src.sheets import get_sheets_client
from src.emailer import get_gmail_client
from src.utils import estimate_tokens


console = Console()


class JobRadar:
    """Main job radar pipeline."""
    
    def __init__(self, dry_run: bool = False, use_sheets: bool = True, send_email: bool = False):
        self.dry_run = dry_run
        self.use_sheets = use_sheets
        self.send_email = send_email
        self.db = get_db()
        self.scraper = get_scraper()
        self.cache = get_cache_manager()
        self.extractor = get_job_extractor(dry_run=dry_run)
        
        # Sheets client (optional)
        self.sheets = None
        if use_sheets:
            try:
                self.sheets = get_sheets_client()
                self.sheets.authenticate()
            except Exception as e:
                console.print(f"[yellow]⚠️ Sheets not available: {e}[/yellow]")
                self.sheets = None
        
        # Stats for this run
        self.stats = {
            "orgs_scanned": 0,
            "urls_scanned": 0,
            "urls_success": 0,
            "urls_failed": 0,
            "pages_changed": 0,
            "pages_unchanged": 0,
            "llm_calls_needed": 0,
            "estimated_tokens": 0,
            "actual_llm_calls": 0,
            "jobs_new": 0,
            "jobs_updated": 0,
            "jobs_unchanged": 0,
            "apply_now_count": 0,
            "save_for_weekly_count": 0,
            "archive_count": 0,
        }
        
        self.run_id = None
        self.new_jobs = []  # Track new jobs for Sheets export
    
    def run(self, limit: int = None, source: str = "career_site"):
        """Run the job radar pipeline."""
        start_time = time.time()
        run_mode = "dry_run" if self.dry_run else "real"
        
        # Create run record
        self.run_id = self.db.create_run(run_mode=run_mode, source=source)
        console.print(f"\n🚀 [bold]Job Radar Run[/bold] - {self.run_id[:8]}...")
        console.print(f"   Mode: {'🔍 Dry-Run' if self.dry_run else '⚡ Real'}") 
        console.print(f"   Source: {'📊 Google Sheets' if self.sheets else '💾 Local DB'}")
        console.print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Get organizations - prefer Sheets if available
        if self.sheets:
            orgs = self._get_orgs_from_sheets(limit)
        else:
            orgs = self.db.get_active_organizations(limit=limit)
        
        console.print(f"\n📋 Organizations to scan: {len(orgs)}")
        
        # Process each organization
        for org in orgs:
            self._process_organization(org)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Aggregate stats from bridge table for verification
        if not self.dry_run:
            agg_stats = self.db.aggregate_run_stats(self.run_id)
            # Verify our counts match - handle None values from SQL
            if agg_stats:
                for key, val in agg_stats.items():
                    if val is not None:
                        self.stats[key] = val
        
        # Update run stats
        self.db.update_run(self.run_id, {
            "orgs_scanned": self.stats["orgs_scanned"],
            "urls_scanned": self.stats["urls_scanned"],
            "jobs_new": self.stats["jobs_new"],
            "jobs_updated": self.stats["jobs_updated"],
            "jobs_unchanged": self.stats["jobs_unchanged"],
            "apply_now_count": self.stats["apply_now_count"],
            "save_for_weekly_count": self.stats["save_for_weekly_count"],
            "archive_count": self.stats["archive_count"],
            "llm_calls": self.stats["actual_llm_calls"],
            "llm_tokens_est": self.stats["estimated_tokens"],
            "duration_seconds": duration,
        })
        
        # Export new jobs to Sheets
        if self.sheets and self.new_jobs and not self.dry_run:
            console.print("\n📤 Exporting to Google Sheets...")
            self.sheets.append_job_results(self.new_jobs)
            console.print(f"   ✓ View at: {self.sheets.get_spreadsheet_url()}")
        
        # Send email report
        if self.send_email and not self.dry_run:
            self._send_email_report()
        
        # Print summary
        self._print_summary(duration)
        
        return self.run_id
    
    def _send_email_report(self):
        """Send email report with job results."""
        console.print("\n📧 Sending email report...")
        
        try:
            gmail = get_gmail_client()
            if not gmail.authenticate():
                console.print("   ❌ Gmail authentication failed")
                return
            
            # Categorize jobs
            apply_now = [j for j in self.new_jobs if j.get('recommended_action') == 'apply_now']
            save_for_weekly = [j for j in self.new_jobs if j.get('recommended_action') == 'save_for_weekly']
            
            jobs_data = {
                'new_jobs': self.new_jobs,
                'apply_now': apply_now,
                'save_for_weekly': save_for_weekly,
                'run_stats': self.stats,
            }
            
            result = gmail.send_job_radar_report(jobs_data)
            
            if result.get('success'):
                console.print(f"   ✓ Email sent! Message ID: {result.get('message_id')}")
            else:
                console.print(f"   ❌ Failed to send: {result.get('error')}")
                
        except Exception as e:
            console.print(f"   ❌ Email error: {e}")
    
    def _get_orgs_from_sheets(self, limit: int = None):
        """Get organizations from Google Sheets."""
        orgs = self.sheets.read_organizations()
        
        # Convert to expected format with org_id
        result = []
        for i, org in enumerate(orgs):
            org_id = f"sheets_{i}_{org['name'][:20].lower().replace(' ', '_')}"
            result.append({
                "org_id": org_id,
                "name": org["name"],
                "career_url": org["career_url"],
                "location": org.get("location", ""),
                "industry": org.get("industry", ""),
            })
        
        if limit:
            result = result[:limit]
        
        return result
    
    def _process_organization(self, org: dict):
        """Process a single organization."""
        org_id = org.get("org_id", org.get("name", "unknown"))
        org_name = org["name"]
        career_url = org.get("career_url")
        
        if not career_url:
            console.print(f"   ⚠️  {org_name}: No career URL")
            return
        
        self.stats["orgs_scanned"] += 1
        console.print(f"\n🏢 [bold]{org_name}[/bold]")
        console.print(f"   URL: {career_url[:60]}...")
        
        # Fetch page
        self.stats["urls_scanned"] += 1
        result = self.scraper.fetch_and_process(career_url)
        
        if not result["success"]:
            self.stats["urls_failed"] += 1
            console.print(f"   ❌ Failed: {result['error']}")
            return
        
        self.stats["urls_success"] += 1
        console.print(f"   ✓ Fetched: {result['char_count']:,} chars (~{result['token_estimate']:,} tokens)")
        
        # Check cache
        needs_llm, cached_hash = self.cache.check_cache(career_url, result["raw_text"])
        
        if needs_llm:
            self.stats["pages_changed"] += 1
            self.stats["llm_calls_needed"] += 1
            self.stats["estimated_tokens"] += result["token_estimate"]
            
            if self.dry_run:
                console.print(f"   📝 Content changed - LLM call would be needed")
            else:
                console.print(f"   📝 Content changed - extracting jobs...")
                self.stats["actual_llm_calls"] += 1
                
                # Extract jobs using LLM
                jobs = self.extractor.extract_jobs(
                    org_id=org_id,
                    org_name=org_name,
                    career_url=career_url,
                    page_content=result["raw_text"],
                    content_hash=result["content_hash"],
                    run_id=self.run_id,
                )
                
                # Process extracted jobs
                for job in jobs:
                    self._process_job(job, org_name)
            
            # Update cache after processing
            self.cache.update_cache(career_url, result["raw_text"])
        else:
            self.stats["pages_unchanged"] += 1
            console.print(f"   ⏭️  Content unchanged - skipping LLM")
    
    def _process_job(self, job, org_name: str):
        """Process a single extracted job - upsert and record change."""
        job_dict = job.to_dict()
        
        # Upsert to database
        job_id, change_type = self.db.upsert_job(job_dict)
        
        # Record in bridge table
        self.db.add_run_job_change(
            run_id=self.run_id,
            job_id=job_id,
            change_type=change_type,
            recommended_action=job.recommended_action,
            content_hash=job.content_hash,
        )
        
        # Update local stats
        if change_type == "new":
            self.stats["jobs_new"] += 1
            action_icon = "🆕"
            # Track for Sheets export
            self.new_jobs.append({
                **job_dict,
                "org_name": org_name,
            })
        elif change_type == "updated":
            self.stats["jobs_updated"] += 1
            action_icon = "🔄"
        else:
            self.stats["jobs_unchanged"] += 1
            action_icon = "➖"
        
        # Track by recommended action
        if job.recommended_action == "apply_now":
            self.stats["apply_now_count"] += 1
            action_label = "[bold green]APPLY NOW[/bold green]"
        elif job.recommended_action == "save_for_weekly":
            self.stats["save_for_weekly_count"] += 1
            action_label = "[yellow]Save for review[/yellow]"
        else:
            self.stats["archive_count"] += 1
            action_label = "[dim]Archive[/dim]"
        
        console.print(f"      {action_icon} {job.job_title} | Fit: {job.fit_score}% | {action_label}")
    
    def _print_summary(self, duration: float):
        """Print run summary."""
        console.print("\n")
        
        # Create summary table
        table = Table(title="📊 Run Summary", show_header=False, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Run ID", self.run_id[:8] + "...")
        table.add_row("Duration", f"{duration:.1f}s")
        table.add_row("Data Source", "Google Sheets" if self.sheets else "Local DB")
        table.add_row("─" * 20, "─" * 10)
        table.add_row("Organizations scanned", str(self.stats["orgs_scanned"]))
        table.add_row("URLs fetched", str(self.stats["urls_scanned"]))
        table.add_row("  ✓ Successful", str(self.stats["urls_success"]))
        table.add_row("  ✗ Failed", str(self.stats["urls_failed"]))
        table.add_row("─" * 20, "─" * 10)
        table.add_row("Pages with changes", str(self.stats["pages_changed"]))
        table.add_row("Pages unchanged", str(self.stats["pages_unchanged"]))
        table.add_row("─" * 20, "─" * 10)
        
        if self.dry_run:
            table.add_row("[bold]LLM calls needed[/bold]", str(self.stats["llm_calls_needed"]))
            table.add_row("[bold]Est. tokens[/bold]", f"{self.stats['estimated_tokens']:,}")
            table.add_row("Actual LLM calls", "0 (dry-run)")
        else:
            table.add_row("LLM calls made", str(self.stats["actual_llm_calls"]))
            table.add_row("Tokens used (est.)", f"{self.stats['estimated_tokens']:,}")
            table.add_row("─" * 20, "─" * 10)
            table.add_row("[bold]Jobs - New[/bold]", str(self.stats["jobs_new"]))
            table.add_row("[bold]Jobs - Updated[/bold]", str(self.stats["jobs_updated"]))
            table.add_row("Jobs - Unchanged", str(self.stats["jobs_unchanged"]))
            table.add_row("─" * 20, "─" * 10)
            table.add_row("[bold green]🚨 Apply Now[/bold green]", str(self.stats["apply_now_count"]))
            table.add_row("[yellow]📋 Save for Review[/yellow]", str(self.stats["save_for_weekly_count"]))
            table.add_row("[dim]📦 Archive[/dim]", str(self.stats["archive_count"]))
        
        console.print(table)
        
        if self.dry_run:
            console.print(Panel(
                "[yellow]🔍 Dry-run complete. No LLM calls were made.[/yellow]\n"
                "Run without --dry-run to execute real LLM calls.",
                title="Dry-Run Mode"
            ))
        elif self.stats["apply_now_count"] > 0:
            console.print(Panel(
                f"[bold green]🎯 {self.stats['apply_now_count']} jobs recommended for immediate action![/bold green]\n"
                "Run with --send-email to push results to Gmail.",
                title="Action Required"
            ))


def main():
    parser = argparse.ArgumentParser(
        description="Impact Finance Job Radar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_radar.py --dry-run --limit 5    # Test with 5 orgs, no LLM
  python run_radar.py --limit 5              # Real run with 5 orgs
  python run_radar.py --no-sheets            # Use local DB instead of Sheets
  python run_radar.py                        # Full scan of all orgs
        """
    )
    
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Dry-run mode: fetch pages and estimate LLM calls without making them"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of organizations to scan"
    )
    parser.add_argument(
        "--source",
        default="career_site",
        choices=["career_site", "job_board"],
        help="Source type to scan"
    )
    parser.add_argument(
        "--no-sheets",
        action="store_true",
        help="Don't use Google Sheets, use local DB only"
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send email report after scan"
    )
    
    args = parser.parse_args()
    
    try:
        radar = JobRadar(
            dry_run=args.dry_run, 
            use_sheets=not args.no_sheets,
            send_email=args.send_email
        )
        radar.run(limit=args.limit, source=args.source)
    except ValueError as e:
        console.print(f"[red]❌ Configuration error: {e}[/red]")
        console.print("Please check your .env file and ensure GEMINI_API_KEY is set.")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        raise


if __name__ == "__main__":
    main()

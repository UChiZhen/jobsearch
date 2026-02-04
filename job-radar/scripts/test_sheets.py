#!/usr/bin/env python3
"""
Test Google Sheets integration.
First run will open browser for OAuth authorization if token needs additional scopes.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sheets import get_sheets_client


def main():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    
    if not sheet_id:
        print("❌ GOOGLE_SHEET_ID not found in .env")
        print()
        print("请按以下步骤操作:")
        print("1. 创建一个新的 Google Sheet")
        print("2. 复制 Sheet ID (URL 中 /d/ 和 /edit 之间的部分)")
        print("3. 在 .env 文件中添加: GOOGLE_SHEET_ID=你的ID")
        return
    
    print("🔐 Testing Google Sheets API...")
    print(f"   Sheet ID: {sheet_id[:20]}...")
    print()
    
    client = get_sheets_client(sheet_id)
    
    if not client.authenticate():
        print("❌ Authentication failed")
        return
    
    print()
    print("📖 Testing read from Organizations sheet...")
    orgs = client.read_organizations()
    
    if orgs:
        print(f"   Found {len(orgs)} organizations")
        print("   First 3:")
        for org in orgs[:3]:
            print(f"      - {org['name']}: {org.get('career_url', 'N/A')[:50]}...")
    else:
        print("   ⚠️ No organizations found. Make sure your sheet has an 'Organizations' tab")
        print("   with columns: Organizations, Website, Locations, Relevant Industry")
    
    print()
    print("📝 Testing write to Job Results sheet...")
    test_jobs = [
        {
            "job_id": "test_job_1",
            "org_name": "Test Organization",
            "job_title": "Test Analyst",
            "location": "Chicago, IL",
            "fit_score": 85,
            "recommended_action": "apply_now",
            "top_reasons": "Great match for skills",
            "risks": "None identified",
            "resume_angle": "Highlight data skills",
            "job_url": "https://example.com/job",
        }
    ]
    
    if client.write_job_results(test_jobs, sheet_name="Job Results", clear_first=True):
        print("   ✅ Write successful!")
        print(f"   View at: {client.get_spreadsheet_url()}")
    else:
        print("   ❌ Write failed")
    
    print()
    print("🎉 Google Sheets integration test complete!")


if __name__ == "__main__":
    main()

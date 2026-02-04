#!/usr/bin/env python3
"""
Seed organizations from the Excel file.
Imports Organizations sheet into the database.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from src.database import get_db


# Path to the Excel file
EXCEL_PATH = Path(__file__).parent.parent.parent / "Daily_Task.xlsx"


def load_organizations(limit: int = None) -> pd.DataFrame:
    """Load organizations from Excel."""
    df = pd.read_excel(EXCEL_PATH, sheet_name="Organizations")
    
    # Rename columns to match our schema
    df = df.rename(columns={
        "Organizations": "name",
        "Website": "career_url",
        "Locations": "location",
        "Relevant Industry": "industry"
    })
    
    # Filter to only rows with a career URL
    df = df[df["career_url"].notna() & (df["career_url"] != "")]
    
    if limit:
        df = df.head(limit)
    
    return df


def seed_organizations(limit: int = None, dry_run: bool = False):
    """Seed organizations into the database."""
    print(f"📂 Loading organizations from {EXCEL_PATH}")
    
    df = load_organizations(limit)
    print(f"   Found {len(df)} organizations with career URLs")
    
    if dry_run:
        print("\n🔍 Dry-run mode - showing first 5 organizations:")
        for _, row in df.head(5).iterrows():
            print(f"   - {row['name']}: {row['career_url']}")
        return
    
    db = get_db()
    inserted = 0
    
    for _, row in df.iterrows():
        org = {
            "name": row["name"],
            "career_url": row["career_url"],
            "location": row.get("location"),
            "industry": row.get("industry"),
            "is_active": 1
        }
        
        org_id = db.upsert_organization(org)
        inserted += 1
        print(f"   ✓ {org['name']} -> {org_id}")
    
    print(f"\n✅ Seeded {inserted} organizations")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Seed organizations from Excel")
    parser.add_argument("--limit", type=int, help="Limit number of organizations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported")
    
    args = parser.parse_args()
    
    seed_organizations(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

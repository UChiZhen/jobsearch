#!/usr/bin/env python3
"""
Initialize the Job Radar database.
Creates all tables and indexes.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Database


def main():
    print("🚀 Initializing Job Radar database...")
    
    db = Database()
    db.init_schema()
    
    # Verify tables were created
    tables = db.get_tables()
    print(f"\n📋 Tables created: {len(tables)}")
    for table in tables:
        print(f"   - {table}")
    
    print("\n✅ Database initialization complete!")


if __name__ == "__main__":
    main()

"""
Migrate data from SQLite to PostgreSQL
Run this AFTER setting up PostgreSQL in Railway
"""
import sqlite3
from sqlalchemy import create_engine, MetaData, Table, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

def migrate():
    # Get database URLs
    sqlite_url = "sqlite:///./notifli.db"
    postgres_url = os.getenv("DATABASE_URL")
    
    if not postgres_url or "sqlite" in postgres_url:
        print("Error: DATABASE_URL must be set to a PostgreSQL URL")
        print("Set it in Railway Variables or export it:")
        print("  export DATABASE_URL='postgres://...'")
        return
    
    print(f"Source (SQLite): {sqlite_url}")
    print(f"Target (PostgreSQL): {postgres_url[:50]}...")
    
    # Connect to both databases
    sqlite_engine = create_engine(sqlite_url)
    postgres_engine = create_engine(postgres_url)
    
    # Export SQLite data
    print("\n📤 Exporting data from SQLite...")
    sqlite_conn = sqlite3.connect("notifli.db")
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    tables = ['Business', 'Client', 'Appointment', 'ReminderSettings', 'SMSLog']
    data = {}
    
    for table in tables:
        try:
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if rows else []
            data[table] = {"columns": columns, "rows": [dict(row) for row in rows]}
            print(f"  ✓ {table}: {len(rows)} rows")
        except Exception as e:
            print(f"  ✗ {table}: {e}")
    
    sqlite_conn.close()
    
    # Import to PostgreSQL
    print("\n📥 Importing data to PostgreSQL...")
    PostgresSession = sessionmaker(bind=postgres_engine)
    postgres_session = PostgresSession()
    
    for table_name, table_data in data.items():
        if not table_data["rows"]:
            print(f"  ⏭️  {table_name}: No data to import")
            continue
        
        columns = table_data["columns"]
        rows = table_data["rows"]
        
        try:
            # Build insert query
            cols = ", ".join(columns)
            placeholders = ", ".join([f":{col}" for col in columns])
            query = text(f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})")
            
            for row in rows:
                # Convert None to null, handle any type conversions
                clean_row = {k: (None if v == "" else v) for k, v in row.items()}
                postgres_session.execute(query, clean_row)
            
            postgres_session.commit()
            print(f"  ✓ {table_name}: Imported {len(rows)} rows")
            
        except Exception as e:
            print(f"  ✗ {table_name}: {e}")
            postgres_session.rollback()
    
    postgres_session.close()
    print("\n✅ Migration complete!")
    print("\n⚠️  Next steps:")
    print("  1. Verify data in Railway PostgreSQL")
    print("  2. Update DATABASE_URL in Railway Variables")
    print("  3. Redeploy Railway")
    print("  4. Test the app thoroughly")

if __name__ == "__main__":
    migrate()

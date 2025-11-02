"""
Script to fix database permissions for TruthScope backend.
Run this to grant necessary permissions to the appuser.
"""

import os
import sys
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector
import pg8000

# Load environment variables
load_dotenv()

# Database configuration
CLOUD_SQL_CONNECTION_NAME = os.getenv("CLOUD_SQL_CONNECTION_NAME")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def get_db_connection():
    """Get a connection to Cloud SQL."""
    connector = Connector()
    conn = connector.connect(
        CLOUD_SQL_CONNECTION_NAME,
        "pg8000",
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME
    )
    return conn, connector

def fix_permissions():
    """Fix database permissions."""
    print("=" * 60)
    print("TruthScope Database Permission Fix")
    print("=" * 60)
    
    conn = None
    connector = None
    cursor = None
    
    try:
        print("\n1. Connecting to Cloud SQL...")
        conn, connector = get_db_connection()
        cursor = conn.cursor()
        print("✅ Connected successfully!")
        
        print("\n2. Granting permissions to appuser...")
        
        # Grant table permissions
        tables = ['url_verdicts', 'analysis_results', 'users']
        for table in tables:
            try:
                cursor.execute(f"GRANT ALL PRIVILEGES ON TABLE {table} TO appuser;")
                print(f"   ✅ Granted permissions on {table}")
            except Exception as e:
                print(f"   ⚠️  {table}: {str(e)}")
        
        # Grant sequence permissions
        try:
            cursor.execute("GRANT USAGE, SELECT ON SEQUENCE users_id_seq TO appuser;")
            print("   ✅ Granted permissions on users_id_seq sequence")
        except Exception as e:
            print(f"   ⚠️  Sequence: {str(e)}")
        
        # Grant schema permissions
        try:
            cursor.execute("GRANT ALL PRIVILEGES ON SCHEMA public TO appuser;")
            print("   ✅ Granted permissions on public schema")
        except Exception as e:
            print(f"   ⚠️  Schema: {str(e)}")
        
        # Grant default privileges
        try:
            cursor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO appuser;")
            cursor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO appuser;")
            print("   ✅ Set default privileges for future objects")
        except Exception as e:
            print(f"   ⚠️  Default privileges: {str(e)}")
        
        # Commit changes
        conn.commit()
        print("\n3. Committing changes...")
        print("✅ All changes committed successfully!")
        
        # Verify permissions
        print("\n4. Verifying permissions...")
        cursor.execute("""
            SELECT 
                table_name, 
                privilege_type 
            FROM 
                information_schema.role_table_grants 
            WHERE 
                grantee = 'appuser'
            ORDER BY 
                table_name, 
                privilege_type;
        """)
        
        results = cursor.fetchall()
        if results:
            print("\n   Current permissions for 'appuser':")
            current_table = None
            for table_name, privilege in results:
                if table_name != current_table:
                    print(f"\n   📋 {table_name}:")
                    current_table = table_name
                print(f"      • {privilege}")
        else:
            print("   ⚠️  No permissions found (this might be okay if using a superuser)")
        
        print("\n" + "=" * 60)
        print("✅ Permission fix completed successfully!")
        print("=" * 60)
        print("\nYou can now restart your backend server.")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"\nDetails: {str(e)}")
        sys.exit(1)
    
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass
        if connector:
            try:
                connector.close()
            except:
                pass

if __name__ == "__main__":
    print("\n⚠️  IMPORTANT: Make sure you have the correct database credentials!")
    print(f"   User: {DB_USER}")
    print(f"   Database: {DB_NAME}")
    print(f"   Connection: {CLOUD_SQL_CONNECTION_NAME}")
    
    response = input("\n   Continue? (yes/no): ")
    if response.lower() in ['yes', 'y']:
        fix_permissions()
    else:
        print("Aborted.")

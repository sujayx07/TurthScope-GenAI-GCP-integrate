# Fix Database Permissions - Manual Steps

## Problem
The `appuser` doesn't have permissions to access the `users` table (and possibly other tables).

## Solution
You need to run SQL commands as a database administrator/owner to grant permissions.

---

## Option 1: Use Google Cloud Console (Easiest)

### Step 1: Open Cloud SQL Instance
1. Go to: https://console.cloud.google.com/sql/instances/truthscope-db/overview?project=truthscope-prod-2025
2. Click on your Cloud SQL instance: `truthscope-db`

### Step 2: Open Cloud Shell
1. Click the **"Cloud Shell"** icon (>_) in the top-right corner
2. Wait for Cloud Shell to start

### Step 3: Connect to Database
Run this command (replace with your actual instance connection name):
```bash
gcloud sql connect truthscope-db --user=postgres --database=news_analysis_db --project=truthscope-prod-2025
```

Enter the **postgres** password when prompted (this is the admin password you set when creating the instance).

### Step 4: Run Permission Fix Commands
Once connected to the database, run these SQL commands:

```sql
-- Grant permissions on all tables
GRANT ALL PRIVILEGES ON TABLE url_verdicts TO appuser;
GRANT ALL PRIVILEGES ON TABLE analysis_results TO appuser;
GRANT ALL PRIVILEGES ON TABLE users TO appuser;

-- Grant sequence permissions (for auto-increment)
GRANT USAGE, SELECT ON SEQUENCE users_id_seq TO appuser;

-- Grant schema permissions
GRANT ALL PRIVILEGES ON SCHEMA public TO appuser;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO appuser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO appuser;

-- Verify permissions
SELECT 
    table_name, 
    privilege_type 
FROM 
    information_schema.role_table_grants 
WHERE 
    grantee = 'appuser' 
    AND table_schema = 'public'
ORDER BY 
    table_name, 
    privilege_type;
```

### Step 5: Exit
Type `\q` to exit psql.

---

## Option 2: Use pgAdmin or Another SQL Client

If you have pgAdmin or another PostgreSQL client:

1. **Connect to your Cloud SQL instance** using:
   - Host: Your Cloud SQL instance IP (get from console)
   - Port: 5432
   - Database: news_analysis_db
   - User: **postgres** (admin user, NOT appuser)
   - Password: Your postgres admin password

2. **Run the SQL commands** from Step 4 above

---

## Option 3: Temporary Workaround - Use Postgres User in App

If you can't fix permissions right now, you can temporarily use the postgres user in your app:

### Edit your `.env` file:
```properties
DB_USER=postgres
DB_PASSWORD=YourPostgresAdminPassword
```

**⚠️ WARNING**: This is NOT recommended for production! Only use this for testing.

---

## Verify Permissions After Fix

After running the permission commands, test your extension again. The error should be gone!

To verify permissions were granted, you can run:
```sql
\dp users
```

You should see `appuser` with permissions listed.

---

## Why This Happened

When tables are created by one user (e.g., `postgres`), other users (e.g., `appuser`) don't automatically get permissions on those tables. You need to explicitly grant permissions.

The fix commands above ensure:
1. `appuser` can read/write to all tables
2. `appuser` can use sequences (for auto-increment IDs)
3. Future tables will also grant permissions to `appuser`

---

## Next Steps

1. Fix permissions using one of the options above
2. Restart your backend: `python check_text.py`
3. Test the extension again

The "permission denied" error should be resolved! ✅

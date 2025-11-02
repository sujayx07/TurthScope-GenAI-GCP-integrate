-- Fix Permissions for TruthScope Database
-- Run this script to grant necessary permissions to the appuser

-- Connect to the database first:
-- \c news_analysis_db

-- Grant permissions to appuser for all tables
GRANT ALL PRIVILEGES ON TABLE url_verdicts TO appuser;
GRANT ALL PRIVILEGES ON TABLE analysis_results TO appuser;
GRANT ALL PRIVILEGES ON TABLE users TO appuser;

-- Grant sequence permissions (for SERIAL/auto-increment columns)
GRANT USAGE, SELECT ON SEQUENCE users_id_seq TO appuser;

-- Grant permissions on the schema (if needed)
GRANT ALL PRIVILEGES ON SCHEMA public TO appuser;

-- Grant default privileges for future tables (optional but recommended)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO appuser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO appuser;

-- Verify permissions
SELECT 
    grantee, 
    table_schema, 
    table_name, 
    privilege_type 
FROM 
    information_schema.role_table_grants 
WHERE 
    grantee = 'appuser'
ORDER BY 
    table_name, 
    privilege_type;

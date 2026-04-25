-- Create development database (primary)
-- This is already created by POSTGRES_DB environment variable

-- Create test database
CREATE DATABASE analysi_test;

-- Grant permissions to dev user for test database
GRANT ALL PRIVILEGES ON DATABASE analysi_test TO dev;

-- Connect to test database and enable required extensions
\c analysi_test;

-- Enable pgcrypto extension for UUID generation in test database
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Enable pg_partman for automated partition management
CREATE SCHEMA IF NOT EXISTS partman;
CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman;

-- Enable pgvector for vector similarity search (Project Paros)
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_cron for scheduled maintenance jobs
-- Note: pg_cron can only be created in the database set in cron.database_name
-- (analysi_db). For the test database, we only need pg_partman.

-- Back to development database to ensure it also has extensions
\c analysi_db;

-- Enable pgcrypto extension for UUID generation in development database
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Enable pg_partman for automated partition management
CREATE SCHEMA IF NOT EXISTS partman;
CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman;

-- Enable pgvector for vector similarity search (Project Paros)
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_cron for scheduled maintenance jobs
CREATE EXTENSION IF NOT EXISTS pg_cron;

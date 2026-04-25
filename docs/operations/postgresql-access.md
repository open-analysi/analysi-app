# PostgreSQL Database Access Guide

This guide documents how to access the PostgreSQL database for debugging, testing, and maintenance tasks.

## Quick Access Commands

### Production/Docker Environment
```bash
# Access PostgreSQL in Docker container
docker exec analysi-postgres sh -c "PGPASSWORD=devpassword psql -h localhost -U dev -d analysi_db"

# Run a single query
docker exec analysi-postgres sh -c "PGPASSWORD=devpassword psql -h localhost -U dev -d analysi_db -c \"SELECT COUNT(*) FROM components;\""
```

### Test Database (Branch-Isolated)

Each branch gets its own ephemeral test database via `make test-db-up`. Connection
info is written to `.env.test.local` (gitignored) with a dynamically allocated port.

```bash
# Start per-branch test DB (creates analysi_test_<branch-slug> on a unique port)
make test-db-up

# Access it (read port from .env.test.local)
source .env.test.local
PGPASSWORD=devpassword psql -h localhost -p $ANALYSI_TEST_DB_PORT -U dev -d $ANALYSI_TEST_DB_NAME

# Tear down when done
make test-db-down
```

## Step-by-Step Process to Find Database Credentials

### 1. Check Docker Container Names
First, identify the PostgreSQL container:
```bash
docker ps --format "table {{.Names}}\t{{.Image}}" | grep postgres
```
Output example:
```
analysi-postgres                analysi-postgres:15-partman
analysi-postgres-exporter       prometheuscommunity/postgres-exporter:latest
```

### 2. Find Database Credentials
Check the `.env` file for database configuration:
```bash
grep -E "POSTGRES_|DATABASE_" .env
```

Key variables to look for:
- `POSTGRES_USER`: Database username (typically `dev`)
- `POSTGRES_PASSWORD`: Database password (typically `devpassword`)
- `POSTGRES_DB`: Database name (typically `analysi_db`)
- `POSTGRES_EXTERNAL_PORT`: Host port for external access (typically `5434`)

### 3. Determine Correct Database Name
The database name might differ from what you expect. Check available databases:
```bash
docker exec analysi-postgres sh -c "PGPASSWORD=devpassword psql -h localhost -U dev -l"
```

Common database names:
- `analysi_db` - Main development database (Docker)
- `analysi` - Production database
- `analysi_test_<branch-slug>` - Per-branch test database (created by `make test-db-up`)

### 4. Access Database from Docker Container
```bash
# Template
docker exec <container-name> sh -c "PGPASSWORD=<password> psql -h localhost -U <user> -d <database>"

# Actual command
docker exec analysi-postgres sh -c "PGPASSWORD=devpassword psql -h localhost -U dev -d analysi_db"
```

### 5. Access Database from Host Machine
```bash
# Template (note the port is the external port from .env)
PGPASSWORD=<password> psql -h localhost -p <external-port> -U <user> -d <database>

# Actual command
PGPASSWORD=devpassword psql -h localhost -p 5434 -U dev -d analysi_db
```

## Common Database Queries for Testing

### Check for NULL cy_names
```sql
-- Count components with NULL cy_name
SELECT COUNT(*) as null_count FROM components WHERE cy_name IS NULL;

-- List components with NULL cy_name
SELECT id, name, kind, created_at FROM components WHERE cy_name IS NULL;

-- Check specific component
SELECT id, name, cy_name, kind FROM components WHERE name LIKE '%Task%';
```

### Verify Table Structure
```sql
-- List all tables
\dt

-- Show table structure
\d components

-- Check if a column exists
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'components' AND column_name = 'cy_name';
```

### Task and Component Queries
```sql
-- Find tasks by cy_name
SELECT c.id, c.name, c.cy_name, t.script
FROM components c
JOIN tasks t ON t.component_id = c.id
WHERE c.cy_name = 'my_task_name';

-- List all tasks with their cy_names
SELECT c.name, c.cy_name, c.status
FROM components c
WHERE c.kind = 'task'
ORDER BY c.created_at DESC;

-- Find duplicate cy_names (should be none)
SELECT cy_name, COUNT(*)
FROM components
WHERE cy_name IS NOT NULL
GROUP BY cy_name, tenant_id, app
HAVING COUNT(*) > 1;
```

## Common Issues and Solutions

### Issue: "FATAL: role does not exist"
**Solution**: Check the correct username in `.env` file. It's usually `dev`, not `postgres` or `analysi_user`.

### Issue: "database does not exist"
**Solution**: The database name in Docker is `analysi_db`, not `analysi`. Check with `\l` command.

### Issue: "relation does not exist"
**Solution**: Table names are plural (`components`, `tasks`, `alerts`, `workflows`). Check with `\dt` to list all tables.

### Issue: Cannot connect from host machine
**Solution**: Use the external port (5434) not the internal port (5432):
```bash
# Wrong
psql -h localhost -p 5432 ...

# Correct
psql -h localhost -p 5434 ...
```

## Python Script Access
When writing Python scripts to access the database:

```python
# Docker internal connection (from within container)
DATABASE_URL = "postgresql+asyncpg://dev:devpassword@analysi-postgres:5432/analysi_db"

# External connection (from host machine)
DATABASE_URL = "postgresql+asyncpg://dev:devpassword@localhost:5434/analysi_db"

# Test database (read from .env.test.local after make test-db-up)
# TEST_DATABASE_URL = "postgresql+asyncpg://dev:devpassword@localhost:<dynamic-port>/analysi_test_<branch>"
```

## Environment-Specific Configurations

### Development (Docker Compose)
- Container name: `analysi-postgres`
- Internal port: 5432
- External port: 5434
- Database: `analysi_db`
- User: `dev`
- Password: `devpassword`

### Test Environment (Per-Branch)
- Database: `analysi_test_<branch-slug>` (dynamically created)
- Port: dynamically allocated (written to `.env.test.local`)
- Same credentials as development (dev/devpassword)
- Created via `make test-db-up`, torn down via `make test-db-down`

### CI/CD Pipeline
- May use different credentials
- Check GitHub Actions secrets or CI configuration

## Useful PostgreSQL Commands

```sql
-- Show current database
SELECT current_database();

-- Show current user
SELECT current_user;

-- List all schemas
\dn

-- Show table sizes
SELECT
    schemaname AS table_schema,
    tablename AS table_name,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Show active connections
SELECT pid, usename, application_name, client_addr, state
FROM pg_stat_activity
WHERE datname = current_database();

-- Kill a connection (if needed)
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE pid = <process_id>;
```

## Security Notes

1. **Never commit passwords**: The `.env` file should be in `.gitignore`
2. **Use environment variables**: Don't hardcode credentials in scripts
3. **Limit access**: Use read-only users when possible for queries
4. **SSL in production**: Always use SSL connections in production

## Troubleshooting Checklist

1. ✅ Container is running: `docker ps | grep postgres`
2. ✅ Correct container name: `analysi-postgres`
3. ✅ Correct credentials from `.env`
4. ✅ Correct database name: `analysi_db` (Docker) or check `.env.test.local` (tests)
5. ✅ Correct port: 5434 (external) or 5432 (internal), dynamic for test DBs
6. ✅ Table names are plural: `components`, `tasks`, `alerts`

## Quick One-Liner Examples

```bash
# Count alerts
docker exec analysi-postgres sh -c "PGPASSWORD=devpassword psql -h localhost -U dev -d analysi_db -c \"SELECT COUNT(*) FROM alerts;\""

# List workflows
docker exec analysi-postgres sh -c "PGPASSWORD=devpassword psql -h localhost -U dev -d analysi_db -c \"SELECT id, name, status FROM workflows ORDER BY created_at DESC LIMIT 10;\""

# Check partition health
docker exec analysi-postgres sh -c "PGPASSWORD=devpassword psql -h localhost -U dev -d analysi_db -c \"SELECT * FROM partman.part_config;\""
```

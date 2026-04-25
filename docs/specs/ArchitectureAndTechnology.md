+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "Technology stack overview"
+++

# Architecture and Technology

## Technology Stack
- **FastAPI REST API**: Python with Uvicorn ASGI server, OpenAPI specs
- **PostgreSQL**: Flyway migrations, dockerized dev (RDS production)
- **SQLAlchemy**: Async ORM with `Annotated` DI pattern
- **Docker Compose**: Development orchestration
- **Poetry**: Python dependency management

## Database Architecture

### PostgreSQL Setup
- pgAdmin pre-configured, single service direct access
- Disable SSL in dev: `connect_args={"ssl": False}`
- Use `text()` for raw SQL queries
- Database reset: `fix_db.sh` script (stops containers, removes volume, restarts, applies migrations)

## Component Inheritance Pattern

### Problem
Share common metadata (tenant_id, name, description) between entity types (Tasks, Knowledge Units) while balancing normalization, API simplicity, performance, and maintainability.

### Architecture
```
API Layer (flat schemas) → Router (field mapping) → Service → Repository (Component + Entity ops) → Database (component ← entity FK+CASCADE)
```

### Schema Design
**Component (base)**: id, tenant_id, kind enum, name, description, status, metadata fields
**Task (derived)**: id, component_id (FK CASCADE), script, directive, function, scope, llm_config

### Key Patterns

#### Repository Operations
- **Create**: Component first, flush for ID, then Task with component_id
- **Update**: Separate component/task fields, update both tables, refresh relationships
- **Delete**: Delete Component (cascade removes Task)
- **Query**: JOIN Component, load relationships for API responses

#### API Mapping
Manually combine Component + Task fields for flat response schemas

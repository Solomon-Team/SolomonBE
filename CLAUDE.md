# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BookKeeper is a FastAPI-based backend for a Minecraft server economy/guild management system. It tracks player inventories, trades, locations, parties, and messages with a multi-tenant architecture using PostgreSQL.

**Key Concept**: Multi-tenant system where `structure_id` (e.g., "GPR") scopes nearly all data. Each structure has its own users, items, locations, roles, and permissions.

## Development Commands

### Running the Application

```bash
# Local development (requires PostgreSQL running)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# With Docker Compose (includes database)
docker-compose up
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

### Development Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Core Structure

- **app/main.py**: FastAPI application entry point with CORS middleware and router registration
- **app/core/**: Configuration, database connection, security (JWT, bcrypt)
- **app/models/**: SQLAlchemy ORM models (all inherit from `Base`)
- **app/schemas/**: Pydantic models for request/response validation
- **app/routes/**: API endpoint handlers (grouped by resource)
- **app/services/**: Business logic, dependencies, and utilities
- **migrations/**: Alembic database migrations

### Multi-Tenant Design

Almost all models have a `structure_id` column. When querying data, filter by the current user's structure:

```python
# Get structure from authenticated user
structure_id = user.structure_id

# Query scoped to structure
db.query(Item).filter(Item.structure_id == structure_id)
```

### Authentication Flow

1. User logs in via `/auth/login` with username/password
2. Backend returns JWT token containing `sub: user_id`
3. Protected routes use `get_current_user` dependency to extract user from token
4. User object includes eager-loaded roles for permission checks

### Permission System

Role-based permissions stored as JSON in `Role.permissions`:

```python
# Check permission
from app.services.deps import has_perm, require_perm

# In route handler
if not has_perm(user, "items.manage"):
    raise HTTPException(403)

# As dependency
@router.get("/admin")
def admin_route(user: User = Depends(require_perm("users.admin"))):
    ...
```

### Trade System

Trades have a complex lifecycle managed by `app/services/trade_hooks.py`:

- **TradeLine** records specify direction (`GAINED`/`GIVEN`), item, quantity, locations
- **apply_user_ledgers_and_inventory()** updates:
  - `PlayerInventory` (current balances)
  - `PlayerInventoryLedger` (historical transactions)
- Profit calculated by valuing each line at trade timestamp

### Minecraft Integration

The system ingests live Minecraft data via `/mc/ingest` endpoint:

- **MCIngestToken**: Authentication for mod/plugin sending data
- **MCLivePlayer**: Real-time player positions, world, online status
- **MCPositionHistory**: Historical position snapshots (throttled)
- **MCPlayerInventorySnapshot/MCContainerSnapshot**: Inventory states
- Links Minecraft UUIDs to internal users via `UserProfile.minecraft_uuid` or `minecraft_username`

See `app/services/mc_ingest.py` for ingestion logic and `app/services/mc_policy.py` for message routing based on player proximity.

### Seeding System

`app/services/seed.py` provides idempotent demo data creation:

- Default structure "GPR" (Golden Prosperity)
- Item categories, core items, valuations
- Movement reasons (GAINED, GIVEN, TRANSFERRED, etc.)
- System roles (ADMIN, GUILDMASTER, TRADER, MEMBER)
- Locations, users, sample trades

Runs automatically on FastAPI startup (`@app.on_event("startup")`).

### Messaging System

Messages support multiple target types:

- **INDIVIDUAL**: Direct user-to-user
- **PARTY**: To party members
- **LOCATION**: Position-based (uses MCPositionHistory)
- **BROADCAST**: Structure-wide

`MessageRecipientStatus` tracks read/unread per recipient. Location-based delivery uses `MessagePositionPolicy` (distance, world matching).

## Important Conventions

### Database Sessions

Always use the `get_db` dependency for session management:

```python
@router.get("/items")
def list_items(db: Session = Depends(get_db)):
    # db will be automatically closed after request
```

### Error Handling

Use FastAPI's `HTTPException` with appropriate status codes:

```python
raise HTTPException(status_code=404, detail="Item not found")
raise HTTPException(status_code=403, detail="Not allowed")
```

### Model Relationships

Key relationships to remember:

- `User.roles` (many-to-many via association table)
- `User.structure_id` (every user belongs to one structure)
- `Trade.lines` (one-to-many)
- `Party.members` (many-to-many via `PartyMember`)
- `Message.targets` (one-to-many)

### Code Generation

`app/services/codegen.py` generates unique item codes. Use for creating new items:

```python
from app.services.codegen import generate_unique_item_code
code = generate_unique_item_code(db, structure_id)
```

## Environment Variables

Required in `.env`:

- `DATABASE_URL`: PostgreSQL connection string (format: `postgresql+psycopg://user:pass@host:port/db`)
- `JWT_SECRET`: Secret key for JWT signing
- `JWT_ALGORITHM`: Usually "HS256"
- `CORS_ALLOW_ORIGINS`: Comma-separated allowed origins

## Notes

- Database uses PostgreSQL-specific features (e.g., JSONB for role permissions)
- All datetime fields should use UTC (`datetime.utcnow()`)
- The system expects at least these movement reasons: GAINED, GIVEN, TRANSFERRED
- Item valuations (`ItemValue`) are timestamped for historical pricing
- Player inventory is calculated from ledger entries, not stored directly

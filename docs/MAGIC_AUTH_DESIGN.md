# Magic Link Authentication System Design

## Overview
Automatic authentication flow using Minecraft UUID-based magic links with optional password setup for web access.

## Database Schema Changes

### 1. **structures** (NEW TABLE)
Formalizes structure/organization entities.

```sql
CREATE TABLE structures (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

### 2. **users** (MODIFIED)
Updated to support magic link auth and optional passwords.

```sql
ALTER TABLE users
    ADD COLUMN mc_uuid VARCHAR(36) UNIQUE,           -- Minecraft UUID (primary identifier)
    ADD COLUMN mc_name VARCHAR(16),                   -- Minecraft username (display)
    ADD COLUMN login_name VARCHAR(50) UNIQUE,         -- Website login username (optional)
    ADD COLUMN has_password BOOLEAN NOT NULL DEFAULT FALSE,
    ALTER COLUMN hashed_password DROP NOT NULL,       -- Now nullable
    ALTER COLUMN structure_id DROP NOT NULL,          -- Now nullable
    ADD CONSTRAINT fk_users_structure FOREIGN KEY (structure_id) REFERENCES structures(id);

-- Make username nullable and non-unique (transitional)
ALTER TABLE users ALTER COLUMN username DROP NOT NULL;
DROP INDEX IF EXISTS ix_users_username;
CREATE INDEX ix_users_login_name ON users(login_name);
CREATE INDEX ix_users_mc_uuid ON users(mc_uuid);
```

**Key Changes:**
- `mc_uuid`: Primary identifier from Minecraft (unique, indexed)
- `mc_name`: Display name from Minecraft
- `login_name`: Username for website login (only set after password setup)
- `has_password`: Flag to track if user has set a password
- `hashed_password`: Now nullable (not required for MC-only users)
- `structure_id`: Now nullable with FK constraint to structures table

### 3. **magic_login_tokens** (NEW TABLE)
Short-lived tokens for magic link authentication.

```sql
CREATE TABLE magic_login_tokens (
    id SERIAL PRIMARY KEY,
    token VARCHAR(64) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mc_uuid VARCHAR(36),                             -- Track which MC account requested
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    ip_address VARCHAR(45),                          -- Track request IP
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_magic_tokens_token ON magic_login_tokens(token);
CREATE INDEX ix_magic_tokens_expires ON magic_login_tokens(expires_at);
CREATE INDEX ix_magic_tokens_user ON magic_login_tokens(user_id);
```

**Token Lifecycle:**
- Generated with 5-minute expiry
- Single-use (marked with `used_at` timestamp)
- Auto-cleanup of expired tokens (background job or query filter)

### 4. **structure_join_codes** (NEW TABLE)
Invite codes for joining structures/organizations.

```sql
CREATE TABLE structure_join_codes (
    id SERIAL PRIMARY KEY,
    code VARCHAR(16) NOT NULL UNIQUE,
    structure_id VARCHAR(50) NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
    created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP WITH TIME ZONE,             -- NULL = never expires
    max_uses INTEGER,                                 -- NULL = unlimited
    used_count INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_join_codes_code ON structure_join_codes(code);
CREATE INDEX ix_join_codes_structure ON structure_join_codes(structure_id);
CREATE INDEX ix_join_codes_active ON structure_join_codes(is_active, expires_at);
```

**Code Properties:**
- 8-12 character alphanumeric codes (e.g., "JOIN-WHB-2024")
- Optional expiration date
- Optional max use count
- Can be deactivated without deletion
- Track usage count

### 5. **auth_audit_log** (NEW TABLE)
Security audit trail for authentication events.

```sql
CREATE TABLE auth_audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(50) NOT NULL,                 -- 'magic_link_request', 'magic_login', 'password_set', 'login_success', 'login_failed'
    mc_uuid VARCHAR(36),
    ip_address VARCHAR(45),
    user_agent TEXT,
    metadata JSONB,                                   -- Additional context
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_auth_audit_user ON auth_audit_log(user_id, created_at);
CREATE INDEX ix_auth_audit_event ON auth_audit_log(event_type, created_at);
CREATE INDEX ix_auth_audit_mc ON auth_audit_log(mc_uuid);
```

---

## API Endpoints

### A. Minecraft-Initiated Flows

#### 1. **POST /api/mc/magic-link**
Request a magic login link.

**Request:**
```json
{
  "mcUuid": "550e8400-e29b-41d4-a716-446655440000",
  "mcName": "Steve"
}
```

**Response (200):**
```json
{
  "token": "abc123def456...",
  "magicUrl": "https://bookkeeper.example.com/#/magic-login/abc123def456...",
  "expiresAt": "2024-01-15T10:35:00Z",
  "isNewUser": true
}
```

**Flow:**
1. Rate limit: 1 request per mcUuid per minute
2. Find or create user by `mc_uuid`
3. If new user: `INSERT INTO users (mc_uuid, mc_name, has_password=FALSE)`
4. Generate random 64-char token
5. Store in `magic_login_tokens` with 5-min expiry
6. Log to `auth_audit_log`
7. Return token + URL

**Rate Limiting:**
- 1 request per minute per `mcUuid`
- 10 requests per minute per IP
- Return 429 with `Retry-After` header

---

#### 2. **POST /api/mc/join-structure**
Join a structure using a code (from Minecraft).

**Request:**
```json
{
  "mcUuid": "550e8400-e29b-41d4-a716-446655440000",
  "code": "JOIN-WHB-2024"
}
```

**Response (200):**
```json
{
  "success": true,
  "structureId": "WHB",
  "structureName": "Warehouse Base",
  "message": "Successfully joined Warehouse Base"
}
```

**Flow:**
1. Find user by `mc_uuid` (404 if not found)
2. Validate join code:
   - Exists and `is_active = TRUE`
   - Not expired (`expires_at > NOW()` or NULL)
   - Not at max uses (`used_count < max_uses` or NULL)
3. If user already in another structure → error (must leave first)
4. Update `user.structure_id = code.structure_id`
5. Increment `code.used_count`
6. Log to `auth_audit_log`
7. Return success

**Error Cases:**
- 404: User not found (mcUuid not registered)
- 400: Invalid code
- 400: Code expired
- 400: Code at max uses
- 409: User already in a structure

---

### B. Web-Initiated Flows

#### 3. **POST /api/auth/magic-login**
Exchange magic token for JWT.

**Request:**
```json
{
  "token": "abc123def456..."
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "userId": 123,
    "mcUuid": "550e8400-e29b-41d4-a716-446655440000",
    "mcName": "Steve",
    "loginName": null,
    "hasPassword": false,
    "structureId": null,
    "roles": []
  }
}
```

**Flow:**
1. Find token in `magic_login_tokens`
2. Validate:
   - Not expired (`expires_at > NOW()`)
   - Not already used (`used_at IS NULL`)
3. Mark as used (`used_at = NOW()`)
4. Load user with roles
5. Generate JWT with payload:
   ```json
   {
     "sub": "123",
     "mcUuid": "550e8400-...",
     "mcName": "Steve",
     "loginName": null,
     "hasPassword": false,
     "structureId": null,
     "roleIds": [],
     "roleCodes": [],
     "permissions": {}
   }
   ```
6. Log to `auth_audit_log`
7. Return JWT + user data

**Error Cases:**
- 404: Token not found
- 401: Token expired
- 401: Token already used

---

#### 4. **POST /api/auth/set-password**
Set username and password for web login (requires JWT).

**Request (with Authorization: Bearer <jwt>):**
```json
{
  "loginName": "steve_the_miner",
  "password": "SecurePassword123!"
}
```

**Response (200):**
```json
{
  "success": true,
  "loginName": "steve_the_miner"
}
```

**Flow:**
1. Verify JWT (must be authenticated)
2. Validate `loginName` not already taken
3. Validate password strength:
   - Min 8 characters
   - At least 1 uppercase, 1 lowercase, 1 number
4. Hash password with bcrypt
5. Update user:
   ```sql
   UPDATE users
   SET login_name = ?, hashed_password = ?, has_password = TRUE
   WHERE id = ?
   ```
6. Log to `auth_audit_log`
7. Return success

**Error Cases:**
- 401: Not authenticated
- 409: loginName already taken
- 400: Password too weak

---

#### 5. **POST /api/auth/login**
Standard username/password login.

**Request:**
```json
{
  "loginName": "steve_the_miner",
  "password": "SecurePassword123!"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "userId": 123,
    "mcUuid": "550e8400-...",
    "mcName": "Steve",
    "loginName": "steve_the_miner",
    "hasPassword": true,
    "structureId": "WHB",
    "roles": ["MEMBER"]
  }
}
```

**Flow:**
1. Find user by `login_name`
2. Verify password (bcrypt)
3. Generate JWT (same structure as magic-login)
4. Log to `auth_audit_log`
5. Return JWT + user data

**Error Cases:**
- 401: Invalid credentials (don't specify which field is wrong)

---

### C. Structure Management

#### 6. **POST /api/structures/{structureId}/codes**
Generate a join code (requires leader permission).

**Request (with Authorization: Bearer <jwt>):**
```json
{
  "expiresAt": "2024-12-31T23:59:59Z",  // optional
  "maxUses": 100                          // optional
}
```

**Response (200):**
```json
{
  "id": 42,
  "code": "JOIN-WHB-2024",
  "structureId": "WHB",
  "expiresAt": "2024-12-31T23:59:59Z",
  "maxUses": 100,
  "usedCount": 0,
  "createdAt": "2024-01-15T10:00:00Z"
}
```

**Permissions Required:**
- `structures.manage` OR user is structure leader

---

#### 7. **GET /api/structures/{structureId}/codes**
List all join codes for a structure.

**Response (200):**
```json
{
  "codes": [
    {
      "id": 42,
      "code": "JOIN-WHB-2024",
      "expiresAt": "2024-12-31T23:59:59Z",
      "maxUses": 100,
      "usedCount": 15,
      "isActive": true,
      "createdBy": "admin",
      "createdAt": "2024-01-15T10:00:00Z"
    }
  ]
}
```

---

#### 8. **DELETE /api/structures/{structureId}/codes/{codeId}**
Revoke a join code.

**Response (200):**
```json
{
  "success": true
}
```

**Flow:**
- Set `is_active = FALSE` (soft delete)

---

#### 9. **POST /api/structures/join**
Join a structure using a code (from website, requires JWT).

**Request (with Authorization: Bearer <jwt>):**
```json
{
  "code": "JOIN-WHB-2024"
}
```

**Response (200):**
```json
{
  "success": true,
  "structureId": "WHB",
  "structureName": "Warehouse Base"
}
```

**Flow:**
- Same validation as `/api/mc/join-structure`
- Uses JWT user instead of mcUuid lookup

---

#### 10. **POST /api/structures/{structureId}/leave**
Leave current structure (set structure_id = NULL).

**Response (200):**
```json
{
  "success": true
}
```

---

#### 11. **DELETE /api/structures/{structureId}/members/{userId}**
Kick a member (requires leader permission).

**Response (200):**
```json
{
  "success": true
}
```

**Flow:**
- Set `target_user.structure_id = NULL`
- Log to audit

---

## JWT Payload Structure

```json
{
  "sub": "123",                    // User ID
  "mcUuid": "550e8400-...",        // Minecraft UUID
  "mcName": "Steve",               // Minecraft display name
  "loginName": "steve_the_miner",  // Website username (null if not set)
  "hasPassword": true,             // Boolean flag
  "structureId": "WHB",            // Current structure (null if none)
  "roleIds": [1, 2],               // Role IDs
  "roleCodes": ["MEMBER"],         // Role codes
  "exp": 1705318800                // Expiration timestamp
}
```

**Note:** Removed `permissions` from JWT to avoid stale permission cache.

---

## Rate Limiting Strategy

### Endpoints to Rate Limit:
1. `POST /api/mc/magic-link`: 1/min per mcUuid, 10/min per IP
2. `POST /api/auth/magic-login`: 5/min per IP
3. `POST /api/auth/login`: 5/min per IP, 10/hour per loginName
4. `POST /api/auth/set-password`: 3/hour per user

### Implementation:
- Use `slowapi` library with Redis backend
- Store rate limit state in Redis with TTL
- Return 429 with `Retry-After` header

---

## Security Considerations

1. **Magic Token Security:**
   - 64 random bytes (base64url encoded)
   - 5-minute expiry
   - Single-use only
   - Stored hashed in database

2. **Password Requirements:**
   - Minimum 8 characters
   - At least 1 uppercase letter
   - At least 1 lowercase letter
   - At least 1 number
   - Optional: 1 special character

3. **Audit Logging:**
   - All authentication events logged
   - IP address and user agent captured
   - Failed attempts tracked

4. **Structure Isolation:**
   - Users can only be in one structure at a time
   - Must leave before joining another
   - FK constraints enforce data integrity

5. **Code Generation:**
   - Use `secrets.token_urlsafe()` for codes
   - Format: `JOIN-{STRUCT}-{RANDOM}`
   - Collision detection

---

## Migration Plan

### Phase 1: Database Schema
1. Create `structures` table
2. Migrate existing structure_ids to `structures`
3. Add FK constraint to `users.structure_id`
4. Add new columns to `users` table
5. Create `magic_login_tokens` table
6. Create `structure_join_codes` table
7. Create `auth_audit_log` table

### Phase 2: Backend API
1. Update User model
2. Create new models (MagicLoginToken, StructureJoinCode, Structure, AuthAuditLog)
3. Update security.py
4. Implement rate limiting middleware
5. Create MC routes
6. Create auth routes
7. Create structure management routes
8. Update existing login endpoint
9. Update seed data

### Phase 3: Minecraft Mod
1. Add HTTP client library
2. Implement magic-link request on join
3. Display clickable URL in chat
4. Add `/join <code>` command
5. Add structure UI (optional)

### Phase 4: Vue Frontend
1. Create `/magic-login/:token` route
2. Create SetPassword component
3. Create JoinStructure component
4. Create StructureManagement component (for leaders)
5. Update login page
6. Add "Login with Minecraft" option

---

## Environment Variables

Add to `.env`:

```
# Rate Limiting
REDIS_URL=redis://localhost:6379/0
RATE_LIMIT_ENABLED=true

# Magic Link
MAGIC_LINK_EXPIRY_MINUTES=5
MAGIC_LINK_BASE_URL=https://bookkeeper.example.com

# Frontend URL
FRONTEND_URL=https://bookkeeper.example.com
```

---

## Testing Checklist

### Unit Tests:
- [ ] Magic token generation and validation
- [ ] Join code generation and validation
- [ ] Password strength validation
- [ ] Rate limiting logic

### Integration Tests:
- [ ] Full magic-link flow (MC → Web)
- [ ] Password setup flow
- [ ] Join structure flow (both MC and web)
- [ ] Code expiration and max uses
- [ ] Rate limit enforcement

### E2E Tests:
- [ ] New MC player → magic link → set password → web login
- [ ] Structure leader creates code → member joins
- [ ] Leave structure → join another

---

## Backward Compatibility

During migration:
- Existing users with `username` and `hashed_password` can still login
- Map old `username` to `login_name`
- Add default `mc_uuid` if missing (generate fake UUID or leave NULL)
- Existing structure_ids must be migrated to `structures` table first

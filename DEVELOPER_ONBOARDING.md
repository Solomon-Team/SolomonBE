# BookKeeper Developer Guide
**Multi-Tenant Minecraft Economy & Guild Management System**

> **Quick Start**: Backend (FastAPI/PostgreSQL) + Frontend (Vue 3/TypeScript) + Minecraft Mod (Fabric/Java)

---

## 🏗️ System Architecture

### Overview
BookKeeper is a **multi-tenant system** where each `structure_id` (e.g., "GPR" for Golden Prosperity) represents an independent guild/economy with its own users, items, locations, and permissions.

### Three-Component Stack

```
┌─────────────────┐      HTTP/WebSocket      ┌──────────────────┐
│  Minecraft Mod  │ ◄──────────────────────► │  Backend (API)   │
│  (Fabric/Java)  │                           │  FastAPI + PG    │
└─────────────────┘                           └────────┬─────────┘
                                                       │
                                                  HTTP/WS
                                                       │
                                              ┌────────▼─────────┐
                                              │  Frontend (Web)  │
                                              │  Vue 3 + TS      │
                                              └──────────────────┘
```

**Data Flow**:
1. Minecraft mod → Backend: Player positions, inventory, chest data (HTTP POST + WebSocket)
2. Backend → Minecraft mod: Broadcast messages, chest sync updates (WebSocket)
3. Frontend → Backend: Trade creation, item management, user admin (HTTP + JWT)
4. Backend → Frontend: Real-time player positions (HTTP polling, WebSocket planned)

---

## 📁 Repository Structure

### Backend: `C:\BookKeeper\BackendBK`
**Tech Stack**: FastAPI, PostgreSQL, Alembic, JWT Auth, SQLAlchemy ORM, WebSocket

```
BackendBK/
├── app/
│   ├── main.py              # FastAPI entry point, CORS, router registration
│   ├── core/                # Config, database, security (JWT, bcrypt)
│   ├── models/              # SQLAlchemy ORM models (User, Item, Trade, etc.)
│   ├── schemas/             # Pydantic request/response models
│   ├── routes/              # API endpoints (auth, trades, mc, websockets)
│   ├── services/            # Business logic (deps, trade_hooks, mc_ingest, chest_sync)
│   └── migrations/          # Alembic database migrations
├── .env                     # DATABASE_URL, JWT_SECRET, CORS_ALLOW_ORIGINS
├── requirements.txt         # Python dependencies
└── CLAUDE.md               # Detailed backend documentation
```

**Key Concepts**:
- **Multi-tenant**: All queries filtered by `user.structure_id`
- **Auth**: JWT tokens via `/auth/login` or magic links (`/auth/magic-login`)
- **Permissions**: Role-based via `Role.permissions` JSON field
- **Minecraft Integration**: `/api/mc/events/jwt` ingests live data, WebSocket broadcasts updates

**How to Run**:
```bash
# Setup
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Configure .env
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/bookkeeper
JWT_SECRET=your-secret-key
CORS_ALLOW_ORIGINS=http://localhost:5173

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### Frontend: `C:\Users\mifan\Desktop\BookKeeper\frontend-vue`
**Tech Stack**: Vue 3, TypeScript, Vite, Pinia, UnoCSS, Axios, Chart.js, Leaflet

```
frontend-vue/
├── src/
│   ├── main.ts              # App initialization, Pinia, API setup
│   ├── pages/               # Route-level views (Dashboard, Trades, Inventory, Admin)
│   ├── components/          # Reusable UI (comms, items, ui primitives)
│   ├── stores/              # Pinia stores (auth, positions, items, comms)
│   ├── services/            # API clients (authApi, tradesApi, inventoryApi, etc.)
│   ├── router/              # Vue Router with auth guards
│   ├── layouts/             # AppShell (Sidebar + TopBar)
│   └── styles/              # Theme CSS variables
├── vite.config.ts           # Build config, dev proxy
├── package.json             # Dependencies & scripts
└── .env.development         # VITE_API_BASE_URL=http://localhost:8000
```

**Key Features**:
- **Auth**: JWT stored in localStorage, auto-logout on expiry
- **Real-time**: HTTP polling for player positions (4s interval)
- **Admin Tools**: User/role management, player linking, structure config
- **Messaging**: CHAT/TITLE/ACTIONBAR/BOSSBAR delivery to Minecraft
- **Inventory**: AE-style grid UI for item management

**How to Run**:
```bash
# Setup (Node v20.19+ or v22.12+)
npm install

# Start dev server
npm run dev  # → http://localhost:5173

# Build for production
npm run build  # → dist/
```

**Environment Variables** (`.env.development`):
```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_MOD_POLL_MS=4000
```

---

### Minecraft Mod: `C:\Users\mifan\Documents\GitHub\MinecraftMods\InventoryNetwork\InventoryNetwork`
**Tech Stack**: Fabric Loader, Java 21, OkHttp (HTTP + WebSocket), Gson (JSON)

```
InventoryNetwork/
├── src/
│   ├── main/java/com/BookKeeper/InventoryNetwork/
│   │   ├── InventoryNetworkMod.java       # Mod entry point
│   │   ├── ApiClient.java                 # HTTP client for backend
│   │   └── config/
│   │       └── BookKeeperConfig.java      # Config from inventory_network.json
│   └── client/java/com/BookKeeper/InventoryNetwork/
│       ├── InventoryNetworkModClient.java # Client initializer (events, modules)
│       ├── ChestTracker.java              # Detects chest opens/closes, sends data
│       ├── ChestHighlighter.java          # Renders chest outlines in-world
│       ├── ChestSyncManager.java          # Stores aggregated chest data from server
│       ├── WebSocketManager.java          # WebSocket connection with auto-reconnect
│       ├── EntityTracker.java             # Keybind to highlight entities
│       ├── CommandHandler.java            # /bk commands (join, leave, login, etc.)
│       ├── DatabaseManager.java           # Local H2 database (being phased out)
│       └── ui/
│           ├── InventoryPanelOverlay.java # In-game UI for searching chests
│           └── LoginScreen.java           # GUI for magic link auth
├── config/inventory_network.json          # API URL, auto magic link, polling
├── gradle.properties                      # Mod version, Minecraft version
└── build.gradle                           # Dependencies (Fabric API, OkHttp, Gson, H2)
```

**Key Features**:
- **Chest Tracking**: Detects opens/closes, sends to backend via HTTP POST
- **WebSocket**: Receives chest updates, messages from server
- **Magic Link Auth**: GUI for login, stores JWT in memory
- **Commands**: `/bk login`, `/bk join`, `/bk leave`, `/bk chestsync test`
- **Real-time Sync**: ChestSyncManager caches all chests from all players

**How to Build & Run**:
```bash
# Build mod JAR
gradlew.bat build  # → build/libs/*.jar

# Run Minecraft client (testing)
gradlew.bat runClient

# Install mod
# Copy JAR from build/libs/ to .minecraft/mods/
```

**Configuration** (`config/inventory_network.json`):
```json
{
  "apiBaseUrl": "http://localhost:8000",
  "autoMagicLink": true,
  "magicLinkCooldownSeconds": 60
}
```

---

## 🔗 Component Communication

### Backend ↔ Minecraft Mod

**HTTP Endpoints**:
- `POST /api/mc/events/jwt` - Ingest player position, inventory, **chest data**
  - Headers: `Authorization: Bearer {JWT}`
  - Body: `{"uuid": "...", "username": "...", "x": 100, "y": 64, "z": 200, "event": "Container", "Container": {...}}`
- `GET /api/mc/chests` - Fetch all chests (fallback for reconnection)

**WebSocket** (`ws://localhost:8000/ws/mc?token={JWT}`):
- Server → Mod: `{"type": "chest_full_state", "chests": [...]}` (on connection)
- Server → Mod: `{"type": "chest_update", "chest": {...}, "summary": {...}}` (incremental)
- Server → Mod: `{"type": "message", "text": "...", "kind": "CHAT"}` (broadcast messages)
- Mod → Server: `{"type": "pong"}` (heartbeat response)

### Backend ↔ Frontend

**HTTP Endpoints** (all require JWT in `Authorization: Bearer {token}`):
- `POST /auth/login` - Username/password → JWT
- `POST /auth/magic-login/request` - Request magic link
- `GET /trades` - List trades
- `POST /trades` - Create trade
- `GET /items` - Item catalog
- `GET /mc/positions/snapshot` - Recent player positions (polled by frontend)

**WebSocket** (planned, not yet implemented):
- Real-time trade notifications, position updates

---

## 🚀 Recent Feature: ChestSync (COMPLETED)

### What It Does
Synchronizes chest contents across all players in a structure in real-time. When any player opens a chest, the contents are sent to the backend, stored in the database, and broadcast to all connected clients via WebSocket.

### Implementation Status
- ✅ **Backend**: Database tables (`chest_sync_snapshot`, `chest_sync_history`), ingestion, WebSocket broadcast
- ✅ **Minecraft Mod**: ChestTracker sends data, ChestSyncManager receives updates
- ❌ **UI Integration**: Mod UI still uses local H2, needs to query ChestSyncManager

### Files Modified/Created

**Backend**:
- `app/models/chest_sync.py` - New models (ChestSyncSnapshot, ChestSyncHistory)
- `app/services/chest_sync.py` - Broadcast logic, query helpers
- `app/services/mc_ingest.py` - Dual-write + broadcast (lines 146-213)
- `app/routes/websockets.py` - Send full state on connection (lines 100-109)
- `app/schemas/mc.py` - ChestSnapshotOut, ChestSummaryStats
- `migrations/versions/659830dae6ac_chest_sync_tables.py` - Migration applied ✅

**Minecraft Mod**:
- `ChestSyncManager.java` - Aggregated chest data storage (282 lines)
- `ChestTracker.java` - Modified to send to backend (lines 207-245)
- `ApiClient.java` - `sendChestData()` method (lines 182-217)
- `WebSocketManager.java` - Chest message handlers (lines 176-232)

### Next Steps (UI Integration)
1. Update `InventoryPanelOverlay.java` to query `ChestSyncManager.getInstance()` instead of `DatabaseManager`
2. Update `ChestHighlighter.java` to use ChestSyncManager data
3. Add "Last opened by: PlayerName" visual indicator
4. Test with 2+ players opening same chest

---

## 🛠️ Development Workflow

### Adding a New Feature

**Example: Add a "Favorites" system for items**

1. **Backend** (FastAPI):
   ```bash
   # 1. Create migration
   alembic revision --autogenerate -m "add_favorites_table"

   # 2. Add model (app/models/favorite.py)
   class Favorite(Base):
       __tablename__ = "favorites"
       id: Mapped[int] = mapped_column(Integer, primary_key=True)
       user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
       item_code: Mapped[str] = mapped_column(String(50))

   # 3. Add schema (app/schemas/favorite.py)
   class FavoriteCreate(BaseModel):
       item_code: str

   # 4. Add route (app/routes/favorites.py)
   @router.post("/favorites")
   def add_favorite(payload: FavoriteCreate, user = Depends(get_current_user)):
       # ...

   # 5. Register router (app/main.py)
   app.include_router(favorites_router)

   # 6. Apply migration
   alembic upgrade head
   ```

2. **Frontend** (Vue):
   ```bash
   # 1. Add API service (src/services/favoritesApi.ts)
   export const addFavorite = (itemCode: string) =>
     api.post('/favorites', { item_code: itemCode })

   # 2. Add store (src/stores/favorites.ts)
   export const useFavoritesStore = defineStore('favorites', () => {
     const favorites = ref<string[]>([])
     const add = async (itemCode: string) => {
       await addFavorite(itemCode)
       favorites.value.push(itemCode)
     }
     return { favorites, add }
   })

   # 3. Add component (src/components/FavoriteButton.vue)
   <template>
     <button @click="toggleFavorite">⭐</button>
   </template>

   # 4. Use in page (src/pages/ItemsCatalog.vue)
   const favStore = useFavoritesStore()
   ```

3. **Minecraft Mod** (Java - optional):
   ```java
   // 1. Add API method (ApiClient.java)
   public boolean addFavorite(String jwtToken, String itemCode) {
       JsonObject body = new JsonObject();
       body.addProperty("item_code", itemCode);
       // POST request...
   }

   // 2. Add command (CommandHandler.java)
   Commands.literal("favorite")
       .then(Commands.argument("item", StringArgumentType.string())
           .executes(ctx -> {
               String item = StringArgumentType.getString(ctx, "item");
               apiClient.addFavorite(token, item);
               return 1;
           }))
   ```

---

## 📝 Key Conventions

### Backend
- **Always filter by `structure_id`**: `db.query(Item).filter(Item.structure_id == user.structure_id)`
- **Use dependencies**: `user = Depends(get_current_user)` for auth, `db = Depends(get_db)` for sessions
- **Error handling**: `raise HTTPException(status_code=404, detail="Not found")`
- **Async for WebSocket/broadcast**: `async def my_route()` if calling `await broadcast_chest_update()`

### Frontend
- **API calls in services**: Never call axios directly in components
- **State in Pinia stores**: Global state goes in stores, local state in `ref()`/`reactive()`
- **Auth guard**: Add `meta: { requiresAuth: true }` to protected routes
- **Toast notifications**: `const toastStore = useToastStore(); toastStore.add({ message: "..." })`

### Minecraft Mod
- **JWT from WebSocketManager**: `String token = WebSocketManager.getInstance().getJwtToken()`
- **Background threads**: Wrap HTTP calls in `new Thread(() -> { ... }, "ThreadName").start()`
- **Logging**: Use `InventoryNetworkMod.LOGGER.info/warn/error`
- **Client-only code**: Must be in `src/client/java`, not `src/main/java`

---

## 🐛 Troubleshooting

### Backend won't start
- ✅ Check PostgreSQL is running
- ✅ Verify `.env` has correct `DATABASE_URL`
- ✅ Run `alembic upgrade head` to apply migrations
- ✅ Check port 8000 is not in use

### Frontend can't connect to backend
- ✅ Check CORS: `CORS_ALLOW_ORIGINS=http://localhost:5173` in backend `.env`
- ✅ Verify `VITE_API_BASE_URL=http://localhost:8000` in frontend
- ✅ Check backend logs for 401/403 errors (auth issue)

### Minecraft mod not sending data
- ✅ Check `config/inventory_network.json` has correct `apiBaseUrl`
- ✅ Verify JWT token: Look for "WebSocket connected" in `latest.log`
- ✅ Check backend logs for incoming requests at `/api/mc/events/jwt`
- ✅ Enable debug logging: Add `-Dfabric.log.level=debug` to JVM args

### Empty chests not updating
- ✅ Recent fix applied: Backend now accepts `e.container = {}` (empty dict)
- ✅ Restart backend if using `--reload`
- ✅ Check database: `SELECT * FROM chest_sync_snapshot WHERE items_json = '{}'`

---

## 📚 Additional Resources

- **Backend Docs**: `BackendBK/CLAUDE.md` - Detailed architecture, seeding, trade system
- **ChestSync Docs**: `BackendBK/CHESTSYNC_DEVELOPMENT.md` - Full implementation details
- **API Endpoints**: Run backend, visit `http://localhost:8000/docs` (FastAPI Swagger UI)
- **Frontend Types**: See `src/services/*.ts` for TypeScript interfaces

---

## 🎯 Onboarding Checklist

- [ ] Clone all 3 repos (Backend, Frontend, Minecraft Mod)
- [ ] Install dependencies (Python venv, npm, JDK 21)
- [ ] Set up PostgreSQL database
- [ ] Configure `.env` files (Backend, Frontend)
- [ ] Run migrations: `alembic upgrade head`
- [ ] Start backend: `uvicorn app.main:app --reload`
- [ ] Start frontend: `npm run dev`
- [ ] Build mod: `gradlew.bat build`
- [ ] Copy mod JAR to `.minecraft/mods/`
- [ ] Launch Minecraft, verify WebSocket connects
- [ ] Open a chest, verify data in database
- [ ] Check frontend can see player positions

**Welcome to BookKeeper!** 🎉

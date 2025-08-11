from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.core.database import SessionLocal
from app.routes import auth, trades, users, items, item_values, structure_settings, locations, roles, rbac
from app.services.seed import seed_examples

app = FastAPI()

# Allow origins from env (comma-separated) with sensible defaults
origins_env = os.getenv("CORS_ALLOW_ORIGINS", "")
origins = [o.strip() for o in origins_env.split(",") if o.strip()] or [
    "https://bookkeeperfe.onrender.com",  # Render frontend
    "http://localhost:5173",              # Vite dev
    "http://localhost:3000",              # alt dev ports
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(items.router)
app.include_router(item_values.router)
app.include_router(structure_settings.router)
app.include_router(trades.router)
app.include_router(users.router)
app.include_router(locations.router)
app.include_router(roles.router)
app.include_router(rbac.router)




@app.on_event("startup")
def on_startup():
    # Idempotent full seed for a rich demo dataset
    db = SessionLocal()
    try:
        seed_examples(db)
    finally:
        db.close()

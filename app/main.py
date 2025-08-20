from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.core.database import SessionLocal
from app.routes import auth, trades, users, items, item_values, structure_settings, locations, roles, rbac, inventory, \
    movement_reasons, item_icons, player_inventory, user_profiles, mc, auth_mc, parties, mc_messages, messages
from app.services.seed import seed_examples


app = FastAPI()

# Hardcoded allowed origins
origins = [
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
app.include_router(inventory.router)
app.include_router(movement_reasons.router)
app.include_router(item_icons.router)
app.include_router(user_profiles.router)
app.include_router(player_inventory.router)
app.include_router(mc.router)
app.include_router(auth_mc.router)
app.include_router(parties.router)
app.include_router(messages.router)
app.include_router(mc_messages.router)







@app.on_event("startup")
def on_startup():
    # Idempotent full seed for a rich demo dataset
    db = SessionLocal()
    try:
        seed_examples(db)
    finally:
        db.close()

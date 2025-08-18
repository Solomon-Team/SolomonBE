# create_mc_ingest_token.py
import os, secrets
from hashlib import sha256
from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.models.mc import MCIngestToken

def main():
    structure_id = str(os.environ.get("STRUCTURE_ID", "1"))
    name = os.environ.get("TOKEN_NAME", "default")
    token_plain = secrets.token_urlsafe(32)  # ~43 chars
    token_sha = sha256(token_plain.encode("utf-8")).hexdigest()
    db = SessionLocal()
    try:
        row = MCIngestToken(structure_id=structure_id, name=name, token_sha256=token_sha, active=True, created_at=datetime.now(timezone.utc))
        db.add(row)
        db.commit()
        print("STRUCTURE_ID:", structure_id)
        print("NAME:", name)
        print("INGEST_TOKEN:", token_plain)
        print("Store this token in your mod config; it won't be shown again.")
    finally:
        db.close()

if __name__ == "__main__":
    main()

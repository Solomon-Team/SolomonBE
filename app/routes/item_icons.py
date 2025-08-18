from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.deps import get_current_user, require_perm
from app.models.user import User
from app.models.item import Item

router = APIRouter(prefix="/items", tags=["items"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/{item_id}/icon", dependencies=[Depends(require_perm("items.manage"))])
async def upload_item_icon(
    item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    content = await file.read()
    if len(content) > 256 * 1024:
        raise HTTPException(status_code=413, detail="Icon too large (max 256KB)")

    item.icon_image = content
    item.icon_mime_type = file.content_type or "image/png"
    # You added icon_updated_at column already
    from datetime import datetime, timezone
    item.icon_updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "mime_type": item.icon_mime_type, "size": len(content)}

@router.get("/{item_id}/icon")
def get_item_icon(
    item_id: int,
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item or not item.icon_image:
        raise HTTPException(status_code=404, detail="Icon not found")
    return Response(content=bytes(item.icon_image), media_type=item.icon_mime_type or "image/png")

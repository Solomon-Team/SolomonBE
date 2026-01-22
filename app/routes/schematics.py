# app/routes/schematics.py
import hashlib
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.services.deps import get_db, get_current_user, require_perm
from app.models.user import User
from app.models.schematic import Schematic, SchematicSplitResult
from app.schemas.schematic import (
    SchematicOut,
    SchematicListOut,
    SchematicUploadResponse,
    SchematicUpdate,
    SplitResultOut,
    SplitResultsBatchCreate,
    SplitResultsBatchOut,
    LoadSchematicOnClientRequest,
    LoadSchematicOnClientResponse,
)
from app.services.websocket_manager import WebSocketManager

logger = logging.getLogger("bookkeeper.schematics")
router = APIRouter(prefix="/api/schematics", tags=["schematics"])

# Maximum file size for inline storage (10MB)
MAX_INLINE_SIZE = 10 * 1024 * 1024


@router.post("/upload", response_model=SchematicUploadResponse, status_code=201)
async def upload_schematic(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Upload a schematic file (.litematic).
    Files under 10MB are stored inline in the database.
    """
    # Validate file extension
    if not file.filename or not file.filename.endswith(".litematic"):
        raise HTTPException(400, "Only .litematic files are supported")

    # Read file content
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(400, "Empty file not allowed")

    # Calculate hash for deduplication
    file_hash = hashlib.sha256(content).hexdigest()

    # Check for duplicate hash in same structure
    existing = db.query(Schematic).filter(
        Schematic.structure_id == user.structure_id,
        Schematic.file_hash == file_hash
    ).first()

    if existing:
        raise HTTPException(409, f"A schematic with the same content already exists: {existing.name}")

    # Create schematic record
    schematic = Schematic(
        structure_id=user.structure_id,
        name=name,
        description=description,
        file_hash=file_hash,
        file_size=file_size,
        original_filename=file.filename,
        schematic_data=content if file_size <= MAX_INLINE_SIZE else None,
        storage_path=None,  # TODO: Implement external storage for large files
        uploaded_by_user_id=user.id,
        uploaded_at=datetime.now(timezone.utc),
        is_public=False,
    )

    if file_size > MAX_INLINE_SIZE:
        # TODO: Save to external storage and set storage_path
        raise HTTPException(413, f"File size {file_size} exceeds maximum inline storage of {MAX_INLINE_SIZE} bytes. Large file storage not yet implemented.")

    db.add(schematic)
    db.commit()
    db.refresh(schematic)

    logger.info(f"Schematic uploaded: id={schematic.id}, name={name}, size={file_size}, user={user.id}")

    return SchematicUploadResponse(
        id=schematic.id,
        name=schematic.name,
        file_hash=schematic.file_hash,
        file_size=schematic.file_size,
        original_filename=schematic.original_filename,
        uploaded_at=schematic.uploaded_at,
    )


@router.get("", response_model=List[SchematicListOut])
def list_schematics(
    q: Optional[str] = Query(None, description="Search by name"),
    include_public: bool = Query(False, description="Include public schematics from other structures"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List schematics accessible to the current user.
    """
    query = db.query(Schematic)

    if include_public:
        # Own schematics OR public ones
        query = query.filter(
            (Schematic.structure_id == user.structure_id) |
            (Schematic.is_public == True)
        )
    else:
        query = query.filter(Schematic.structure_id == user.structure_id)

    if q:
        like = f"%{q.lower()}%"
        query = query.filter(Schematic.name.ilike(like))

    schematics = query.order_by(Schematic.uploaded_at.desc()).all()

    # Add split results count
    result = []
    for s in schematics:
        result.append(SchematicListOut(
            id=s.id,
            name=s.name,
            description=s.description,
            file_size=s.file_size,
            original_filename=s.original_filename,
            uploaded_at=s.uploaded_at,
            is_public=s.is_public,
            split_results_count=len(s.split_results),
        ))

    return result


@router.get("/{schematic_id}", response_model=SchematicOut)
def get_schematic(
    schematic_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get schematic metadata by ID.
    """
    schematic = db.query(Schematic).filter(Schematic.id == schematic_id).first()

    if not schematic:
        raise HTTPException(404, "Schematic not found")

    # Check access
    if schematic.structure_id != user.structure_id and not schematic.is_public:
        raise HTTPException(403, "Access denied")

    return SchematicOut(
        id=schematic.id,
        structure_id=schematic.structure_id,
        name=schematic.name,
        description=schematic.description,
        file_hash=schematic.file_hash,
        file_size=schematic.file_size,
        original_filename=schematic.original_filename,
        uploaded_by_user_id=schematic.uploaded_by_user_id,
        uploaded_at=schematic.uploaded_at,
        is_public=schematic.is_public,
        has_split_results=len(schematic.split_results) > 0,
    )


@router.get("/{schematic_id}/download")
def download_schematic(
    schematic_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Download the schematic file.
    """
    schematic = db.query(Schematic).filter(Schematic.id == schematic_id).first()

    if not schematic:
        raise HTTPException(404, "Schematic not found")

    # Check access
    if schematic.structure_id != user.structure_id and not schematic.is_public:
        raise HTTPException(403, "Access denied")

    if schematic.schematic_data is None:
        if schematic.storage_path:
            # TODO: Read from external storage
            raise HTTPException(501, "External storage not yet implemented")
        raise HTTPException(404, "Schematic data not found")

    return Response(
        content=schematic.schematic_data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{schematic.original_filename}"',
            "Content-Length": str(schematic.file_size),
        }
    )


@router.patch("/{schematic_id}", response_model=SchematicOut)
def update_schematic(
    schematic_id: int,
    payload: SchematicUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Update schematic metadata.
    """
    schematic = db.query(Schematic).filter(Schematic.id == schematic_id).first()

    if not schematic:
        raise HTTPException(404, "Schematic not found")

    # Only owner can update
    if schematic.uploaded_by_user_id != user.id:
        raise HTTPException(403, "Only the uploader can update this schematic")

    if payload.name is not None:
        schematic.name = payload.name
    if payload.description is not None:
        schematic.description = payload.description
    if payload.is_public is not None:
        schematic.is_public = payload.is_public

    db.commit()
    db.refresh(schematic)

    return SchematicOut(
        id=schematic.id,
        structure_id=schematic.structure_id,
        name=schematic.name,
        description=schematic.description,
        file_hash=schematic.file_hash,
        file_size=schematic.file_size,
        original_filename=schematic.original_filename,
        uploaded_by_user_id=schematic.uploaded_by_user_id,
        uploaded_at=schematic.uploaded_at,
        is_public=schematic.is_public,
        has_split_results=len(schematic.split_results) > 0,
    )


@router.delete("/{schematic_id}", status_code=204)
def delete_schematic(
    schematic_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Delete a schematic.
    """
    schematic = db.query(Schematic).filter(Schematic.id == schematic_id).first()

    if not schematic:
        raise HTTPException(404, "Schematic not found")

    # Only owner can delete
    if schematic.uploaded_by_user_id != user.id:
        raise HTTPException(403, "Only the uploader can delete this schematic")

    db.delete(schematic)
    db.commit()

    logger.info(f"Schematic deleted: id={schematic_id}, user={user.id}")


# ============ Split Results Endpoints ============

@router.post("/{schematic_id}/split-results", response_model=SplitResultsBatchOut, status_code=201)
def save_split_results(
    schematic_id: int,
    payload: SplitResultsBatchCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Save KD-Tree split results for a schematic.
    """
    schematic = db.query(Schematic).filter(Schematic.id == schematic_id).first()

    if not schematic:
        raise HTTPException(404, "Schematic not found")

    # Check access
    if schematic.structure_id != user.structure_id:
        raise HTTPException(403, "Access denied")

    # Delete existing split results
    db.query(SchematicSplitResult).filter(
        SchematicSplitResult.schematic_id == schematic_id
    ).delete()

    # Create new split results
    created_count = 0
    for leaf in payload.leaves:
        split_result = SchematicSplitResult(
            schematic_id=schematic_id,
            leaf_index=leaf.leaf_index,
            region_name=leaf.region_name,
            bounds_min_x=leaf.bounds_min_x,
            bounds_min_y=leaf.bounds_min_y,
            bounds_min_z=leaf.bounds_min_z,
            bounds_max_x=leaf.bounds_max_x,
            bounds_max_y=leaf.bounds_max_y,
            bounds_max_z=leaf.bounds_max_z,
            blocks_non_air=leaf.blocks_non_air,
            stacks_needed=leaf.stacks_needed,
            material_counts=leaf.material_counts,
            created_at=datetime.now(timezone.utc),
        )
        db.add(split_result)
        created_count += 1

    db.commit()

    logger.info(f"Split results saved: schematic_id={schematic_id}, leaves={created_count}")

    return SplitResultsBatchOut(
        schematic_id=schematic_id,
        total_created=created_count,
    )


@router.get("/{schematic_id}/split-results", response_model=List[SplitResultOut])
def get_split_results(
    schematic_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get split results for a schematic.
    """
    schematic = db.query(Schematic).filter(Schematic.id == schematic_id).first()

    if not schematic:
        raise HTTPException(404, "Schematic not found")

    # Check access
    if schematic.structure_id != user.structure_id and not schematic.is_public:
        raise HTTPException(403, "Access denied")

    results = db.query(SchematicSplitResult).filter(
        SchematicSplitResult.schematic_id == schematic_id
    ).order_by(SchematicSplitResult.leaf_index).all()

    return results


# ============ Load on Client Endpoint ============

@router.post("/{schematic_id}/load-on-client", response_model=LoadSchematicOnClientResponse)
async def load_schematic_on_client(
    schematic_id: int,
    payload: LoadSchematicOnClientRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("schematics.admin")),
):
    """
    Trigger loading a schematic on a specific client.
    Requires schematics.admin permission.
    """
    schematic = db.query(Schematic).filter(Schematic.id == schematic_id).first()

    if not schematic:
        raise HTTPException(404, "Schematic not found")

    # Check if target user is connected
    ws_manager = WebSocketManager.get_instance()
    if not ws_manager.is_connected(payload.user_id):
        raise HTTPException(400, f"User {payload.user_id} is not connected")

    # Generate request ID
    request_id = str(uuid.uuid4())

    # Send load_schematic message
    message = {
        "type": "load_schematic",
        "schematic_id": str(schematic_id),
        "x": payload.x,
        "y": payload.y,
        "z": payload.z,
        "request_id": request_id,
    }

    success = await ws_manager.send_to_user(payload.user_id, message)

    if not success:
        raise HTTPException(500, "Failed to send load request to client")

    logger.info(f"Load schematic request sent: schematic={schematic_id}, user={payload.user_id}, pos=({payload.x}, {payload.y}, {payload.z})")

    return LoadSchematicOnClientResponse(
        request_id=request_id,
        schematic_id=schematic_id,
        target_user_id=payload.user_id,
        position={"x": payload.x, "y": payload.y, "z": payload.z},
    )

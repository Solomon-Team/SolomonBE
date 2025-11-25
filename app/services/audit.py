# app/services/audit.py
from sqlalchemy.orm import Session
from app.models.auth_audit_log import AuthAuditLog
from typing import Optional, Dict, Any
from fastapi import Request


def log_auth_event(
    db: Session,
    event_type: str,
    user_id: Optional[int] = None,
    mc_uuid: Optional[str] = None,
    request: Optional[Request] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> AuthAuditLog:
    """
    Log an authentication event to the audit log.

    Args:
        db: Database session
        event_type: Type of event (magic_link_request, magic_login, password_set, login_success, login_failed, etc.)
        user_id: User ID (if known)
        mc_uuid: Minecraft UUID (if applicable)
        request: FastAPI request object (to extract IP and user agent)
        metadata: Additional metadata as dict

    Returns:
        AuthAuditLog: The created log entry
    """
    ip_address = None
    user_agent = None

    if request:
        # Extract IP address (handle proxy headers)
        ip_address = request.client.host if request.client else None
        if "x-forwarded-for" in request.headers:
            ip_address = request.headers["x-forwarded-for"].split(",")[0].strip()

        # Extract user agent
        user_agent = request.headers.get("user-agent")

    log_entry = AuthAuditLog(
        user_id=user_id,
        event_type=event_type,
        mc_uuid=mc_uuid,
        ip_address=ip_address,
        user_agent=user_agent,
        event_metadata=metadata or {}
    )

    db.add(log_entry)
    db.flush()  # Get the ID without committing

    return log_entry

# app/services/chest_sync_cleanup.py
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import delete

from app.models.chest_sync import ChestSyncHistory

logger = logging.getLogger("bookkeeper.chest_sync.cleanup")
logger.setLevel(logging.INFO)


def get_ttl_days() -> int:
    """Get TTL in days from environment variable, default to 30"""
    try:
        return int(os.getenv("CHEST_SYNC_HISTORY_TTL_DAYS", "30"))
    except ValueError:
        logger.warning("Invalid CHEST_SYNC_HISTORY_TTL_DAYS, using default 30")
        return 30


def cleanup_old_history(db: Session) -> int:
    """
    Delete chest history records older than TTL.

    Returns:
        Number of records deleted
    """
    ttl_days = get_ttl_days()
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=ttl_days)

    logger.info(f"Starting chest history cleanup (TTL={ttl_days} days, cutoff={cutoff_date})")

    # Delete old records
    result = db.execute(
        delete(ChestSyncHistory).where(
            ChestSyncHistory.recorded_at < cutoff_date
        )
    )

    deleted_count = result.rowcount
    db.commit()

    logger.info(f"Chest history cleanup completed: deleted {deleted_count} records")

    return deleted_count


def run_cleanup_job(db: Session):
    """
    Main entry point for scheduled cleanup job.
    Call this from a cron job or APScheduler.
    """
    try:
        deleted_count = cleanup_old_history(db)
        logger.info(f"Cleanup job completed successfully: {deleted_count} records removed")
    except Exception as e:
        logger.error(f"Cleanup job failed: {e}", exc_info=True)
        raise

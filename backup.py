"""
SQLite backup — nightly snapshot with retention pruning.
Uses sqlite3's online backup API so the live database can be copied safely
without locking out the running app, even while it's open elsewhere.
"""

import os
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backups"
RETENTION_DAYS = 30


def backup_database(app):
    """Copy the live SQLite database to a dated file, then prune old backups."""
    db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "", 1)
    if not os.path.exists(db_path):
        logger.warning(f"Backup skipped — database file not found at {db_path}")
        return

    backup_dir = os.path.join(os.path.dirname(db_path), BACKUP_DIR_NAME)
    os.makedirs(backup_dir, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d")
    dest_path = os.path.join(backup_dir, f"row_tracker_{stamp}.db")
    # Overwrite cleanly rather than backing up into a stale same-day file.
    if os.path.exists(dest_path):
        os.remove(dest_path)

    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(dest_path)
    try:
        with dest:
            source.backup(dest)
        logger.info(f"Database backed up to {dest_path}")
    finally:
        source.close()
        dest.close()

    _prune_old_backups(backup_dir)


def _prune_old_backups(backup_dir):
    """Remove dated backups older than RETENTION_DAYS."""
    cutoff = datetime.now().timestamp() - (RETENTION_DAYS * 86400)
    for name in os.listdir(backup_dir):
        if not (name.startswith("row_tracker_") and name.endswith(".db")):
            continue
        path = os.path.join(backup_dir, name)
        if os.path.getmtime(path) < cutoff:
            os.remove(path)
            logger.info(f"Pruned old backup: {name}")

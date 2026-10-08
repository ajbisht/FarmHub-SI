"""Storage Sync Engine for FarmHub Autonomous Irrigation.

Provides transparent database persistence for Google Cloud Run by mirroring
local SQLite database snapshots to a mounted Google Cloud Storage (GCS) bucket.
"""

import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

from agent.config import config

logger = logging.getLogger("StorageSync")

GCS_MOUNT_PATH = Path(os.getenv("GCS_MOUNT_PATH", "/mnt/data"))
LOCAL_DB_PATH = Path(config.db_path)


class StorageSyncManager:
    """Manages restoring and snapshotting the SQLite database to/from GCS."""

    def __init__(self, mount_dir: Optional[Path] = None, local_db: Optional[Path] = None):
        self.mount_dir = mount_dir or GCS_MOUNT_PATH
        self.local_db = local_db or LOCAL_DB_PATH
        self.gcs_db_file = self.mount_dir / self.local_db.name
        self.running = False
        self._sync_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def is_gcs_mounted(self) -> bool:
        """Returns True if the GCS volume mount is present and accessible."""
        try:
            return self.mount_dir.exists() and self.mount_dir.is_dir()
        except Exception:
            return False

    def restore_from_gcs(self) -> bool:
        """Restores the database from GCS mount into local filesystem on boot."""
        if not self.is_gcs_mounted():
            logger.info(f"GCS mount ({self.mount_dir}) not present. Using standalone local storage: {self.local_db}")
            return False

        with self._lock:
            try:
                if self.gcs_db_file.exists() and self.gcs_db_file.stat().st_size > 0:
                    self.local_db.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(self.gcs_db_file, self.local_db)
                    size_kb = self.local_db.stat().st_size / 1024
                    logger.info(f"SUCCESS: Restored persistent database from GCS ({size_kb:.1f} KB) -> {self.local_db}")
                    return True
                else:
                    logger.info("GCS volume mounted, but no existing database file found. Initializing fresh DB in cloud mount.")
                    return False
            except Exception as e:
                logger.error(f"Error restoring database from GCS mount: {e}")
                return False

    def sync_to_gcs(self) -> bool:
        """Flushes the local SQLite database to the persistent GCS mount."""
        if not self.is_gcs_mounted():
            return False

        if not self.local_db.exists() or self.local_db.stat().st_size == 0:
            return False

        with self._lock:
            try:
                self.mount_dir.mkdir(parents=True, exist_ok=True)
                temp_target = self.mount_dir / f"{self.local_db.name}.tmp"
                # Copy to temporary file then replace to maintain atomic consistency
                shutil.copy2(self.local_db, temp_target)
                temp_target.replace(self.gcs_db_file)
                size_kb = self.gcs_db_file.stat().st_size / 1024
                logger.debug(f"Persisted database snapshot to GCS mount ({size_kb:.1f} KB).")
                return True
            except Exception as e:
                logger.warning(f"Failed to sync database snapshot to GCS: {e}")
                return False

    def start_periodic_sync(self, interval_sec: int = 120):
        """Starts a background daemon thread to sync state every interval_sec seconds."""
        if not self.is_gcs_mounted():
            return

        if self.running:
            return

        self.running = True

        def _worker():
            logger.info(f"Started persistent GCS storage sync worker (interval: {interval_sec}s).")
            while self.running:
                time.sleep(interval_sec)
                if self.running:
                    self.sync_to_gcs()

        self._sync_thread = threading.Thread(target=_worker, name="StorageSyncWorker", daemon=True)
        self._sync_thread.start()

    def stop_sync(self):
        """Stops the sync worker and flushes the final database state to GCS."""
        self.running = False
        if self.is_gcs_mounted():
            logger.info("Flushing final database state to GCS on shutdown...")
            self.sync_to_gcs()


# Global singleton instance
storage_sync = StorageSyncManager()

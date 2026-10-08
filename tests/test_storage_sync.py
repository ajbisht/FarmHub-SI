import pytest
from pathlib import Path
from agent.storage_sync import StorageSyncManager


def test_is_gcs_mounted_false_when_not_exist(tmp_path):
    non_existent = tmp_path / "does_not_exist"
    manager = StorageSyncManager(mount_dir=non_existent)
    assert manager.is_gcs_mounted() is False


def test_is_gcs_mounted_true_when_dir_exists(tmp_path):
    mount_dir = tmp_path / "mock_gcs_mount"
    mount_dir.mkdir()
    manager = StorageSyncManager(mount_dir=mount_dir)
    assert manager.is_gcs_mounted() is True


def test_sync_to_gcs_and_restore(tmp_path):
    mount_dir = tmp_path / "mock_mount"
    mount_dir.mkdir()
    local_db = tmp_path / "test_farm.db"

    # Write mock SQLite content
    local_db.write_text("MOCK_SQLITE_DATABASE_DATA_BYTES")

    manager = StorageSyncManager(mount_dir=mount_dir, local_db=local_db)

    # 1. Sync local to mock GCS
    success = manager.sync_to_gcs()
    assert success is True
    assert (mount_dir / "test_farm.db").exists()
    assert (mount_dir / "test_farm.db").read_text() == "MOCK_SQLITE_DATABASE_DATA_BYTES"

    # 2. Simulate container restart (delete local db)
    local_db.unlink()
    assert not local_db.exists()

    # 3. Restore from mock GCS
    restored = manager.restore_from_gcs()
    assert restored is True
    assert local_db.exists()
    assert local_db.read_text() == "MOCK_SQLITE_DATABASE_DATA_BYTES"


def test_restore_returns_false_when_remote_file_missing(tmp_path):
    mount_dir = tmp_path / "mock_mount_empty"
    mount_dir.mkdir()
    local_db = tmp_path / "test_farm.db"

    manager = StorageSyncManager(mount_dir=mount_dir, local_db=local_db)
    assert manager.restore_from_gcs() is False

from __future__ import annotations

from pathlib import Path

import pytest

from backup_tool.services.backup_service import BackupRequest, BackupService
from backup_tool.mssql.backup import SqlServerConnection
from backup_tool.cloud.rclone import RcloneDestination


class FakeDatabase:
    def __init__(self) -> None:
        self.finished: list[dict] = []

    def start_backup_run(self, **kwargs):
        return 42

    def finish_backup_run(self, run_id, **kwargs):
        self.finished.append({"run_id": run_id, **kwargs})


def test_cloud_verification_failure_marks_run_failed(monkeypatch, tmp_path: Path):
    database = FakeDatabase()
    service = BackupService(database)

    def fake_execute_backup(*, backup_path, **kwargs):
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(b"backup")

    monkeypatch.setattr("backup_tool.services.backup_service.execute_backup", fake_execute_backup)
    monkeypatch.setattr("backup_tool.services.backup_service.copy_file_to_remote", lambda **kwargs: None)

    def fail_verification(**kwargs):
        raise RuntimeError("remote verification failed")

    monkeypatch.setattr("backup_tool.services.backup_service.verify_file_on_remote", fail_verification)

    request = BackupRequest(
        connection=SqlServerConnection(host="server"),
        database_name="ERP",
        backup_type="full",
        local_folder=tmp_path,
        cloud_destination=RcloneDestination(remote="customer", path="Backups"),
    )

    with pytest.raises(RuntimeError, match="remote verification failed"):
        service.run_backup(request)

    assert database.finished == [
        {
            "run_id": 42,
            "status": "failed",
            "error_message": "remote verification failed",
        }
    ]

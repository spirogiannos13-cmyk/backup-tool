from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backup_tool.cloud.rclone import (
    RcloneDestination,
    copy_file_to_remote,
    verify_file_on_remote,
)
from backup_tool.mssql.backup import SqlServerConnection, execute_backup
from backup_tool.storage.database import AppDatabase


@dataclass(frozen=True)
class BackupRequest:
    connection: SqlServerConnection
    database_name: str
    backup_type: str
    local_folder: Path
    job_id: int | None = None
    cloud_destination: RcloneDestination | None = None
    compression: bool = True
    checksum: bool = True


def build_backup_filename(database_name: str, backup_type: str, when: datetime | None = None) -> str:
    timestamp = (when or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    suffix = "trn" if backup_type == "log" else "bak"
    safe_database = "".join(
        character if character.isalnum() or character in ("-", "_") else "_"
        for character in database_name
    )
    return f"{safe_database}_{backup_type}_{timestamp}.{suffix}"


class BackupService:
    def __init__(self, database: AppDatabase) -> None:
        self.database = database

    def run_backup(self, request: BackupRequest) -> Path:
        backup_path = request.local_folder / build_backup_filename(
            request.database_name,
            request.backup_type,
        )
        run_id = self.database.start_backup_run(
            job_id=request.job_id,
            database_name=request.database_name,
            backup_type=request.backup_type,
            local_path=str(backup_path),
            cloud_path=request.cloud_destination.as_rclone_path()
            if request.cloud_destination
            else None,
        )

        try:
            execute_backup(
                connection_profile=request.connection,
                database_name=request.database_name,
                backup_path=backup_path,
                backup_type=request.backup_type,
                compression=request.compression,
                checksum=request.checksum,
            )

            if not backup_path.is_file():
                raise FileNotFoundError(
                    f"SQL Server backup completed but the backup file was not found: {backup_path}"
                )

            if request.cloud_destination:
                copy_file_to_remote(
                    source_file=backup_path,
                    destination=request.cloud_destination,
                )
                verify_file_on_remote(
                    source_file=backup_path,
                    destination=request.cloud_destination,
                )

            self.database.finish_backup_run(
                run_id,
                status="success",
                bytes_written=backup_path.stat().st_size,
            )
        except Exception as exc:
            self.database.finish_backup_run(run_id, status="failed", error_message=str(exc))
            raise

        return backup_path

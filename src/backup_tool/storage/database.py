from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import sqlite3


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sql_servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        host TEXT NOT NULL,
        instance TEXT,
        port INTEGER,
        auth_mode TEXT NOT NULL CHECK (auth_mode IN ('windows', 'sql')),
        username TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cloud_destinations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        provider TEXT NOT NULL,
        rclone_remote TEXT NOT NULL,
        remote_path TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backup_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        server_id INTEGER NOT NULL REFERENCES sql_servers(id),
        database_name TEXT NOT NULL,
        backup_type TEXT NOT NULL CHECK (backup_type IN ('full', 'differential', 'log')),
        local_folder TEXT NOT NULL,
        cloud_destination_id INTEGER REFERENCES cloud_destinations(id),
        retention_days INTEGER NOT NULL DEFAULT 14,
        compression_enabled INTEGER NOT NULL DEFAULT 1,
        checksum_enabled INTEGER NOT NULL DEFAULT 1,
        enabled INTEGER NOT NULL DEFAULT 1,
        schedule_notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backup_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER REFERENCES backup_jobs(id),
        database_name TEXT NOT NULL,
        backup_type TEXT NOT NULL CHECK (backup_type IN ('full', 'differential', 'log')),
        local_path TEXT,
        cloud_path TEXT,
        status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'success', 'failed')),
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT,
        bytes_written INTEGER,
        error_message TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_backup_runs_started_at ON backup_runs(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_backup_runs_status ON backup_runs(status)",
    "CREATE INDEX IF NOT EXISTS idx_backup_jobs_enabled ON backup_jobs(enabled)",
)


@dataclass(frozen=True)
class DashboardSummary:
    job_count: int
    destination_count: int
    successful_runs: int
    failed_runs: int


@dataclass(frozen=True)
class CloudDestinationRecord:
    id: int
    name: str
    provider: str
    rclone_remote: str
    remote_path: str
    enabled: bool


@dataclass(frozen=True)
class BackupJobRecord:
    id: int
    name: str
    server_name: str
    server_host: str
    database_name: str
    backup_type: str
    local_folder: str
    cloud_destination_name: str | None
    enabled: bool


class AppDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.commit()

    def execute_many(self, statements: Iterable[str]) -> None:
        with self.connect() as connection:
            for statement in statements:
                connection.execute(statement)
            connection.commit()

    def dashboard_summary(self) -> DashboardSummary:
        with self.connect() as connection:
            job_count = connection.execute("SELECT COUNT(*) FROM backup_jobs").fetchone()[0]
            destination_count = connection.execute(
                "SELECT COUNT(*) FROM cloud_destinations WHERE enabled = 1"
            ).fetchone()[0]
            successful_runs = connection.execute(
                "SELECT COUNT(*) FROM backup_runs WHERE status = 'success'"
            ).fetchone()[0]
            failed_runs = connection.execute(
                "SELECT COUNT(*) FROM backup_runs WHERE status = 'failed'"
            ).fetchone()[0]

        return DashboardSummary(
            job_count=job_count,
            destination_count=destination_count,
            successful_runs=successful_runs,
            failed_runs=failed_runs,
        )

    def add_cloud_destination(
        self,
        *,
        name: str,
        provider: str,
        rclone_remote: str,
        remote_path: str,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO cloud_destinations (name, provider, rclone_remote, remote_path)
                VALUES (?, ?, ?, ?)
                """,
                (name, provider, rclone_remote, remote_path),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def upsert_cloud_destination(
        self,
        *,
        name: str,
        provider: str,
        rclone_remote: str,
        remote_path: str,
    ) -> int:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO cloud_destinations (
                    name, provider, rclone_remote, remote_path, enabled
                )
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(name) DO UPDATE SET
                    provider = excluded.provider,
                    rclone_remote = excluded.rclone_remote,
                    remote_path = excluded.remote_path,
                    enabled = 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, provider, rclone_remote, remote_path),
            )
            row = connection.execute(
                "SELECT id FROM cloud_destinations WHERE name = ?",
                (name,),
            ).fetchone()
            connection.commit()
            return int(row["id"])

    def list_cloud_destinations(self) -> list[CloudDestinationRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, provider, rclone_remote, remote_path, enabled
                FROM cloud_destinations
                ORDER BY name
                """
            ).fetchall()

        return [
            CloudDestinationRecord(
                id=int(row["id"]),
                name=str(row["name"]),
                provider=str(row["provider"]),
                rclone_remote=str(row["rclone_remote"]),
                remote_path=str(row["remote_path"]),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def add_sql_server(
        self,
        *,
        name: str,
        host: str,
        auth_mode: str,
        instance: str | None = None,
        port: int | None = None,
        username: str | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sql_servers (name, host, instance, port, auth_mode, username)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, host, instance, port, auth_mode, username),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def add_backup_job(
        self,
        *,
        name: str,
        server_id: int,
        database_name: str,
        backup_type: str,
        local_folder: str,
        cloud_destination_id: int | None,
        retention_days: int,
        compression_enabled: bool,
        checksum_enabled: bool,
        schedule_notes: str | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO backup_jobs (
                    name, server_id, database_name, backup_type, local_folder,
                    cloud_destination_id, retention_days, compression_enabled,
                    checksum_enabled, schedule_notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    server_id,
                    database_name,
                    backup_type,
                    local_folder,
                    cloud_destination_id,
                    retention_days,
                    int(compression_enabled),
                    int(checksum_enabled),
                    schedule_notes,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_backup_jobs(self) -> list[BackupJobRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    backup_jobs.id,
                    backup_jobs.name,
                    sql_servers.name AS server_name,
                    sql_servers.host AS server_host,
                    backup_jobs.database_name,
                    backup_jobs.backup_type,
                    backup_jobs.local_folder,
                    cloud_destinations.name AS cloud_destination_name,
                    backup_jobs.enabled
                FROM backup_jobs
                JOIN sql_servers ON sql_servers.id = backup_jobs.server_id
                LEFT JOIN cloud_destinations
                    ON cloud_destinations.id = backup_jobs.cloud_destination_id
                ORDER BY backup_jobs.created_at DESC, backup_jobs.id DESC
                """
            ).fetchall()

        return [
            BackupJobRecord(
                id=int(row["id"]),
                name=str(row["name"]),
                server_name=str(row["server_name"]),
                server_host=str(row["server_host"]),
                database_name=str(row["database_name"]),
                backup_type=str(row["backup_type"]),
                local_folder=str(row["local_folder"]),
                cloud_destination_name=(
                    str(row["cloud_destination_name"])
                    if row["cloud_destination_name"] is not None
                    else None
                ),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def start_backup_run(
        self,
        *,
        job_id: int | None,
        database_name: str,
        backup_type: str,
        local_path: str | None,
        cloud_path: str | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO backup_runs (
                    job_id, database_name, backup_type, local_path, cloud_path, status
                )
                VALUES (?, ?, ?, ?, ?, 'running')
                """,
                (job_id, database_name, backup_type, local_path, cloud_path),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def finish_backup_run(
        self,
        run_id: int,
        *,
        status: str,
        bytes_written: int | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE backup_runs
                SET status = ?, finished_at = CURRENT_TIMESTAMP, bytes_written = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (status, bytes_written, error_message, run_id),
            )
            connection.commit()

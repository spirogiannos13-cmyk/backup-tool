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
        database_name TEXT,
        udl_path TEXT,
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
class SqlServerRecord:
    id: int
    name: str
    host: str
    instance: str | None
    port: int | None
    auth_mode: str
    username: str | None
    database_name: str | None
    udl_path: str | None

    @property
    def server_address(self) -> str:
        if self.instance:
            return f"{self.host}\\{self.instance}"

        if self.port:
            return f"{self.host},{self.port}"

        return self.host

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
    retention_days: int
    compression_enabled: bool
    checksum_enabled: bool
    enabled: bool

@dataclass(frozen=True)
class BackupRunRecord:
    id: int
    job_id: int | None
    job_name: str | None
    database_name: str
    backup_type: str
    local_path: str | None
    cloud_path: str | None
    status: str
    started_at: str
    finished_at: str | None
    bytes_written: int | None
    error_message: str | None

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

            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(sql_servers)"
                ).fetchall()
            }

            if "database_name" not in columns:
                connection.execute(
                    "ALTER TABLE sql_servers ADD COLUMN database_name TEXT"
                )

            if "udl_path" not in columns:
                connection.execute(
                    "ALTER TABLE sql_servers ADD COLUMN udl_path TEXT"
                )


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
            existing = connection.execute(
                """
                SELECT id
                FROM cloud_destinations
                WHERE name = ?
                """,
                (name,),
            ).fetchone()

            if existing is not None:
                destination_id = existing[0]

                connection.execute(
                    """
                    UPDATE cloud_destinations
                    SET
                        provider = ?,
                        rclone_remote = ?,
                        remote_path = ?,
                        enabled = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        provider,
                        rclone_remote,
                        remote_path,
                        destination_id,
                    ),
                )
                connection.commit()
                return destination_id

            cursor = connection.execute(
                """
                INSERT INTO cloud_destinations (
                    name,
                    provider,
                    rclone_remote,
                    remote_path,
                    enabled
                )
                VALUES (?, ?, ?, ?, 1)
                """,
                (
                    name,
                    provider,
                    rclone_remote,
                    remote_path,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def update_cloud_destination(
        self,
        *,
        destination_id: int,
        name: str,
        provider: str,
        rclone_remote: str,
        remote_path: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE cloud_destinations
                SET
                    name = ?,
                    provider = ?,
                    rclone_remote = ?,
                    remote_path = ?,
                    enabled = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    name,
                    provider,
                    rclone_remote,
                    remote_path,
                    destination_id,
                ),
            )
            connection.commit()

    def list_cloud_destinations(self) -> list[CloudDestinationRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    provider,
                    rclone_remote,
                    remote_path,
                    enabled
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
        database_name: str | None = None,
        udl_path: str | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sql_servers (
                    name,
                    host,
                    instance,
                    port,
                    auth_mode,
                    username,
                    database_name,
                    udl_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    host,
                    instance,
                    port,
                    auth_mode,
                    username,
                    database_name,
                    udl_path,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def update_sql_server(
        self,
        *,
        server_id: int,
        name: str,
        host: str,
        auth_mode: str,
        instance: str | None = None,
        port: int | None = None,
        username: str | None = None,
        database_name: str | None = None,
        udl_path: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE sql_servers
                SET
                    name = ?,
                    host = ?,
                    instance = ?,
                    port = ?,
                    auth_mode = ?,
                    username = ?,
                    database_name = ?,
                    udl_path = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    name,
                    host,
                    instance,
                    port,
                    auth_mode,
                    username,
                    database_name,
                    udl_path,
                    server_id,
                ),
            )
            connection.commit()

    def list_sql_servers(self) -> list[SqlServerRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    host,
                    instance,
                    port,
                    auth_mode,
                    username,
                    database_name,
                    udl_path
                FROM sql_servers
                ORDER BY name
                """
            ).fetchall()
        return [
            SqlServerRecord(
                id=int(row["id"]),
                name=str(row["name"]),
                host=str(row["host"]),
                instance=str(row["instance"]) if row["instance"] is not None else None,
                port=int(row["port"]) if row["port"] is not None else None,
                auth_mode=str(row["auth_mode"]),
                username=str(row["username"]) if row["username"] is not None else None,
                database_name=(
                    str(row["database_name"])
                    if row["database_name"] is not None
                    else None
                ),
                udl_path=(
                    str(row["udl_path"])
                    if row["udl_path"] is not None
                    else None
                ),
            )
            for row in rows
        ]

    def delete_sql_server(self, server_id: int) -> None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM backup_jobs
                WHERE server_id = ?
                """,
                (server_id,),
            ).fetchone()

            job_count = int(row[0]) if row else 0

            if job_count > 0:
                raise ValueError(
                    "This SQL Server is used by one or more Backup Jobs. "
                    "Delete those Backup Jobs first."
                )

            connection.execute(
                "DELETE FROM sql_servers WHERE id = ?",
                (server_id,),
            )
            connection.commit()

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
    def update_backup_job(
        self,
        *,
        job_id: int,
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
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE backup_jobs
                SET
                    name = ?,
                    server_id = ?,
                    database_name = ?,
                    backup_type = ?,
                    local_folder = ?,
                    cloud_destination_id = ?,
                    retention_days = ?,
                    compression_enabled = ?,
                    checksum_enabled = ?,
                    schedule_notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
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
                    job_id,
                ),
            )
            connection.commit()

    def delete_backup_job(self, job_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM backup_runs WHERE job_id = ?",
                (job_id,),
            )
            connection.execute(
                "DELETE FROM backup_jobs WHERE id = ?",
                (job_id,),
            )
            connection.commit()

    def delete_cloud_destination(self, destination_id: int) -> None:
        with self.connect() as connection:
            usage_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM backup_jobs
                WHERE cloud_destination_id = ?
                """,
                (destination_id,),
            ).fetchone()[0]

            if usage_count:
                raise ValueError(
                    "This cloud destination is used by one or more backup jobs."
                )

            connection.execute(
                "DELETE FROM cloud_destinations WHERE id = ?",
                (destination_id,),
            )
            connection.commit()


    def list_backup_jobs(self) -> list[BackupJobRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    retention_days,
                    compression_enabled,
                    checksum_enabled,
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
                retention_days=int(row["retention_days"]),
                compression_enabled=bool(row["compression_enabled"]),
                checksum_enabled=bool(row["checksum_enabled"]),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def list_backup_runs(self) -> list[BackupRunRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    backup_runs.id,
                    backup_runs.job_id,
                    backup_jobs.name AS job_name,
                    backup_runs.database_name,
                    backup_runs.backup_type,
                    backup_runs.local_path,
                    backup_runs.cloud_path,
                    backup_runs.status,
                    backup_runs.started_at,
                    backup_runs.finished_at,
                    backup_runs.bytes_written,
                    backup_runs.error_message
                FROM backup_runs
                LEFT JOIN backup_jobs
                    ON backup_jobs.id = backup_runs.job_id
                ORDER BY backup_runs.started_at DESC, backup_runs.id DESC
                """
            ).fetchall()

        return [
            BackupRunRecord(
                id=int(row["id"]),
                job_id=(
                    int(row["job_id"])
                    if row["job_id"] is not None
                    else None
                ),
                job_name=(
                    str(row["job_name"])
                    if row["job_name"] is not None
                    else None
                ),
                database_name=str(row["database_name"]),
                backup_type=str(row["backup_type"]),
                local_path=(
                    str(row["local_path"])
                    if row["local_path"] is not None
                    else None
                ),
                cloud_path=(
                    str(row["cloud_path"])
                    if row["cloud_path"] is not None
                    else None
                ),
                status=str(row["status"]),
                started_at=str(row["started_at"]),
                finished_at=(
                    str(row["finished_at"])
                    if row["finished_at"] is not None
                    else None
                ),
                bytes_written=(
                    int(row["bytes_written"])
                    if row["bytes_written"] is not None
                    else None
                ),
                error_message=(
                    str(row["error_message"])
                    if row["error_message"] is not None
                    else None
                ),
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

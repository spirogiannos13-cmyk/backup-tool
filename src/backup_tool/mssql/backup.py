from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


BACKUP_TYPES = {"full", "differential", "log"}


@dataclass(frozen=True)
class SqlServerConnection:
    host: str
    database: str = "master"
    instance: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    trust_server_certificate: bool = True
    driver: str = "ODBC Driver 18 for SQL Server"

    @property
    def uses_windows_auth(self) -> bool:
        return not self.username

    def server_address(self) -> str:
        if self.instance:
            return f"{self.host}\\{self.instance}"
        if self.port:
            return f"{self.host},{self.port}"
        return self.host

    def to_odbc_connection_string(self) -> str:
        parts = [
            f"DRIVER={{{self.driver}}}",
            f"SERVER={self.server_address()}",
            f"DATABASE={self.database}",
            "Encrypt=yes",
            f"TrustServerCertificate={'yes' if self.trust_server_certificate else 'no'}",
        ]

        if self.uses_windows_auth:
            parts.append("Trusted_Connection=yes")
        else:
            parts.extend([f"UID={self.username}", f"PWD={self.password or ''}"])

        return ";".join(parts) + ";"


def quote_identifier(identifier: str) -> str:
    if not identifier or not identifier.strip():
        raise ValueError("SQL identifier cannot be empty.")
    return "[" + identifier.replace("]", "]]") + "]"


def escape_sql_string(value: str) -> str:
    return value.replace("'", "''")


def build_backup_sql(
    *,
    database_name: str,
    backup_path: Path,
    backup_type: str,
    compression: bool = True,
    checksum: bool = True,
) -> str:
    normalized_type = backup_type.lower()
    if normalized_type not in BACKUP_TYPES:
        raise ValueError(f"Unsupported backup type: {backup_type}")

    backup_target = f"DISK = N'{escape_sql_string(str(backup_path))}'"
    options = ["INIT", "STATS = 10"]

    if compression:
        options.append("COMPRESSION")
    if checksum:
        options.append("CHECKSUM")

    if normalized_type == "log":
        command = f"BACKUP LOG {quote_identifier(database_name)} TO {backup_target}"
    else:
        command = f"BACKUP DATABASE {quote_identifier(database_name)} TO {backup_target}"
        if normalized_type == "differential":
            options.append("DIFFERENTIAL")

    return f"{command} WITH {', '.join(options)};"


def execute_backup(
    *,
    connection_profile: SqlServerConnection,
    database_name: str,
    backup_path: Path,
    backup_type: str,
    compression: bool = True,
    checksum: bool = True,
) -> None:
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError("pyodbc is required to run SQL Server backups.") from exc

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    sql = build_backup_sql(
        database_name=database_name,
        backup_path=backup_path,
        backup_type=backup_type,
        compression=compression,
        checksum=checksum,
    )

    with pyodbc.connect(connection_profile.to_odbc_connection_string(), autocommit=True) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        while cursor.nextset():
            pass

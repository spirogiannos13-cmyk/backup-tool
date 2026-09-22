from __future__ import annotations

from backup_tool.mssql.backup import SqlServerConnection


def list_databases(connection_profile: SqlServerConnection) -> list[str]:
    import pyodbc

    connection_string = connection_profile.to_odbc_connection_string()
    with pyodbc.connect(connection_string, timeout=5) as connection:
        rows = connection.execute(
            "SELECT name FROM sys.databases WHERE state_desc = 'ONLINE' ORDER BY name"
        ).fetchall()
    return [str(row[0]) for row in rows]

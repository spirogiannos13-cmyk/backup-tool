from __future__ import annotations

from pathlib import Path

import pytest

from backup_tool.mssql.backup import build_backup_sql, quote_identifier


def test_quote_identifier_escapes_closing_brackets():
    assert quote_identifier("ERP]Archive") == "[ERP]]Archive]"


def test_build_full_backup_sql():
    sql = build_backup_sql(
        database_name="ERP",
        backup_path=Path("C:/Backups/ERP_full.bak"),
        backup_type="full",
    )

    assert "BACKUP DATABASE [ERP]" in sql
    assert "TO DISK = N'C:\\Backups\\ERP_full.bak'" in sql
    assert "COMPRESSION" in sql
    assert "CHECKSUM" in sql
    assert "DIFFERENTIAL" not in sql


def test_build_differential_backup_sql():
    sql = build_backup_sql(
        database_name="ERP",
        backup_path=Path("C:/Backups/ERP_diff.bak"),
        backup_type="differential",
    )

    assert "BACKUP DATABASE [ERP]" in sql
    assert "DIFFERENTIAL" in sql


def test_build_log_backup_sql():
    sql = build_backup_sql(
        database_name="ERP",
        backup_path=Path("C:/Backups/ERP_log.trn"),
        backup_type="log",
    )

    assert "BACKUP LOG [ERP]" in sql


def test_invalid_backup_type_raises():
    with pytest.raises(ValueError):
        build_backup_sql(
            database_name="ERP",
            backup_path=Path("C:/Backups/ERP.bak"),
            backup_type="copy_only",
        )

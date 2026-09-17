from __future__ import annotations

from pathlib import Path

from backup_tool.cloud.rclone import (
    RcloneDestination,
    build_copy_command,
    verify_file_on_remote,
)


def test_destination_formats_rclone_path():
    destination = RcloneDestination(remote="customer_drive", path="SQLBackups/ClientA")

    assert destination.as_rclone_path() == "customer_drive:SQLBackups/ClientA"


def test_destination_formats_file_at_remote_root():
    destination = RcloneDestination(remote="customer_drive", path="")

    assert destination.file_path("ERP_full.bak") == "customer_drive:ERP_full.bak"


def test_build_copy_command_uses_copyto():
    command = build_copy_command(
        source_file=Path("C:/Backups/ERP_full.bak"),
        destination=RcloneDestination(remote="mega_customer", path="Backups"),
        rclone_binary="rclone",
    )

    assert command[:2] == ["rclone", "copyto"]
    assert command[2] == "C:\\Backups\\ERP_full.bak"
    assert command[3] == "mega_customer:Backups/ERP_full.bak"


def test_verify_file_on_remote_runs_rclone_check(monkeypatch, tmp_path):
    source = tmp_path / "ERP_full.bak"
    source.write_bytes(b"backup")
    calls = []

    monkeypatch.setattr(
        "backup_tool.cloud.rclone.find_rclone",
        lambda: "rclone.exe",
    )

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return object()

    monkeypatch.setattr("backup_tool.cloud.rclone.subprocess.run", fake_run)

    result = verify_file_on_remote(
        source_file=source,
        destination=RcloneDestination(remote="customer_drive", path="Backups"),
        timeout_seconds=120,
    )

    assert result is not None
    assert calls[0][0] == [
        "rclone.exe",
        "check",
        str(source),
        "customer_drive:Backups/ERP_full.bak",
        "--one-way",
    ]
    assert calls[0][1]["check"] is True
    assert calls[0][1]["timeout"] == 120


def test_verify_file_on_remote_requires_local_file(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backup_tool.cloud.rclone.find_rclone",
        lambda: "rclone.exe",
    )

    missing = tmp_path / "missing.bak"

    import pytest

    with pytest.raises(FileNotFoundError):
        verify_file_on_remote(
            source_file=missing,
            destination=RcloneDestination(remote="customer_drive", path="Backups"),
        )

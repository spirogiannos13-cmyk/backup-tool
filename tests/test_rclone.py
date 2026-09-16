from __future__ import annotations

from pathlib import Path

from backup_tool.cloud.rclone import RcloneDestination, build_copy_command


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

from __future__ import annotations

from backup_tool.storage.database import AppDatabase


def test_database_initializes_and_summarizes(tmp_path):
    database = AppDatabase(tmp_path / "app.db")
    database.initialize()

    summary = database.dashboard_summary()

    assert summary.job_count == 0
    assert summary.destination_count == 0
    assert summary.successful_runs == 0
    assert summary.failed_runs == 0


def test_database_tracks_cloud_destinations_and_runs(tmp_path):
    database = AppDatabase(tmp_path / "app.db")
    database.initialize()

    destination_id = database.add_cloud_destination(
        name="Customer Google Drive",
        provider="drive",
        rclone_remote="customer_drive",
        remote_path="SQLBackups/Customer",
    )
    run_id = database.start_backup_run(
        job_id=None,
        database_name="ERP",
        backup_type="full",
        local_path="C:/Backups/ERP_full.bak",
    )
    database.finish_backup_run(run_id, status="success", bytes_written=128)

    summary = database.dashboard_summary()

    assert destination_id == 1
    assert summary.destination_count == 1
    assert summary.successful_runs == 1
    assert summary.failed_runs == 0

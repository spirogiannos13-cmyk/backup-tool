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


def test_database_creates_backup_job_configuration(tmp_path):
    database = AppDatabase(tmp_path / "app.db")
    database.initialize()

    server_id = database.add_sql_server(
        name="Customer SQL",
        host="sql01",
        instance="MSSQLSERVER",
        port=None,
        auth_mode="windows",
    )
    destination_id = database.upsert_cloud_destination(
        name="Customer MEGA",
        provider="mega",
        rclone_remote="customer_mega",
        remote_path="SQLBackups/Customer",
    )
    job_id = database.add_backup_job(
        name="ERP full backup",
        server_id=server_id,
        database_name="ERP",
        backup_type="full",
        local_folder="C:/SQLBackups",
        cloud_destination_id=destination_id,
        retention_days=14,
        compression_enabled=True,
        checksum_enabled=True,
    )

    jobs = database.list_backup_jobs()
    destinations = database.list_cloud_destinations()
    summary = database.dashboard_summary()

    assert job_id == 1
    assert len(jobs) == 1
    assert jobs[0].name == "ERP full backup"
    assert jobs[0].database_name == "ERP"
    assert jobs[0].cloud_destination_name == "Customer MEGA"
    assert len(destinations) == 1
    assert destinations[0].provider == "mega"
    assert summary.job_count == 1
    assert summary.destination_count == 1


def test_database_upserts_cloud_destination_by_name(tmp_path):
    database = AppDatabase(tmp_path / "app.db")
    database.initialize()

    first_id = database.upsert_cloud_destination(
        name="Customer Drive",
        provider="drive",
        rclone_remote="old_drive",
        remote_path="Old",
    )
    second_id = database.upsert_cloud_destination(
        name="Customer Drive",
        provider="drive",
        rclone_remote="new_drive",
        remote_path="New",
    )

    destinations = database.list_cloud_destinations()

    assert first_id == second_id
    assert len(destinations) == 1
    assert destinations[0].rclone_remote == "new_drive"
    assert destinations[0].remote_path == "New"

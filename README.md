# Backup Tool

Python desktop application for backing up Microsoft SQL Server databases and
uploading the generated backup files to customer-owned cloud storage.

## What It Will Do

- Connect to Microsoft SQL Server instances.
- Create native MSSQL backups:
  - Full backups (`.bak`)
  - Differential backups (`.bak`)
  - Transaction log backups (`.trn`)
- Store backup history, jobs, cloud destinations, and run status locally.
- Upload finished backup files to cloud storage through rclone.
- Support providers such as Google Drive, MEGA, OneDrive, Dropbox, S3,
  FTP/SFTP, WebDAV, local folders, and NAS paths.

## Architecture

```text
MSSQL Server
    -> native local backup file
    -> optional cloud upload via rclone
    -> local app history in SQLite
    -> raw logs on disk
```

SQLite is only used by the application for settings/history. The databases being
backed up are Microsoft SQL Server databases.

## First Development Setup

Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run tests:

```powershell
python -m pytest
```

Launch the UI:

```powershell
backup-tool
```

or:

```powershell
python -m backup_tool
```

## External Requirements

- Microsoft SQL Server ODBC Driver for Python SQL connections.
- `rclone` installed and configured on the customer machine.
- A local folder where the SQL Server service account can write backup files.

## Cloud Setup

Cloud accounts are configured with rclone:

```powershell
rclone config
```

The app stores only the rclone remote name and destination path, for example:

```text
customer_drive:SQLBackups/CustomerName/ServerName
```

Cloud passwords and OAuth tokens stay in rclone's config, not in this app's
SQLite database.

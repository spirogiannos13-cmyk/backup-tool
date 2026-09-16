# Project Instructions

This project is a Python desktop application for backing up customer Microsoft
SQL Server databases and uploading the generated backup files to customer-owned
cloud storage.

## Product Direction

- Build a modern Windows-friendly desktop UI.
- Use Python 3.12+.
- Use PySide6 for the desktop interface.
- Use Microsoft SQL Server native backup commands for MSSQL databases.
- Use rclone for cloud providers such as Google Drive, MEGA, OneDrive,
  Dropbox, S3-compatible storage, FTP/SFTP, WebDAV, and local/NAS folders.
- Keep cloud credentials outside the app database. Let rclone manage provider
  authentication and tokens.
- Use local SQLite only as the application's control database for jobs,
  destinations, backup runs, and history.
- Use TOML config files for simple editable app settings.
- Use plain log files for detailed runtime logs.

## Safety Rules

- Never copy raw MSSQL `.mdf` or `.ldf` files as the primary backup method.
- Prefer `BACKUP DATABASE` and `BACKUP LOG` commands.
- Do not store SQL passwords, cloud tokens, or API keys in source control.
- Do not commit generated backup files, logs, local databases, or `.env` files.
- Use unique timestamped backup filenames.
- Assume customer machines may have slow or unstable internet connections.
  Always finish the local backup before cloud upload.

## Engineering Rules

- Keep modules small and testable.
- Keep UI code separate from backup/cloud/database logic.
- Add tests for SQL command generation, database schema initialization, and
  cloud command construction.
- Prefer subprocess calls with argument lists instead of shell strings.
- Keep changes focused and commit-ready.

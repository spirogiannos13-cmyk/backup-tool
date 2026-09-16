from __future__ import annotations

import argparse
import sys

from backup_tool.config import get_app_paths
from backup_tool.storage.database import AppDatabase


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backup-tool",
        description="MSSQL backup manager with multi-cloud uploads.",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize the local application database and exit.",
    )
    args = parser.parse_args(argv)

    paths = get_app_paths()
    paths.ensure()
    database = AppDatabase(paths.database_path)
    database.initialize()

    if args.init_db:
        print(f"Initialized app database: {paths.database_path}")
        return 0

    try:
        from backup_tool.ui.main_window import run_app
    except ImportError as exc:
        print("PySide6 is required to launch the desktop UI.")
        print("Install dependencies with: python -m pip install -e \".[dev]\"")
        print(f"Import error: {exc}")
        return 2

    return run_app(database)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

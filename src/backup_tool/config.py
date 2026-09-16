from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


APP_DIR_NAME = "BackupTool"


@dataclass(frozen=True)
class AppPaths:
    root: Path
    data_dir: Path
    log_dir: Path
    config_path: Path
    database_path: Path

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


def get_app_paths(base_dir: Path | None = None) -> AppPaths:
    root = base_dir or Path.cwd()
    data_dir = root / "data"
    log_dir = root / "logs"
    return AppPaths(
        root=root,
        data_dir=data_dir,
        log_dir=log_dir,
        config_path=root / "settings.toml",
        database_path=data_dir / "backup_tool.db",
    )


def load_settings(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}

    with path.open("rb") as file:
        return tomllib.load(file)

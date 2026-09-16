from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path


def configure_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"backup-tool-{datetime.now(UTC):%Y%m%d}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return log_path

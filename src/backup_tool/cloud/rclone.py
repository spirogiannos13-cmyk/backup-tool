from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class RcloneDestination:
    remote: str
    path: str

    def as_rclone_path(self) -> str:
        clean_path = self.path.strip().strip("/")
        if clean_path:
            return f"{self.remote}:{clean_path}"
        return f"{self.remote}:"

    def file_path(self, filename: str) -> str:
        clean_path = self.path.strip().strip("/")
        if clean_path:
            return f"{self.remote}:{clean_path}/{filename}"
        return f"{self.remote}:{filename}"


def find_rclone() -> str | None:
    return shutil.which("rclone")


def build_copy_command(
    *,
    source_file: Path,
    destination: RcloneDestination,
    rclone_binary: str = "rclone",
) -> list[str]:
    return [
        rclone_binary,
        "copyto",
        str(source_file),
        destination.file_path(source_file.name),
        "--progress",
        "--transfers",
        "1",
        "--checkers",
        "4",
    ]


def copy_file_to_remote(
    *,
    source_file: Path,
    destination: RcloneDestination,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    rclone_binary = find_rclone()
    if not rclone_binary:
        raise RuntimeError("rclone was not found on PATH.")

    command = build_copy_command(
        source_file=source_file,
        destination=destination,
        rclone_binary=rclone_binary,
    )
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )


def verify_file_on_remote(
    *,
    source_file: Path,
    destination: RcloneDestination,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Verify that the remote copy matches the local file.

    rclone check compares size and hashes when the remote provides a
    compatible hash. For remotes without hash support, rclone falls back
    to the checks it can perform (including size), and returns non-zero if
    the objects do not match or the check cannot be completed.
    """
    rclone_binary = find_rclone()
    if not rclone_binary:
        raise RuntimeError("rclone was not found on PATH.")

    if not source_file.is_file():
        raise FileNotFoundError(f"Backup file was not found: {source_file}")

    command = [
        rclone_binary,
        "check",
        str(source_file),
        destination.file_path(source_file.name),
        "--one-way",
    ]
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )


def list_remotes() -> list[str]:
    rclone_binary = find_rclone()
    if not rclone_binary:
        return []

    result = subprocess.run(
        [rclone_binary, "listremotes"],
        check=True,
        text=True,
        capture_output=True,
    )
    return [line.rstrip(":") for line in result.stdout.splitlines() if line.strip()]

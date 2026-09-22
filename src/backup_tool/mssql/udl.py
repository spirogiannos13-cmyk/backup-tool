from __future__ import annotations

from pathlib import Path


def parse_udl(path: Path) -> dict[str, str]:
    """Read an OLE DB UDL file and return its connection-string properties.

    The parser intentionally treats the UDL as configuration input only.
    It does not retain the original file contents.
    """
    text = path.read_text(encoding="utf-16", errors="replace")
    connection = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[oledb]") or not stripped:
            continue
        if stripped.startswith("Provider=") or "=" in stripped:
            connection += stripped

    properties: dict[str, str] = {}
    for part in connection.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        properties[key.strip().lower()] = value.strip()

    return properties


def udl_to_fields(path: Path) -> dict[str, str | None]:
    props = parse_udl(path)
    return {
        "provider": props.get("provider"),
        "host": props.get("data source") or props.get("server"),
        "database": props.get("initial catalog") or props.get("database"),
        "username": props.get("user id") or props.get("uid"),
        "password": props.get("password") or props.get("pwd"),
    }

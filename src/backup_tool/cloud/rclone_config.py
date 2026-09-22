from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess

from backup_tool.cloud.rclone import find_rclone


@dataclass(frozen=True)
class RcloneConfigOption:
    name: str
    help: str
    default: object | None
    value: object | None
    examples: tuple[dict[str, object], ...]
    required: bool
    is_password: bool
    exclusive: bool
    value_type: str
    field_name: str
    hide: int
    advanced: bool
    sensitive: bool
    default_str: str
    value_str: str
    no_prefix: bool


@dataclass(frozen=True)
class RcloneConfigResponse:
    state: str
    option: RcloneConfigOption | None
    error: str
    result: str


def _parse_option(data: dict[str, object]) -> RcloneConfigOption:
    examples = tuple(
        example
        for example in data.get("Examples", [])
        if isinstance(example, dict)
    )

    return RcloneConfigOption(
        name=str(data.get("Name", "")),
        help=str(data.get("Help", "")),
        default=data.get("Default"),
        value=data.get("Value"),
        examples=examples,
        required=bool(data.get("Required", False)),
        is_password=bool(data.get("IsPassword", False)),
        exclusive=bool(data.get("Exclusive", False)),
        value_type=str(data.get("Type", "string")),
        field_name=str(data.get("FieldName", "")),
        hide=int(data.get("Hide", 0) or 0),
        advanced=bool(data.get("Advanced", False)),
        sensitive=bool(data.get("Sensitive", False)),
        default_str=str(data.get("DefaultStr", "")),
        value_str=str(data.get("ValueStr", "")),
        no_prefix=bool(data.get("NoPrefix", False)),
    )


def _parse_response(stdout: str) -> RcloneConfigResponse:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"rclone returned invalid JSON: {stdout}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError("rclone returned an unexpected response.")

    option_data = payload.get("Option")
    option = (
        _parse_option(option_data)
        if isinstance(option_data, dict)
        else None
    )

    return RcloneConfigResponse(
        state=str(payload.get("State", "")),
        option=option,
        error=str(payload.get("Error", "")),
        result=str(payload.get("Result", "")),
    )


def _run_config_command(
    command: list[str],
    *,
    timeout_seconds: int | None = None,
) -> RcloneConfigResponse:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )

    return _parse_response(result.stdout)


class RcloneOAuthProcess:
    def __init__(
        self,
        *,
        remote_name: str,
        backend_type: str,
    ) -> None:
        if not remote_name.strip():
            raise ValueError("Remote name is required.")
        if not backend_type.strip():
            raise ValueError("Backend type is required.")

        self.remote_name = remote_name.strip()
        self.backend_type = backend_type.strip()
        self.process: subprocess.Popen[str] | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(
        self,
        *,
        state: str,
        result: str,
    ) -> subprocess.Popen[str]:
        if self.running:
            raise RuntimeError("OAuth process is already running.")

        if not state:
            raise ValueError("OAuth state is required.")

        rclone_binary = find_rclone()
        if not rclone_binary:
            raise RuntimeError("rclone was not found on PATH.")

        command = [
            rclone_binary,
            "config",
            "update",
            self.remote_name,
            "--continue",
            "--state",
            state,
            "--result",
            result,
        ]

        self.process = subprocess.Popen(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return self.process

    def stop(self) -> None:
        if self.process is None:
            return

        if self.running:
            self.process.terminate()

        self.process = None


class RcloneConfigSession:
    def __init__(
        self,
        *,
        remote_name: str,
        backend_type: str,
        timeout_seconds: int | None = None,
    ) -> None:
        if not remote_name.strip():
            raise ValueError("Remote name is required.")

        if not backend_type.strip():
            raise ValueError("Backend type is required.")

        self.remote_name = remote_name.strip()
        self.backend_type = backend_type.strip()
        self.timeout_seconds = timeout_seconds
        self.state = ""
        self.option: RcloneConfigOption | None = None
        self.completed = False

    def start(self) -> RcloneConfigResponse:
        response = start_remote_configuration(
            remote_name=self.remote_name,
            backend_type=self.backend_type,
            timeout_seconds=self.timeout_seconds,
        )
        self._update(response)
        return response

    def answer(self, result: str) -> RcloneConfigResponse:
        if self.completed:
            raise RuntimeError("rclone configuration is already complete.")

        if not self.state:
            raise RuntimeError("Configuration has not been started.")

        response = continue_remote_configuration(
            remote_name=self.remote_name,
            backend_type=self.backend_type,
            state=self.state,
            result=result,
            timeout_seconds=self.timeout_seconds,
        )
        self._update(response)
        return response

    def _update(self, response: RcloneConfigResponse) -> None:
        self.state = response.state
        self.option = response.option
        self.completed = not bool(response.state)


def start_remote_configuration(
    *,
    remote_name: str,
    backend_type: str,
    timeout_seconds: int | None = None,
) -> RcloneConfigResponse:
    if not remote_name.strip():
        raise ValueError("Remote name is required.")

    if not backend_type.strip():
        raise ValueError("Backend type is required.")

    rclone_binary = find_rclone()
    if not rclone_binary:
        raise RuntimeError("rclone was not found on PATH.")

    command = [
        rclone_binary,
        "config",
        "create",
        remote_name.strip(),
        backend_type.strip(),
        "--non-interactive",
    ]

    return _run_config_command(
        command,
        timeout_seconds=timeout_seconds,
    )


def continue_remote_configuration(
    *,
    remote_name: str,
    backend_type: str,
    state: str,
    result: str,
    timeout_seconds: int | None = None,
) -> RcloneConfigResponse:
    if not remote_name.strip():
        raise ValueError("Remote name is required.")

    if not backend_type.strip():
        raise ValueError("Backend type is required.")

    if not state:
        raise ValueError("Configuration state is required.")

    rclone_binary = find_rclone()
    if not rclone_binary:
        raise RuntimeError("rclone was not found on PATH.")

    command = [
        rclone_binary,
        "config",
        "update",
        remote_name.strip(),
        "--continue",
        "--state",
        state,
        "--result",
        result,
    ]

    return _run_config_command(
        command,
        timeout_seconds=timeout_seconds,
    )

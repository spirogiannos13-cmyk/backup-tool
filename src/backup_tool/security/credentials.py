from __future__ import annotations

import ctypes
from ctypes import wintypes

_TARGET_PREFIX = "BackupTool/SqlServer/"
_CREDENTIAL_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(wintypes.BYTE)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _api():
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Windows Credential Manager is available only on Windows.")
    return ctypes.windll.advapi32


def _target(server_id: int) -> str:
    return f"{_TARGET_PREFIX}{server_id}"


def save_sql_password(server_id: int, username: str, password: str) -> None:
    blob = password.encode("utf-16-le")
    buffer = (wintypes.BYTE * len(blob)).from_buffer_copy(blob)
    credential = _CREDENTIALW(
        Type=_CREDENTIAL_TYPE_GENERIC,
        TargetName=_target(server_id),
        CredentialBlobSize=len(blob),
        CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(wintypes.BYTE)),
        Persist=_CRED_PERSIST_LOCAL_MACHINE,
        UserName=username,
    )
    if not _api().CredWriteW(ctypes.byref(credential), 0):
        error = ctypes.get_last_error()
        raise OSError(error, f"CredWriteW failed with Windows error {error}.")


def load_sql_password(server_id: int) -> str | None:
    pointer = ctypes.POINTER(_CREDENTIALW)()
    if not _api().CredReadW(
        _target(server_id),
        _CREDENTIAL_TYPE_GENERIC,
        0,
        ctypes.byref(pointer),
    ):
        error = ctypes.get_last_error()
        if error == _ERROR_NOT_FOUND:
            return None
        raise OSError(error, f"CredReadW failed with Windows error {error}.")

    try:
        credential = pointer.contents
        raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        _api().CredFree(pointer)


def delete_sql_password(server_id: int) -> None:
    if not _api().CredDeleteW(_target(server_id), _CREDENTIAL_TYPE_GENERIC, 0):
        error = ctypes.get_last_error()
        if error != _ERROR_NOT_FOUND:
            raise OSError(error, f"CredDeleteW failed with Windows error {error}.")

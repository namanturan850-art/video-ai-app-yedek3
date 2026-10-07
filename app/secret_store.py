"""Encrypted local vault. No credentials are stored in source, SQLite or logs."""
import ctypes
import json
import os
from pathlib import Path
import tempfile
from threading import RLock

from cryptography.fernet import Fernet, InvalidToken


class SettingsStorageError(Exception):
    """Never include underlying file contents or credential values in errors."""


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    """Windows DPAPI, current-user scope, with no interactive prompts."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise OSError("Windows anahtar koruması kullanılamadı.")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel32.LocalFree(result.data)


def protect_key(key: bytes) -> bytes:
    return b"DPAPI1:" + _dpapi(key) if os.name == "nt" else b"LOCAL1:" + key


def unprotect_key(data: bytes) -> bytes:
    if data.startswith(b"DPAPI1:") and os.name == "nt":
        return _dpapi(data[7:], decrypt=True)
    if data.startswith(b"LOCAL1:") and os.name != "nt":
        return data[7:]
    raise SettingsStorageError("Yerel anahtar bu kullanıcı hesabında açılamadı.")


def atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if os.name != "nt":
                os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class SettingsStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.key_path = directory / "vault.key"
        self.vault_path = directory / "settings.enc"
        self.lock = RLock()

    def read(self) -> dict:
        if not self.vault_path.exists():
            return {}
        try:
            cipher = Fernet(unprotect_key(self.key_path.read_bytes()))
            values = json.loads(cipher.decrypt(self.vault_path.read_bytes()))
            if not isinstance(values, dict):
                raise ValueError("Invalid vault")
            return values
        except (OSError, ValueError, InvalidToken, SettingsStorageError):
            raise SettingsStorageError("Ayarlar açılamadı. Uygulamayı ayarları kaydettiğiniz Windows hesabında açın. Yerel ayar dosyalarını silmeden destek isteyin.") from None

    def write(self, values: dict) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                self.directory.chmod(0o700)
            if not self.key_path.exists():
                if self.vault_path.exists():
                    raise SettingsStorageError("Yerel anahtar kayıp; mevcut ayarlar korunuyor.")
                atomic_write(self.key_path, protect_key(Fernet.generate_key()))
            cipher = Fernet(unprotect_key(self.key_path.read_bytes()))
            atomic_write(self.vault_path, cipher.encrypt(json.dumps(values, ensure_ascii=False).encode("utf-8")))
        except (OSError, ValueError, InvalidToken, SettingsStorageError):
            raise SettingsStorageError("Ayarlar kaydedilemedi. Klasörün yazılabilir olduğunu ve aynı Windows hesabını kullandığınızı kontrol edin. Mevcut ayar dosyalarını silmeyin.") from None

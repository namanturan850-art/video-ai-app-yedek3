"""Encrypted local vault. No credentials are stored in source, SQLite or logs."""
import ctypes
import json
import os
from pathlib import Path
import tempfile
import time
import logging
from threading import RLock

from cryptography.fernet import Fernet, InvalidToken


class SettingsStorageError(Exception):
    """Never include underlying file contents or credential values in errors."""
    def __init__(self, message=None, category='key_decrypt_failed'):
        self.category = category
        messages = {
            'key_decrypt_failed': 'Ayarlar açılamadı. Ayarları kaydettiğiniz Windows hesabını kullanın; mevcut dosyaları silmeyin.',
            'folder_permission': 'Ayar klasörüne erişilemiyor. Uygulamayı yazma izniniz olan bir klasörde açın; mevcut verileri koruyun.',
            'temp_file_failed': 'Ayarlar için geçici dosya oluşturulamadı. Klasör iznini ve boş disk alanını kontrol edin.',
            'atomic_replace_failed': 'Ayar dosyası güncellenemedi. Dosyaları kullanan programları kapatıp tekrar deneyin. Önceki ayarlar korundu.',
            'encryption_failed': 'Ayarlar şifrelenemedi. Aynı Windows hesabında tekrar deneyin; mevcut dosyaları silmeyin.',
            'storage_locked': 'Ayar dosyası başka bir program tarafından kullanılıyor. Bir süre bekleyip tekrar Kaydet deyin. Önceki ayarlar korundu.'}
        super().__init__(message or messages[category])
        logging.getLogger('uvicorn.error.settings').info('vault operation=storage result=failure category=%s', category)


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
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
    except OSError:
        raise SettingsStorageError(category='temp_file_failed') from None
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if os.name != "nt":
                os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # The stream is CLOSED before replace: required on Windows. Antivirus/indexing
        # can briefly hold the destination; retry only known sharing/lock violations.
        for attempt in range(3):
            try:
                os.replace(temporary, path)
                break
            except OSError as error:
                locked = getattr(error, 'winerror', None) in (32, 33)
                if locked and attempt < 2:
                    time.sleep(.1 * (attempt + 1))
                    continue
                raise SettingsStorageError(category='storage_locked' if locked else 'atomic_replace_failed') from None
    except OSError:
        raise SettingsStorageError(category='temp_file_failed') from None
    finally:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass  # Never replace the real failure or touch the existing vault/key.


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
        except OSError as error:
            category = 'storage_locked' if getattr(error, 'winerror', None) in (32, 33) else 'folder_permission' if isinstance(error, PermissionError) else 'key_decrypt_failed'
            raise SettingsStorageError(category=category) from None
        except (ValueError, InvalidToken, SettingsStorageError):
            raise SettingsStorageError(category='key_decrypt_failed') from None

    def write(self, values: dict) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                self.directory.chmod(0o700)
        except OSError:
            raise SettingsStorageError(category='folder_permission') from None
        try:
            if not self.key_path.exists():
                if self.vault_path.exists():
                    raise SettingsStorageError("Yerel anahtar kayıp; mevcut ayarlar korunuyor.")
                try:
                    protected = protect_key(Fernet.generate_key())
                except (OSError, ValueError):
                    raise SettingsStorageError(category='encryption_failed') from None
                atomic_write(self.key_path, protected)
            cipher = Fernet(unprotect_key(self.key_path.read_bytes()))
        except SettingsStorageError:
            raise
        except (OSError, ValueError, InvalidToken):
            raise SettingsStorageError(category='key_decrypt_failed') from None
        try:
            content = cipher.encrypt(json.dumps(values, ensure_ascii=False).encode('utf-8'))
        except (ValueError, TypeError, UnicodeError):
            raise SettingsStorageError(category='encryption_failed') from None
        try:
            atomic_write(self.vault_path, content)
        except OSError:
            raise SettingsStorageError(category='atomic_replace_failed') from None

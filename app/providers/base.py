from typing import Protocol, runtime_checkable
import re


class ScriptProviderError(Exception):
    """Only fixed Turkish messages; never attach requests or raw API responses."""
    def __init__(self, message: str, status_code: int = 502, *, category: str = 'provider_error', retry_after: int = 0, upstream_status: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.category = category
        self.retry_after = max(0, min(120, retry_after))
        self.upstream_status = upstream_status


def normalize_text(value: object) -> str:
    """The provider boundary returns final text only, never a reasoning channel."""
    if not isinstance(value, str):
        raise ScriptProviderError('Sağlayıcının son metin alanı okunamadı.', category='invalid_response')
    text = value.lstrip('\ufeff').strip().replace('\r\n', '\n')
    if not text:
        raise ScriptProviderError('Sağlayıcı boş son yanıt döndürdü.', category='empty_response')
    if len(text) > 200000:
        raise ScriptProviderError('Sağlayıcı yanıtı izin verilen uzunluğu aştı.', category='invalid_response')
    if re.search(r'</?think(?:ing)?\s*>', text, re.IGNORECASE):
        raise ScriptProviderError('Sağlayıcı son metne reasoning içeriği ekledi; çıktı kullanılmadı.', category='reasoning_in_response')
    return text


@runtime_checkable
class ScriptProvider(Protocol):
    def generate_script(self, prompt: str) -> str: ...
    def test_connection(self) -> dict: ...

from typing import Protocol, runtime_checkable


class ScriptProviderError(Exception):
    """Only fixed Turkish messages; never attach requests or raw API responses."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


@runtime_checkable
class ScriptProvider(Protocol):
    def generate_script(self, prompt: str) -> str: ...
    def test_connection(self) -> dict: ...

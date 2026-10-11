"""In-memory stand-in for the official `anthropic` client (no network, no cost).

Only the surface the app uses: beta.messages.stream(...).get_final_message()
and models.retrieve(id). Every request is recorded so tests can assert on the
exact model/betas/fallbacks/output_config that would have been sent.
"""
from types import SimpleNamespace

import anthropic
import httpx2


def api_error(cls, status, message='synthetic'):
    request = httpx2.Request('POST', 'https://api.anthropic.com/v1/messages')
    if cls in (anthropic.APIConnectionError, anthropic.APITimeoutError):
        return cls(request=request)
    return cls(message, response=httpx2.Response(status, request=request), body=None)


def message(text, *, model='claude-opus-5-5', stop_reason='end_turn', input_tokens=1000, output_tokens=500):
    return SimpleNamespace(content=[SimpleNamespace(type='thinking', thinking=''), SimpleNamespace(type='text', text=text)],
                           stop_reason=stop_reason, model=model,
                           usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0))


class _Stream:
    def __init__(self, result):self.result = result
    def __enter__(self):
        if isinstance(self.result, Exception): raise self.result
        return self
    def __exit__(self, *exc):return False
    def get_final_message(self):return self.result


class FakeAnthropic:
    """`responder(request) -> message | Exception`."""
    def __init__(self, responder=None, *, models=('claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'), model_error=None):
        self.requests = []
        self.responder = responder or (lambda request: message('Hallo Welt.'))
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))
        self.models = SimpleNamespace(retrieve=self._retrieve)
        self._models, self._model_error = models, model_error

    def _stream(self, **request):
        self.requests.append(request)
        return _Stream(self.responder(request))

    def _retrieve(self, model_id):
        if self._model_error: raise self._model_error
        if model_id not in self._models: raise api_error(anthropic.NotFoundError, 404)
        return SimpleNamespace(id=model_id)

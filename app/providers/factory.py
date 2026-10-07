"""Provider selection without hardcoded models or implicit fallback."""
from app.providers.base import ScriptProvider, ScriptProviderError
from app.providers.gemini import GeminiScriptProvider

SCRIPT_ENGINE_LABELS = {'ollama': 'Ollama', 'openai': 'OpenAI', 'gemini': 'Gemini'}


def make_script_provider(engine: str, settings, *, discovery: bool = False) -> ScriptProvider:
    if engine != 'gemini':
        raise ScriptProviderError('Bu motorun senaryo üretim akışı henüz eklenmedi. Motor tercihiniz projede saklanabilir.', 422)
    config = settings.gemini_config()
    return GeminiScriptProvider(config.get('api_key', ''), '' if discovery else config['model'])

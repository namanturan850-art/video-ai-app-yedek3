"""Provider selection without hardcoded models or implicit fallback."""
from app.providers.base import ScriptProvider, ScriptProviderError
from app.providers.gemini import GeminiScriptProvider
from app.providers.text_api import OllamaScriptProvider, OpenAIScriptProvider

SCRIPT_ENGINE_LABELS = {'ollama': 'Ollama', 'openai': 'OpenAI', 'gemini': 'Gemini', 'claude': 'Claude'}


def safe_model(config, settings):
    if any(key in config.get('model', '') for key in settings.secret_values()):
        raise ScriptProviderError('Model alanında gizli anahtar var. Modeli Ayarlar ekranında düzeltin.', 422, category='invalid_settings')


def make_script_provider(engine: str, settings, *, discovery: bool = False, chain: bool = True) -> ScriptProvider:
    if engine == 'gemini':
        config = settings.gemini_config()
        if discovery: return GeminiScriptProvider(config.get('api_key', ''), '')
        safe_model(config, settings)
        if not chain:  # diagnostics test exactly the selected model
            return GeminiScriptProvider(config.get('api_key', ''), config['model'])
        from app.providers.gemini_chain import GeminiChain, chain_models
        # The backup chain: a model whose daily quota is used up hands over to the next one.
        models = chain_models(config)
        if not models: return GeminiScriptProvider(config.get('api_key', ''), config['model'])  # no model chosen yet: same message as before
        return GeminiChain(config.get('api_key', ''), models, settings,
                           lambda key, model: GeminiScriptProvider(key, model))
    if engine == 'ollama':
        config = settings.script_config(engine)
        safe_model(config, settings)
        return OllamaScriptProvider(config['base_url'], config['model'])
    if engine == 'openai':
        config = settings.script_config(engine)
        if not config['enabled']:
            raise ScriptProviderError('OpenAI kapalı. Ayarlar → OpenAI bölümünde Etkinleştir seçimini açıp Kaydet deyin.', 422, category='provider_disabled')
        safe_model(config, settings)
        return OpenAIScriptProvider(config.get('api_key', ''), config['model'])
    if engine == 'claude':
        from app.providers.claude import ClaudeProvider
        config = settings.script_config(engine)
        return ClaudeProvider(config.get('api_key', ''), config['model'], ledger=getattr(settings, 'usage_ledger', None))
    raise ScriptProviderError('Geçerli bir senaryo motoru seçin.', 422)

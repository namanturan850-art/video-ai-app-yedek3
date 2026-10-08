/* Official page/search parameters only; pagination response fields are unknown. */
function createAI33VoiceBrowser(loadPage) {
  const state = {provider: '', search: '', page: 1, voices: [], initialized: false, exhausted: false};
  let contextVersion = 0;
  function reset(provider, search = '') {
    contextVersion++;
    Object.assign(state, {provider, search, page: 1, voices: [], initialized: false, exhausted: false});
  }
  async function page(number, append = false) {
    if (!Number.isInteger(number) || number < 1 || number > 10) throw new Error('En fazla 10 sayfa / 300 ses yüklenebilir.');
    const version = contextVersion;
    const result = await loadPage({provider: state.provider, search: state.search, page: number, page_size: 30});
    if (version !== contextVersion) throw new Error('Ses sağlayıcısı veya arama değişti. Sesleri yeniden getirin.');
    const received = result.voices.filter(voice => voice.provider === state.provider).slice(0, 30);
    const combined = new Map((append ? state.voices : []).map(voice => [voice.voice_id, voice]));
    for (const voice of received) combined.set(voice.voice_id, voice);
    state.voices = Array.from(combined.values()).slice(0, 300);
    state.page = number;
    state.initialized = true;
    state.exhausted = received.length === 0 || number === 10;
    return result;
  }
  async function all(progress = () => {}) {
    let result;
    for (let number = 1; number <= 10; number++) {
      result = await page(number, number > 1);
      progress(result);
      if (state.exhausted) break;
    }
    return result;
  }
  return {state, reset, page, all};
}

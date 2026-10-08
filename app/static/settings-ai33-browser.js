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
    const version = contextVersion;
    let result;
    for (let number = 1; number <= 10; number++) {
      if (version !== contextVersion) throw new Error('Ses sağlayıcısı veya arama değişti. Sesleri yeniden getirin.');
      result = await page(number, number > 1);
      await progress(result);
      if (state.exhausted) break;
      // Yield between sequential requests so input/paint can run on Windows.
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    return result;
  }
  return {state, reset, page, all};
}

function updateAI33VoiceOptions(select, voices, selected, savedVoice) {
  const labels = new Map([['', 'Sesleri Getir ile listeden bir ses seçin']]);
  for (const voice of voices) labels.set(voice.voice_id, voice.display_name || voice.voice_id);
  if (selected && !labels.has(selected)) labels.set(selected, savedVoice ? `${savedVoice.display_name} (seçili ses)` : 'Önceki kayıtlı ses (henüz doğrulanmadı)');
  const existing = new Map();
  for (const option of Array.from(select.options)) {
    if (!labels.has(option.value) || existing.has(option.value)) option.remove();
    else existing.set(option.value, option);
  }
  const batch = document.createDocumentFragment();
  for (const [id, label] of labels) {
    let option = existing.get(id);
    if (!option) { option = document.createElement('option'); option.value = id; batch.append(option); }
    if (option.textContent !== label) option.textContent = label;
  }
  select.append(batch);
  select.value = selected || '';
}

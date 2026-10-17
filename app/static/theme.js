/* Persistent application chrome theme. Never changes video/render colour data. */
(() => {
  const defaults = {premiere:'#8065E8', turquoise:'#24D3C5', purple:'#A78BFA', blue:'#60A5FA', orange:'#FB923C', light:'#0F766E'};
  const valid = new Set(Object.keys(defaults));
  const normalize = value => /^#[0-9a-f]{6}$/i.test(value || '') ? value.toUpperCase() : null;
  function preview(theme, accent) {
    theme = valid.has(theme) ? theme : 'premiere';
    accent = normalize(accent) || defaults[theme];
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.setProperty('--vurgu', accent);
    document.documentElement.style.setProperty('--vurgu-acik', accent);
    try { localStorage.setItem('naman-theme', JSON.stringify({theme, accent})); } catch (_) {}
    return {theme, accent};
  }
  function reset() { return preview('premiere', defaults.premiere); }
  window.NAMANTheme = {preview, reset, defaultAccent: theme => defaults[theme] || defaults.premiere};
  try {
    const cached = JSON.parse(localStorage.getItem('naman-theme') || 'null');
    if (cached) preview(cached.theme, cached.accent); else reset();
  } catch (_) { reset(); }
  fetch('/api/settings', {credentials:'same-origin'}).then(response => response.ok ? response.json() : null).then(data => {
    if (data?.general) preview(data.general.appearance_theme, data.general.accent_color);
  }).catch(() => {});
})();

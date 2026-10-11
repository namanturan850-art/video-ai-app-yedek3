/* Same final-text word rule and saved options as Python's duration_metrics. */
/* Typical narration words/minute per language. Agglutinative Turkish needs far
   fewer words per minute; German (measured: ~3,139 chars ≈ 3:13 with an AI33
   ElevenLabs voice) keeps the previous 125–145 default. Only a starting point:
   real narration duration always wins once audio exists. */
const SCRIPT_SPEECH_RATES = {de: [125, 145], en: [140, 160], es: [145, 165], fr: [140, 160], tr: [105, 125]};
function scriptSpeechRate(language) { return SCRIPT_SPEECH_RATES[language] || [125, 145]; }
function scriptWordCount(text) {
  return (text.match(/[\p{L}\p{N}]+(?:['’\-][\p{L}\p{N}]+)*/gu) || []).length;
}
/* Measured pace per language (mirrors SPOKEN_RATE in app/scripts/models.py). */
const SCRIPT_SPOKEN_RATE = {de: 130, en: 150, es: 155, fr: 150, tr: 115};
function scriptDurationMetrics(text, minutes, options) {
  const count = scriptWordCount(text), low = options.words_per_minute_min, high = options.words_per_minute_max;
  const rate = SCRIPT_SPOKEN_RATE[options.language] || (low + high) / 2;
  return {word_count: count, target_word_min: Math.ceil(minutes * low), target_word_max: Math.floor(minutes * high),
    target_minutes: minutes, estimated_minutes: Math.round(count / rate * 100) / 100, spoken_rate: rate};
}
function scriptClock(seconds) { const s = Math.round(seconds); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; }
function scriptReviewMessages(messages, metrics) {
  const allowed = new Set([
    '✓ Yapı ve konu tutarlı.', '⚠ Konu ve anlatım tutarlılığını kontrol edin.',
    '⚠ Bölüm sırasını ve geçişleri kontrol edin.', '⚠ Tonu hedef içerikle uyumlu hale getirin.',
    '⚠ Tekrar tespit edildi; yinelenen ifadeleri düzenleyin.', '⚠ Bilgi ve iddiaları güvenilir kaynaklarla kontrol edin.',
    '⚠ Açılıştaki vaatlerin metinde karşılandığını kontrol edin.', '⚠ Hedef dilde anlatımı kontrol edin.',
    '⚠ Metnin konu, yapı ve ton tutarlılığını gözden geçirin.',
    'Elle düzenlenen metni onaylamadan önce tutarlılık ve gerçek bilgiler açısından inceleyin.',
    'Çeviri kaynak metnin uzunluğunu korur; proje hedef süresine göre genişletilmez.',
    'Tek süre düzeltmesi tamamlanamadı veya uygun sonuç vermedi; mevcut metin korundu.',
    'Seçilen önerilerle yeni taslak oluşturuldu. Önceki sürüm korunur; onaylamadan önce inceleyin.',
    'Tekrarlanan paragraflar var. Düzenle düğmesiyle kontrol edin.',
    'Tekrarlanan paragraflar var. Düzenle düğmesiyle kontrol edin; yinelenen bölümleri kaldırın.'
  ]);
  const safe = [...new Set((Array.isArray(messages) ? messages : []).filter(message => allowed.has(message)))];
  if (metrics.word_count < metrics.target_word_min) safe.push('⚠ Metin hedef süreden kısa.');
  if (metrics.word_count > metrics.target_word_max) safe.push('⚠ Metin hedef süreden uzun.');
  return safe;
}

const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../../app/static/script-metrics.js'), 'utf8'), context);
const words = count => Array.from({length: count}, (_, i) => `Wort${i}`).join(' ');
const options = {words_per_minute_min:125, words_per_minute_max:145};
const metric = text => context.scriptDurationMetrics(text, 3, options);
const review = (messages, text) => Array.from(context.scriptReviewMessages(messages, metric(text)));

test('385 final words in 375–435 have no stale duration warning', () => {
  const measured = metric(words(385));
  assert.equal(measured.word_count, 385);
  assert.equal(measured.target_word_min, 375);
  assert.equal(measured.target_word_max, 435);
  assert.equal(measured.estimated_minutes, 2.85);
  assert.deepEqual(review(['✓ Yapı ve konu tutarlı.', '⚠ Metin hedef süreden kısa.',
    'Kelime sayısı hedef süre aralığının dışında. Kaliteyi ve tahmini süreyi inceleyin; gerekirse metni düzenleyin.'], words(385)), ['✓ Yapı ve konu tutarlı.']);
});

test('184 words show short warning; changing final editor text to 385 removes it', () => {
  const message = '⚠ Metin hedef süreden kısa.';
  assert.deepEqual(review([], words(184)), [message]);
  assert.deepEqual(review([message], words(385)), []);
  assert.equal(metric(words(184)).estimated_minutes, 1.36);
});

test('target endpoints are inclusive and only actual out-of-range text warns', () => {
  for (const count of [375,435]) assert.deepEqual(review([], words(count)), []);
  assert.deepEqual(review([], words(374)), ['⚠ Metin hedef süreden kısa.']);
  assert.deepEqual(review([], words(436)), ['⚠ Metin hedef süreden uzun.']);
});

test('German/English blueprint commentary and private reasoning never enter the review UI', () => {
  const messages = review(['Der im blueprint definierte Titel...', 'Die Struktur des Abschnitts...',
    'Der Tonfall...', '<think>private reasoning</think>', '⚠ Tekrar tespit edildi; yinelenen ifadeleri düzenleyin.'], words(385));
  assert.deepEqual(messages, ['⚠ Tekrar tespit edildi; yinelenen ifadeleri düzenleyin.']);
});

test('Unicode, compound words and apostrophes use the final-text word rule', () => {
  assert.equal(context.scriptWordCount("Türkçe Größe l’été can't Drei-Minuten 3.5 Wort_name 東京"), 10);
});

test('saved version speed controls its range even when the future generation form changes', () => {
  const saved = context.scriptDurationMetrics(words(385), 3, options);
  const future = context.scriptDurationMetrics(words(385), 3, {words_per_minute_min:200,words_per_minute_max:210});
  assert.deepEqual(Array.from(context.scriptReviewMessages([], saved)), []);
  assert.deepEqual(Array.from(context.scriptReviewMessages([], future)), ['⚠ Metin hedef süreden kısa.']);
});

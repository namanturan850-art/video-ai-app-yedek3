"""Public review is a fixed Turkish summary; duration always uses final text."""
from app.scripts.models import duration_metrics

SHORT_WARNING = '⚠ Metin hedef süreden kısa.'
LONG_WARNING = '⚠ Metin hedef süreden uzun.'
REVIEW_MESSAGES = {
    'topic': '⚠ Konu ve anlatım tutarlılığını kontrol edin.',
    'structure': '⚠ Bölüm sırasını ve geçişleri kontrol edin.',
    'tone': '⚠ Tonu hedef içerikle uyumlu hale getirin.',
    'repetition': '⚠ Tekrar tespit edildi; yinelenen ifadeleri düzenleyin.',
    'facts': '⚠ Bilgi ve iddiaları güvenilir kaynaklarla kontrol edin.',
    'promises': '⚠ Açılıştaki vaatlerin metinde karşılandığını kontrol edin.',
    'language': '⚠ Hedef dilde anlatımı kontrol edin.',
}
GENERIC_REVIEW = '⚠ Metnin konu, yapı ve ton tutarlılığını gözden geçirin.'
MANUAL_REVIEW = 'Elle düzenlenen metni onaylamadan önce tutarlılık ve gerçek bilgiler açısından inceleyin.'
TRANSLATION_NOTE = 'Çeviri kaynak metnin uzunluğunu korur; proje hedef süresine göre genişletilmez.'
CORRECTION_WARNING = 'Tek süre düzeltmesi tamamlanamadı veya uygun sonuç vermedi; mevcut metin korundu.'
DURATION_MESSAGES = {SHORT_WARNING, LONG_WARNING, 'Kelime sayısı hedef süre aralığının dışında. Kaliteyi ve tahmini süreyi inceleyin; gerekirse metni düzenleyin.'}
ALLOWED = set(REVIEW_MESSAGES.values()) | {GENERIC_REVIEW, MANUAL_REVIEW, TRANSLATION_NOTE, CORRECTION_WARNING,
    'Seçilen önerilerle yeni taslak oluşturuldu. Önceki sürüm korunur; onaylamadan önce inceleyin.',
    'Tekrarlanan paragraflar var. Düzenle düğmesiyle kontrol edin; yinelenen bölümleri kaldırın.',
    'Tekrarlanan paragraflar var. Düzenle düğmesiyle kontrol edin.'}


def safe_review_issues(issues):
    safe = []
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, str) or issue in DURATION_MESSAGES:
            continue
        message = REVIEW_MESSAGES.get(issue, issue if issue in ALLOWED else GENERIC_REVIEW)
        if message not in safe: safe.append(message)
    return safe


def final_report(text, minutes, options, report):
    metrics = duration_metrics(text, minutes, options)
    issues = safe_review_issues(report.get('issues', []))
    if metrics['word_count'] < metrics['target_word_min']: issues.append(SHORT_WARNING)
    if metrics['word_count'] > metrics['target_word_max']: issues.append(LONG_WARNING)
    consistent = report.get('consistent') is True
    messages = (['✓ Yapı ve konu tutarlı.'] if consistent else []) + issues
    if not consistent and not messages: messages = [GENERIC_REVIEW]
    return {'consistent': consistent, 'issues': issues, 'review_messages': messages, **metrics}

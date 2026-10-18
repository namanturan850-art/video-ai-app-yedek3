"""Counts and input query only; never remote URLs, tokens or response bodies."""
import logging
import re
from urllib.parse import unquote

from app.scripts.engine import SecretGuard

LOG = logging.getLogger('uvicorn.error.stock')
REASONS = ('resolution','duration','relevance','orientation','malformed_result','unsafe_url')
LABELS = {'resolution':'çözünürlük','duration':'süre','relevance':'uygunluk','orientation':'dikey/kare video',
          'malformed_result':'geçersiz medya bilgisi','unsafe_url':'güvensiz adres'}
CATEGORIES = {'none','success','missing_key','invalid_query','timeout','connection_error',
              'invalid_response','key_rejected','rate_limit','invalid_request','upstream_error'}


def safe_query(query, secrets=()):
    text = str(query)[:2000]
    for _ in range(2): text = unquote(text)
    text = SecretGuard(secrets).clean(text)
    # Queries are English phrases from Part 5. Credential/URL-shaped input isn't
    # useful in the diagnostic log; discard it entirely, including signed tokens.
    if re.search(r'https?://|[?=&]|\b(?:authorization|api[_ -]?key|token|secret|password|signature)\s*:',text,re.I):
        return '[Gizli bilgi veya adres içeren sorgu gizlendi]'
    return ' '.join(text.split())[:300]


def count(value):
    return value if type(value) is int and 0<=value<=80 else None


def normalization_counts(value, normalized_count):
    """Legacy cache has no raw counts. Never invent numbers for that case."""
    value = value if isinstance(value,dict) else {}
    rejected = value.get('rejected',{})
    extra = {k: value[k] for k in ('filtered', 'missing_preview', 'result_category', 'response_category', 'http_status', 'current_page', 'last_page')
             if k in value and isinstance(value[k], (int, str))}
    return {**extra, 'raw_count':count(value.get('raw_count')), 'normalized_count':normalized_count,
            'rejected':{reason:count(rejected.get(reason)) for reason in ('malformed_result','unsafe_url')}}


def search_summary(diagnostic):
    label = diagnostic['provider'].title()+' '+('video' if diagnostic['media_type']=='video' else 'görsel')
    raw, normalized, accepted = diagnostic['raw_count'],diagnostic['normalized_count'],diagnostic['accepted_count']
    if diagnostic['category'] not in ('none','success'):
        return label+': arama tamamlanamadı. Güvenli tanı: '+diagnostic['category']+'.'
    if raw is None:
        summary = f'{label}: {normalized} önbellek/sağlayıcı adayı → {accepted} uygun aday (ham sayaç yok).'
    else:
        summary = f'{label}: {raw} sonuç → {normalized} kullanılabilir → {accepted} uygun aday.'
    reasons = [f'{value} {LABELS[reason]}' for reason,value in diagnostic['rejected'].items() if value]
    if reasons: summary += ' Elenen: '+', '.join(reasons)+'.'
    if accepted and diagnostic['available_count']==0: summary += ' Uygun adaylar projede zaten kullanılıyor.'
    if diagnostic['cached']: summary += ' 24 saatlik önbellek kullanıldı.'
    return summary


def log_search(diagnostic):
    LOG.info('stock stage=selection provider=%s media_type=%s query=%s raw_count=%s normalized_count=%s accepted_count=%s '
             'available_count=%s rejected_resolution=%s rejected_duration=%s rejected_relevance=%s '
             'rejected_orientation=%s rejected_malformed_result=%s rejected_unsafe_url=%s cached=%s category=%s',
             diagnostic['provider'],diagnostic['media_type'],diagnostic['query'],diagnostic['raw_count'],
             diagnostic['normalized_count'],diagnostic['accepted_count'],diagnostic['available_count'],
             *(diagnostic['rejected'][r] for r in REASONS),diagnostic['cached'],diagnostic['category'])


def public_report(value):
    """Support export omits local paths, signed URLs and arbitrary raw payloads.

    SecretGuard still validates the final response in the route. Only slot-sized
    narration is included by the caller; full scripts/voice/project files aren't.
    """
    from urllib.parse import urlsplit, urlunsplit
    hidden = {'local_path', 'download_url', 'preview_url', 'source_url', 'creator_url',
              'api_key', 'token', 'authorization', 'password', 'raw_response', 'context'}
    if isinstance(value, dict):
        return {k: public_report(v) for k, v in value.items() if k.casefold() not in hidden}
    if isinstance(value, list):return [public_report(v) for v in value]
    if not isinstance(value, str):return value
    if value.startswith(('https://', 'http://')):
        try:
            url = urlsplit(value)
            return urlunsplit((url.scheme, url.hostname or '', url.path, '', ''))
        except ValueError:return '[adres çıkarıldı]'
    value = re.sub(r'\b[A-Za-z]:[\\/][^\s\n]+', '[yerel yol çıkarıldı]', value)
    value = re.sub(r'(?<![\w:/])/(?:workspace|tmp|home|Users|var|opt)/[^\s\n]+', '[yerel yol çıkarıldı]', value)
    return value

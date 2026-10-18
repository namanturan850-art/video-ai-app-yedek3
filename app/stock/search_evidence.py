"""Bounded per-slot retry evidence. Failures expire; provider errors are retriable."""
from datetime import datetime, timezone, timedelta
from app.stock.search_session import canonical_query

MAX_ATTEMPTS = 300
FAILURE_TTL = timedelta(hours=1)
SLOT_REQUESTS = 24
JOB_REQUESTS = 120


def identity(entry):
    provider = entry.get('provider', '')
    return (provider, entry.get('media_type'), canonical_query(entry.get('query', ''), provider), entry.get('page', 1))


def failed_recently(slot, entry, context):
    for old in reversed(slot.get('search_attempts', [])):
        old_id, requested_id = identity(old), identity(entry)
        counts = old.get('normalization') or {}
        exhausted = counts.get('raw_count') == 0 or (type(counts.get('last_page')) is int and counts['last_page'] <= old_id[3])
        same_page = old_id == requested_id
        later_exhausted_page = old_id[:3] == requested_id[:3] and requested_id[3] > old_id[3] and exhausted
        if old.get('context') != context or old.get('outcome') != 'no_selection' or not (same_page or later_exhausted_page):
            continue
        try:
            stamp = datetime.fromisoformat(old['at'])
            return datetime.now(timezone.utc) - stamp < FAILURE_TTL
        except (KeyError, ValueError, TypeError):
            return False
    return False


def remember(slot, log, context, at):
    entries = list(slot.get('search_attempts', []))
    for search in log.get('searches', []):
        if search.get('skipped'):continue
        entries.append({**search, 'context': context, 'at': at,
                        'outcome': 'provider_error' if search.get('error') else 'selected' if slot.get('selected_media') else 'no_selection'})
    slot['search_attempts'] = entries[-MAX_ATTEMPTS:]


def reasons(log):
    found = set()
    searches = log.get('searches', [])
    if any(s.get('results') == 0 and not s.get('error') for s in searches):found.add('empty_search_results')
    for s in searches:
        category = s.get('error')
        if category == 'rate_limit':found.add('provider_rate_limited')
        elif category in ('auth','invalid_key','unauthorized','missing_key','key_rejected'):found.add('provider_key_rejected')
        elif category:found.add('provider_unreachable')
        if s.get('skipped') == 'budget':found.add('search_budget_reached')
        if s.get('skipped') == 'previous_failure':found.add('previous_search_failures_skipped')
    mapping = {'setting_conflict':'setting_conflict','visual_subject_conflict':'relevance_unverified',
               'used_elsewhere':'duplicate_candidates_rejected','ai_rejected_before':'relevance_unverified',
               'orientation':'portrait_or_resolution_rejected','duration':'candidate_duration_too_short','portrait':'portrait_or_resolution_rejected','resolution':'portrait_or_resolution_rejected',
               'too_short':'source_too_short'}
    for code,count in log.get('rejected', {}).items():
        if count and code in mapping:found.add(mapping[code])
    if any(not v.get('approved') for v in log.get('judged', {}).values()):found.add('relevance_unverified')
    for step in log.get('steps', []):
        if step.get('download_errors'):
            found.add('download_failed')
            if 'rate_limit' in step['download_errors']:found.add('provider_rate_limited')
        if step.get('quality_rejections'):found.add('technical_quality_rejected')
        if step.get('short_sources'):found.add('source_too_short')
    return sorted(found) or ['sources_only_no_approved_stock']

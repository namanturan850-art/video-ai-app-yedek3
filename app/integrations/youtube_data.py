"""YouTube Data API v3 (public data, API key only): video details and comments.

Documented calls only (developers.google.com/youtube/v3/docs):
- GET /youtube/v3/videos?part=snippet,statistics,contentDetails&id=...&key=...
- GET /youtube/v3/commentThreads?part=snippet&videoId=...&order=relevance&maxResults=100&textFormat=plainText&key=...
The API has no "order by likes"; up to 100 relevant top-level comments are read
and the 50 with the most likes are kept. The key is sent only to Google.
"""
import re
from urllib.parse import parse_qs, urlsplit

import httpx

BASE = 'https://www.googleapis.com/youtube/v3'
VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')


class YouTubeDataError(Exception):
    def __init__(self, category, message):
        super().__init__(message)
        self.category = category


def video_id(url):
    """The 11-character id of a youtube.com / youtu.be link, or None."""
    try:
        parts = urlsplit((url or '').strip())
    except ValueError:
        return None
    host = (parts.hostname or '').lower()
    candidate = None
    if host == 'youtu.be':
        candidate = parts.path.strip('/').split('/')[0]
    elif host == 'youtube.com' or host.endswith('.youtube.com'):
        if parts.path == '/watch':
            candidate = (parse_qs(parts.query).get('v') or [''])[0]
        else:
            segments = parts.path.strip('/').split('/')
            if len(segments) >= 2 and segments[0] in ('shorts', 'live', 'embed'):
                candidate = segments[1]
    return candidate if candidate and VIDEO_ID.match(candidate) else None


def duration_seconds(iso):
    """ISO 8601 duration (e.g. PT1H2M3S) to seconds."""
    match = re.fullmatch(r'P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso or '')
    if not match:
        return None
    d, h, m, s = (int(x or 0) for x in match.groups())
    return d * 86400 + h * 3600 + m * 60 + s


def number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YouTubeDataClient:
    def __init__(self, api_key, *, transport=None, timeout=20):
        if not api_key:
            raise YouTubeDataError('missing_key', 'YouTube Data API anahtarı kaydedilmemiş.')
        self.key = api_key
        self.client = httpx.Client(transport=transport, timeout=timeout)

    def _get(self, path, params):
        try:
            response = self.client.get(f'{BASE}/{path}', params={**params, 'key': self.key})
        except httpx.HTTPError:
            raise YouTubeDataError('network', 'YouTube’a bağlanılamadı. İnternet bağlantınızı kontrol edin.') from None
        if response.status_code == 200:
            try:
                return response.json()
            except ValueError:
                raise YouTubeDataError('invalid_response', 'YouTube yanıtı okunamadı.') from None
        try:
            errors = response.json().get('error', {}).get('errors', [])
            reason = errors[0].get('reason', '') if errors else ''
        except (ValueError, AttributeError):
            reason = ''
        if reason == 'videoNotFound':
            raise YouTubeDataError('not_found', 'Video bulunamadı veya herkese açık değil.')
        if reason == 'commentsDisabled':
            raise YouTubeDataError('comments_disabled', 'Bu videoda yorumlar kapalı.')
        if reason in ('quotaExceeded', 'dailyLimitExceeded', 'rateLimitExceeded'):
            raise YouTubeDataError('quota', 'YouTube Data API günlük kotası doldu. Yarın tekrar deneyin.')
        if reason in ('keyInvalid', 'keyExpired') or (response.status_code == 400 and 'key' in response.text.casefold()):
            raise YouTubeDataError('key_invalid', 'YouTube Data API anahtarı geçersiz. Ayarlar → YouTube bölümünden kontrol edin.')
        if response.status_code == 403:
            raise YouTubeDataError('forbidden', 'YouTube Data API bu anahtarla kullanılamıyor. Google Cloud Console’da “YouTube Data API v3” etkin mi kontrol edin.')
        raise YouTubeDataError('http_error', f'YouTube isteği tamamlanamadı (HTTP {response.status_code}).')

    def test(self):
        self._get('videos', {'part': 'id', 'chart': 'mostPopular', 'maxResults': 1, 'regionCode': 'US'})
        return {'status': 'Hazır', 'message': 'YouTube Data API bağlantısı başarılı. Kaynak videoların sayıları ve yorumları okunabilir.', 'category': 'none'}

    def video(self, vid):
        data = self._get('videos', {'part': 'snippet,statistics,contentDetails', 'id': vid})
        items = data.get('items') or []
        if not items:
            raise YouTubeDataError('not_found', 'Video bulunamadı veya herkese açık değil.')
        item = items[0]
        snippet, stats = item.get('snippet') or {}, item.get('statistics') or {}
        return {'id': vid, 'title': str(snippet.get('title', ''))[:300], 'description': str(snippet.get('description', ''))[:5000],
                'tags': [str(t)[:100] for t in (snippet.get('tags') or [])][:60], 'channel': str(snippet.get('channelTitle', ''))[:200],
                'published_at': str(snippet.get('publishedAt', ''))[:40], 'language': str(snippet.get('defaultAudioLanguage') or snippet.get('defaultLanguage') or '')[:20],
                'duration_seconds': duration_seconds((item.get('contentDetails') or {}).get('duration')),
                'views': number(stats.get('viewCount')), 'likes': number(stats.get('likeCount')), 'comments': number(stats.get('commentCount'))}

    def top_comments(self, vid, limit=50):
        data = self._get('commentThreads', {'part': 'snippet', 'videoId': vid, 'order': 'relevance', 'maxResults': 100, 'textFormat': 'plainText'})
        comments = []
        for thread in data.get('items') or []:
            top = ((thread.get('snippet') or {}).get('topLevelComment') or {}).get('snippet') or {}
            text = ' '.join(str(top.get('textDisplay') or '').split())  # textOriginal is author-only
            if text:
                comments.append({'text': text[:600], 'likes': number(top.get('likeCount')) or 0})
        return sorted(comments, key=lambda c: -c['likes'])[:limit]

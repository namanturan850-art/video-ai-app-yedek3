"""Project-local exact identity, safe canonical URLs and downloaded byte hashes."""
from urllib.parse import urlsplit, unquote


def identity_keys(media):
    if not media:return set()
    keys={(media['provider'],media['media_type'],media['media_id'])}
    for field in ('page_url','source_url','download_url'):
        try:
            u=urlsplit(media.get(field,''))
            if u.scheme=='https' and u.hostname and not u.username and not u.password:
                path=unquote(u.path).rstrip('/')
                if path:keys.add(('url',u.hostname.lower().removeprefix('www.'),path))
        except (ValueError,TypeError):pass
    if media.get('sha256'):keys.add(('sha256',media['sha256']))
    return keys


def duplicate(media,others):
    return any(identity_keys(media)&identity_keys(other) for other in others if other)

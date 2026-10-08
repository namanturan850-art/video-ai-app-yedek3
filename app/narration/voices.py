"""Owner-verified v3 voice records. Unverified fields are not copied."""
import ipaddress
import re
from urllib.parse import urlsplit

from pydantic import ValidationError

from app.narration.models import NarrationError, Voice, VOICE_ID_PREFIXES
from app.narration.read_client import shape_diagnostic
from app.scripts.engine import SecretGuard
from app.scripts.models import ScriptError

TEXT_METADATA=('description','language','locale','gender','age','accent','category')
ARRAY_METADATA=('use_cases','descriptives','tags','languages')


def public_preview_url(value):
    """Browser-only public HTTPS media. Never proxy arbitrary URLs server-side."""
    if not isinstance(value,str) or not value or len(value)>2000:return ''
    try:
        url=urlsplit(value);host=(url.hostname or '').rstrip('.').lower()
        if (url.scheme!='https' or url.username is not None or url.password is not None
            or url.port not in (None,443) or url.fragment or '\\' in value
            or any(c.isspace() or ord(c)<32 for c in value)):return ''
        try:
            if not ipaddress.ip_address(host).is_global:return ''
        except ValueError:
            if ('.' not in host or not re.fullmatch(r'[a-z0-9.-]+',host)
                or re.fullmatch(r'[0-9.]+',host)
                or not re.fullmatch(r'[a-z][a-z0-9-]*',host.rsplit('.',1)[-1])
                or host.endswith(('.localhost','.local','.internal','.lan','.home','.invalid'))):return ''
        return value
    except (ValueError,TypeError):return ''


def normalize_voices(data,provider,http_status,secrets):
    """Map only verified voice_id/name and documented optional metadata."""
    try:
        if (not isinstance(data,dict) or data.get('success') is not True
            or not isinstance(data.get('format_version'),str)
            or not isinstance(data.get('data'),list) or not isinstance(data.get('pagination'),dict)):
            raise ValueError()
        result=[]
        for record in data['data']:
            if not isinstance(record,dict):raise ValueError()
            voice_id,name=record.get('voice_id'),record.get('name')
            if (not isinstance(voice_id,str) or not isinstance(name,str) or not name.strip()
                or not any(voice_id.startswith(p) and len(voice_id)>len(p) for p in VOICE_ID_PREFIXES)
                or any(c.isspace() for c in voice_id)):raise ValueError()
            item={'provider':provider,'voice_id':voice_id,'display_name':name}
            for field in TEXT_METADATA:
                if isinstance(record.get(field),str):item[field]=record[field]
            for field in ARRAY_METADATA:
                if isinstance(record.get(field),list):item[field]=record[field]
            # Guard before URL filtering so an echoed key never becomes metadata.
            SecretGuard(secrets).validate({**item,'preview_url':record.get('preview_url'),'avatar_url':record.get('avatar_url')})
            item['preview_url']=public_preview_url(record.get('preview_url'))
            item['avatar_url']=public_preview_url(record.get('avatar_url')) or None
            result.append(Voice.model_validate(item).model_dump())
        return result
    except (ValueError,TypeError,ValidationError,ScriptError):
        raise NarrationError('unexpected_voice_schema','AI33 ses yanıtı beklenen biçimde değil. Önceki ses seçimi korundu; tekrar deneyin.',502,
                             shape_diagnostic(data,'voices',http_status,secrets)) from None

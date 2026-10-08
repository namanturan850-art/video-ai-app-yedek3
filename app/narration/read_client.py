"""Read-only transport from the request contract supplied in the Part 7 request.

No undocumented credits/voice/task fields are interpreted. Paid task creation
must wait for direct verification of the current official response contract.
"""
import json
import logging
import re
import time

import httpx
from pydantic import SecretStr

from app.narration.models import OFFICIAL_BASE, NarrationError

LOG=logging.getLogger('uvicorn.error.narration')
PRIVATE_READ_KEYS=set()


class PrivateReadHTTPFilter(logging.Filter):
    def filter(self,record):
        message=record.getMessage().lower()
        return 'openspeaker.ai' not in message and not any(key.lower() in message for key in tuple(PRIVATE_READ_KEYS))


for name in ('httpx','httpcore','httpcore.connection','httpcore.http11','httpcore.http2','httpcore.proxy'):
    logging.getLogger(name).addFilter(PrivateReadHTTPFilter())


def shape_diagnostic(data,operation,http_status,secrets=()):
    """Field names/types only; hostile names are discarded, values never saved."""
    types={str:'string',int:'number',float:'number',bool:'boolean',list:'array',dict:'object',type(None):'null'}
    fields=[]
    if isinstance(data,dict):
        for key,value in list(data.items())[:40]:
            if (not isinstance(key,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,49}',key)
                    or any(secret and secret.casefold() in key.casefold() for secret in secrets)):
                continue
            fields.append({'name':key,'type':types.get(type(value),'unknown')})
    return {'operation':operation,'http_status':http_status,'top_level_fields':fields,
            'response_type':types.get(type(data),'unknown'),
            'task_id_presence':isinstance(data,dict) and 'task_id' in data}


class OpenSpeakerReadClient:
    def __init__(self,api_key,*,transport=None,secrets=()):
        self.key=SecretStr(api_key);self.transport=transport
        self.secrets=tuple(v for v in (api_key,*secrets) if v)
        PRIVATE_READ_KEYS.update(self.secrets)

    def test_connection(self):
        key=self.key.get_secret_value()
        if not key:raise NarrationError('missing_key','Önce Ayarlar → AI33 / OpenSpeaker bölümünde API anahtarını kaydedin.',422)
        if not key.isascii() or any(ord(c)<33 or ord(c)==127 for c in key):
            raise NarrationError('invalid_request','API anahtarını boşluksuz ve eksiksiz girin.',422)
        started=time.monotonic();category='success';status=None
        try:
            with httpx.Client(timeout=httpx.Timeout(30,connect=10),transport=self.transport,follow_redirects=False) as client:
                with client.stream('GET',OFFICIAL_BASE+'/v1/credits',headers={'xi-api-key':key}) as response:
                    status=response.status_code
                    if status!=200:
                        category={401:'key_rejected',403:'key_rejected',429:'rate_limit'}.get(status,'credits_unavailable')
                        message={'key_rejected':'API anahtarı reddedildi. AI33 / OpenSpeaker anahtarını kontrol edin.',
                                 'rate_limit':'AI33 istek sınırına ulaşıldı. Bir süre bekleyip tekrar deneyin.',
                                 'credits_unavailable':'Kullanım/kredi bilgisi alınamadı. Daha sonra tekrar deneyin.'}[category]
                        raise NarrationError(category,message)
                    raw=bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw)>1_000_000:raise ValueError()
            data=json.loads(raw)
            diagnostic=shape_diagnostic(data,'credits',status,self.secrets)
            # The owner explicitly permits this fallback when the precise credit
            # balance response field cannot be verified. Never guess a field.
            return {'status':'Hazır','message':'AI33 / OpenSpeaker bağlantısı başarılı.',
                    'credits':None,'credits_message':'Kredi bilgisi API tarafından döndürüldü ancak bu sürümde gösterilemiyor.',
                    'diagnostic':diagnostic}
        except httpx.TimeoutException:
            category='timeout'
            raise NarrationError(category,'API zaman aşımına uğradı. İnternet bağlantısını kontrol edip tekrar deneyin.') from None
        except httpx.HTTPError:
            category='connection_error'
            raise NarrationError(category,'API bağlantısı kurulamadı. İnternet bağlantısını kontrol edip tekrar deneyin.') from None
        except (ValueError,TypeError):
            category='credits_unavailable'
            raise NarrationError(category,'Kullanım/kredi bilgisi alınamadı. Yanıt okunamadı; daha sonra tekrar deneyin.') from None
        finally:
            LOG.info('narration operation=credits category=%s http_status=%s elapsed_ms=%.0f',category,status,(time.monotonic()-started)*1000)

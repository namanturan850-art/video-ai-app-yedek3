"""Official verified request routes; unknown response schemas fail closed.

The owner verified v3 voice records. Task completion/output fields remain
unverified; paid generation stays blocked until those are supplied.
"""
import json
import time
from typing import Protocol,runtime_checkable

import httpx

from app.narration.models import OFFICIAL_BASE,VOICE_PROVIDERS,VOICE_ID_PREFIXES,SCHEMA_MESSAGE,NarrationError,safe_task_id
from app.narration.read_client import OpenSpeakerReadClient,LOG,shape_diagnostic
from app.scripts.engine import SecretGuard
from app.scripts.models import ScriptError
from app.narration.voices import normalize_voices


@runtime_checkable
class TTSProvider(Protocol):
    contract_ready: bool
    def list_voices(self,provider,search='',page=1,page_size=30): ...
    def synthesize(self,text,voice,options): ...
    def get_job_status(self,task_id): ...


class OpenSpeakerProvider(OpenSpeakerReadClient):
    # Enable ONLY after voice IDs and task state/output fields are documented.
    contract_ready=False
    output_hosts=frozenset()

    def _request(self,operation,path,*,method='GET',params=None,form=None):
        key=self.key.get_secret_value()
        if not key:raise NarrationError('missing_key','Önce Ayarlar → AI33 / OpenSpeaker API anahtarını kaydedin.',422)
        if not key.isascii() or any(ord(c)<33 or ord(c)==127 for c in key):
            raise NarrationError('invalid_request','API anahtarını boşluksuz ve eksiksiz girin.',422)
        started=time.monotonic();status=None;category='success'
        try:
            # No filenames: these are FormData text fields, not uploaded files.
            # httpx owns Content-Type and the multipart boundary.
            multipart={'files':[(name,(None,str(value))) for name,value in form.items()]} if form is not None else {}
            with httpx.Client(timeout=httpx.Timeout(60,connect=10),transport=self.transport,follow_redirects=False) as client:
                with client.stream(method,OFFICIAL_BASE+path,params=params,headers={'xi-api-key':key},**multipart) as response:
                    status=response.status_code
                    if status!=200:
                        category='task_history_unavailable' if operation=='tasks' and status in (404,405) else {401:'key_rejected',403:'key_rejected',422:'invalid_request',429:'rate_limit'}.get(status,
                                  'task_create_failed' if method=='POST' else 'task_poll_failed' if operation=='poll' else 'connection_error')
                        messages={'key_rejected':'API anahtarı reddedildi. Ayarlardaki anahtarı kontrol edin.',
                                  'invalid_request':'AI33 isteği kabul etmedi. Ses seçimini ve ayarları kontrol edin.',
                                  'rate_limit':'AI33 istek sınırına ulaşıldı. Bir süre bekleyip tekrar deneyin.',
                                  'task_history_unavailable':'Görev geçmişi bu API yanıtında kullanılamıyor. Ses ayarları korundu; bu uç noktanın hesap erişimini kontrol edin.'}
                        raise NarrationError(category,messages.get(category,'AI33 isteği tamamlanamadı. Daha sonra tekrar deneyin.'))
                    raw=bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw)>4_000_000:raise ValueError()
            return json.loads(raw),status
        except httpx.TimeoutException:
            category='timeout'
            raise NarrationError(category,'API zaman aşımına uğradı. Görev varsa korunur; internet bağlantısını kontrol edin.') from None
        except httpx.HTTPError:
            category='connection_error'
            raise NarrationError(category,'API bağlantısı kurulamadı. İnternet bağlantısını kontrol edin.') from None
        except (ValueError,TypeError):
            category='unexpected_task_schema'
            raise NarrationError(category,SCHEMA_MESSAGE,502,shape_diagnostic(None,operation,status,(key,))) from None
        finally:LOG.info('narration operation=%s category=%s http_status=%s elapsed_ms=%.0f',operation,category,status,(time.monotonic()-started)*1000)

    def list_voices(self,provider,search='',page=1,page_size=30):
        if (provider not in VOICE_PROVIDERS or not isinstance(search,str) or len(search)>200
            or type(page) is not int or not 1<=page<=10000 or type(page_size) is not int or not 1<=page_size<=100):
            raise NarrationError('invalid_request','Ses sağlayıcısını, aramayı ve sayfa seçimini kontrol edin.',422)
        SecretGuard(self.secrets).validate((provider,search))
        data,status=self._request('voices','/v3/voices',params={'provider':provider,'search':search,'page':page,'page_size':page_size})
        return normalize_voices(data,provider,status,self.secrets)

    def task_history_diagnostic(self):
        # Official GET /v1/tasks; no guessed type filter, no task creation.
        data,status=self._request('tasks','/v1/tasks')
        diagnostic=shape_diagnostic(data,'tasks',status,self.secrets)
        LOG.info('narration operation=tasks result=read_only diagnostic=%s',diagnostic)
        return diagnostic

    def task_diagnostic(self,task_id):
        # Input is supplied locally, never hardcoded or persisted. No paid call.
        try:task_id=safe_task_id(task_id)
        except NarrationError:
            raise NarrationError('invalid_task_id','Geçerli bir Task ID girin. Yalnız harf, rakam, tire ve alt çizgi kullanılabilir (en fazla 150 karakter).',422) from None
        SecretGuard(self.secrets).validate(task_id)
        data,status=self._request('inspect_task','/v1/task/'+task_id)
        diagnostic=shape_diagnostic(data,'inspect_task',status,self.secrets)
        LOG.info('narration operation=inspect_task result=read_only diagnostic=%s',diagnostic)
        return diagnostic

    def synthesize(self,text,voice,options):
        # Success fields verified in the owner's authenticated documentation
        # excerpt: {"success":true,"task_id":"uuid_task_id"}. The service blocks
        # paid jobs until discovery and output parsing are verified as well.
        speed=options.get('speed',1)
        if (not isinstance(text,str) or not text.strip() or len(text)>1_000_000
            or not isinstance(voice,str) or not voice.strip() or len(voice)>150
            or type(speed) not in (int,float) or not .5<=speed<=1.5):
            raise NarrationError('invalid_request','Ses, metin ve 0,5–1,5 hız aralığını kontrol edin.',422)
        if not any(voice.startswith(prefix) and len(voice)>len(prefix) for prefix in VOICE_ID_PREFIXES) or any(c.isspace() for c in voice):
            raise NarrationError('invalid_voice','Ses kimliği belgelenmiş sağlayıcı önekiyle başlamalı. Ses yanıt belgesi doğrulanınca listeden bir ses seçin.',422)
        SecretGuard(self.secrets).validate((text,voice))
        data,status=self._request('create','/v3/text-to-speech',method='POST',form={'text':text,'voice_id':voice,'speed':speed,'with_transcript':'false'})
        task_id=None
        if isinstance(data,dict) and 'task_id' in data:
            try:
                task_id=safe_task_id(data['task_id'])
                SecretGuard(self.secrets).validate(task_id)
            except ScriptError:
                task_id=None
        if not isinstance(data,dict) or data.get('success') is not True:
            raise NarrationError('task_create_failed','AI33 görevi oluşturma sonucu doğrulanamadı. Yeni ücretli görev otomatik başlatılmaz.',502,
                                 shape_diagnostic(data,'create',status,self.secrets),remote_task_id=task_id)
        if task_id is None:
            raise NarrationError('unexpected_task_schema',SCHEMA_MESSAGE,502,shape_diagnostic(data,'create',status,self.secrets)) from None
        return {'task_id':task_id}

    def get_job_status(self,task_id):
        task_id=safe_task_id(task_id)
        SecretGuard(self.secrets).validate(task_id)
        data,status=self._request('poll','/v1/task/'+task_id)
        diagnostic=shape_diagnostic(data,'poll',status,self.secrets)
        LOG.info('narration operation=poll result=unverified_schema fields=%s metadata_fields=%s task_id_presence=%s',diagnostic['top_level_fields'],diagnostic['metadata_fields'],diagnostic['task_id_presence'])
        raise NarrationError('unexpected_task_schema',SCHEMA_MESSAGE,502,diagnostic)


def make_tts_provider(settings):
    return OpenSpeakerProvider(settings.tts_config().get('api_key',''),secrets=settings.secret_values())

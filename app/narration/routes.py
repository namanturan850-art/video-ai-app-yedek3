from fastapi import APIRouter,Request
from fastapi.responses import FileResponse
from app.narration.audio import audio_path,LIMIT
from app.narration.models import NarrationError


def narration_router(service):
    router=APIRouter(prefix='/api/projects/{project_id}/narration')

    @router.get('')
    def view(project_id:str):return service.view(project_id)

    @router.post('/jobs',status_code=202)
    def start(project_id:str,payload:dict):return service.start(project_id,payload)

    @router.post('/jobs/{job_id}/resume',status_code=202)
    def resume(project_id:str,job_id:str,payload:dict):
        if payload:raise NarrationError('invalid_request','Devam Et yeni seslendirme bilgisi göndermez.',422)
        return service.resume(project_id,job_id)

    @router.post('/versions/{version_id}/activate')
    def activate(project_id:str,version_id:str,payload:dict):
        if payload.get('confirm') is not True or set(payload)!={'confirm'}:
            raise NarrationError('invalid_request','Aktif seslendirme seçimi için açık onay gerekli.',422)
        return service.select_active(project_id,version_id)

    @router.get('/versions/{version_id}/audio')
    def audio(project_id:str,version_id:str):
        item=next((v for v in service.view(project_id)['versions'] if v['id']==version_id),None)
        if not item or not item['metadata'].get('audio'):
            raise NarrationError('invalid_audio','Bu sürüm için ses dosyası henüz hazır değil.',404)
        media=item['metadata']['audio'];path=audio_path(service.projects,project_id,media)
        return FileResponse(path,media_type=media['content_type'],headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @router.post('/versions/{version_id}/recover',status_code=202)
    def recover(project_id:str,version_id:str,payload:dict):
        if payload:raise NarrationError('invalid_request','AI33’ten kurtar yeni seslendirme bilgisi göndermez.',422)
        return service.recover_version(project_id,version_id)

    @router.post('/versions/{version_id}/upload')
    async def upload(project_id:str,version_id:str,request:Request):
        # Raw body with a hard cap; filename and content-length are never trusted.
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>LIMIT:raise NarrationError('invalid_audio','Ses dosyası izin verilen boyutu aşıyor.',422)
        return service.upload_audio(project_id,version_id,request.headers.get('x-audio-format'),bytes(data))

    @router.get('/handoff')
    def handoff(project_id:str):return service.handoff(project_id)

    return router

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from app.rendering.models import RenderError


def render_router(service):
    router=APIRouter(prefix='/api/projects/{project_id}/render')
    @router.get('')
    def view(project_id:str):return service.view(project_id)
    @router.post('/jobs',status_code=202)
    def start(project_id:str,payload:dict):return service.start(project_id,payload)
    @router.post('/jobs/{job_id}/cancel')
    def cancel(project_id:str,job_id:str):return service.cancel(project_id,job_id)
    @router.post('/versions/{version_id}/activate')
    def activate(project_id:str,version_id:str):return service.activate(project_id,version_id)
    @router.get('/versions/{version_id}/video')
    def video(project_id:str,version_id:str,download:bool=False):
        path=service.export(project_id,version_id)
        return FileResponse(path,media_type='video/mp4',filename=path.name,content_disposition_type='attachment' if download else 'inline',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    @router.get('/handoff')
    def handoff(project_id:str):return service.handoff(project_id)
    @router.post('/music',status_code=201)
    async def music(project_id:str,request:Request):
        # Stream with a hard size cap; never trust filenames or content-length.
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>100_000_000:raise RenderError('music_invalid','Müzik dosyası 100 MB sınırını aşıyor.',422)
        return service.music_upload(project_id,request.headers.get('x-music-format'),bytes(data),request.headers.get('x-music-license')=='confirmed')
    return router

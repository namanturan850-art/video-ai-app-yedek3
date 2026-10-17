from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.responses import Response
from app.editor.models import EditorError
from app.stock.download import directory


def editor_router(service):
    router=APIRouter(prefix='/api/projects/{project_id}/editor')
    from app.editor.advanced import AdvancedEditor
    advanced=AdvancedEditor(service)

    @router.get('/advanced')
    def advanced_view(project_id:str):return advanced.get(project_id)

    @router.put('/advanced')
    def advanced_save(project_id:str,payload:dict):return advanced.save(project_id,payload)

    @router.post('/advanced/history/{direction}')
    def advanced_history(project_id:str,direction:str,payload:dict):return advanced.history(project_id,direction,payload)

    @router.get('/advanced/program-frame')
    def advanced_frame(project_id:str,time:float=0):
        from app.editor.previews import program_frame
        return FileResponse(program_frame(service,advanced,project_id,time),media_type='image/jpeg')

    @router.get('/archive/{provider}/{media_id}/thumbnail')
    def archive_thumbnail(project_id:str,provider:str,media_id:str):
        from app.editor.previews import thumbnail
        return FileResponse(thumbnail(service,project_id,provider,media_id),media_type='image/jpeg')

    @router.get('')
    def view(project_id:str): return service.view(project_id)

    @router.get('/archive')
    def archive(project_id:str): return service.archive(project_id)

    @router.get('/waveform')
    def waveform(project_id:str): return service.waveform(project_id)

    @router.get('/audio-settings')
    def audio_settings(project_id:str): return service.audio_settings(project_id)

    @router.put('/audio-settings')
    def save_audio_settings(project_id:str,payload:dict): return service.save_audio_settings(project_id,payload)

    @router.post('/archive/upload',status_code=201)
    async def archive_upload(project_id:str,request:Request):
        name=unquote(request.headers.get('x-file-name',''))
        if not name or Path(name).name != name or len(name)>240:
            raise EditorError('invalid_upload','Dosya adını kontrol edin.')
        folder=directory(service.projects,project_id)
        temporary=folder/('.upload-'+uuid4().hex+'.part')
        size=0
        try:
            with temporary.open('xb') as stream:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>512*1024*1024:
                        raise EditorError('upload_too_large','Dosya 512 MB sınırını aşıyor.',413)
                    stream.write(chunk)
            if not size: raise EditorError('invalid_upload','Boş dosya yüklenemez.')
            return service.import_local(project_id,temporary,name)
        finally:
            temporary.unlink(missing_ok=True)

    @router.get('/archive/{provider}/{media_id}/preview')
    def archive_preview(project_id:str,provider:str,media_id:str):
        path, _ = service.archive_file(project_id,provider,media_id)
        return FileResponse(path)

    @router.put('/slots/{slot_id}/media')
    def assign(project_id:str,slot_id:str,payload:dict): return service.assign(project_id,slot_id,payload)

    @router.post('/slots/{slot_id}/edit')
    def edit_clip(project_id:str,slot_id:str,payload:dict): return service.edit_clip(project_id,slot_id,payload)

    @router.put('/timeline')
    def timeline(project_id:str,payload:dict): return service.update_timeline(project_id,payload)

    @router.post('/timeline/{direction}')
    def timeline_history(project_id:str,direction:str,payload:dict): return service.timeline_history(project_id,direction,payload)

    @router.post('/slots/{slot_id}/motion',status_code=202)
    def motion(project_id:str,slot_id:str,payload:dict): return service.edit_motion(project_id,slot_id,payload)

    @router.get('/revisions')
    def revisions(project_id:str): return service.revisions(project_id)

    @router.put('/archive/{provider}/{media_id}/range')
    def clip_range(project_id:str,provider:str,media_id:str,payload:dict): return service.set_range(project_id,provider,media_id,payload)

    @router.post('/archive/{provider}/{media_id}/analyze')
    def analyze(project_id:str,provider:str,media_id:str,payload:dict): return service.analyze(project_id,provider,media_id,payload)

    @router.post('/quality/video-review')
    def video_review(project_id:str,payload:dict): return service.video_review(project_id,payload)

    @router.get('/manual/package')
    def task_package(project_id:str): return service.task_package(project_id)

    @router.get('/manual/package.zip')
    def task_package_zip(project_id:str):
        content=service.task_package_zip(project_id)
        return Response(content,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="naman-manuel-plan.zip"'})

    @router.post('/manual/validate')
    def validate(project_id:str,payload:dict): return service.validate_import(project_id,payload)

    @router.post('/manual/import',status_code=201)
    def import_plan(project_id:str,payload:dict): return service.import_plan(project_id,payload)

    @router.post('/revisions/{plan_id}/rollback',status_code=201)
    def rollback(project_id:str,plan_id:str,payload:dict): return service.rollback(project_id,plan_id,payload)

    return router

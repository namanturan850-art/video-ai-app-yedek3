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
    from app.editor.editorial import Editorial
    editorial=Editorial(service)
    from app.editor.reviews import Reviews
    reviews=Reviews(service)
    from app.editor.history import History
    history=History(service)

    @router.get('/history')
    def history_snapshot(project_id:str):return history.snapshot(project_id)

    @router.post('/history/{direction}')
    def history_apply(project_id:str,direction:str,payload:dict):return history.apply(project_id,direction,payload)

    @router.post('/quality/comprehensive')
    def comprehensive_start(project_id:str,payload:dict):
        from app.editor.comprehensive import start
        return start(service,project_id,payload)

    @router.get('/quality/comprehensive/{key}')
    def comprehensive_status(project_id:str,key:str):
        from app.editor.comprehensive import status
        return status(service,project_id,key)

    @router.post('/quality/comprehensive/{key}/cancel')
    def comprehensive_cancel(project_id:str,key:str):
        from app.editor.comprehensive import status
        return status(service,project_id,key,cancel=True)

    @router.post('/quality/local')
    def local_quality(project_id:str):
        from app.editor.local_quality import inspect
        return inspect(service,project_id)

    @router.get('/quality/reviews')
    def review_reports(project_id:str):return reviews.get(project_id)

    @router.post('/quality/review-request')
    def review_request(project_id:str,payload:dict):return reviews.request(project_id,payload)

    @router.put('/quality/reviews/{render_id}/{finding_id}')
    def review_status(project_id:str,render_id:str,finding_id:str,payload:dict):return reviews.status(project_id,render_id,finding_id,payload)

    @router.put('/subtitles')
    def edit_subtitles(project_id:str,payload:dict):return editorial.subtitles_edit(project_id,payload)

    @router.post('/subtitles/history/{direction}')
    def subtitle_history(project_id:str,direction:str,payload:dict):return editorial.subtitle_history(project_id,direction,payload)

    @router.get('/editorial')
    def editorial_view(project_id:str):return editorial.get(project_id)

    @router.put('/editorial')
    def editorial_save(project_id:str,payload:dict):return editorial.save(project_id,payload)

    @router.post('/editorial/automatic')
    def editorial_draft(project_id:str):return editorial.automatic(project_id)

    @router.post('/editorial/import-draft')
    def editorial_import(project_id:str,payload:dict):return editorial.import_draft(project_id,payload)

    @router.post('/editorial/drafts/{draft_id}/resolve-transition')
    def resolve_transition(project_id:str,draft_id:str,payload:dict):return editorial.resolve_transition(project_id,draft_id,payload)

    @router.post('/editorial/drafts/{draft_id}/approve')
    def editorial_approve(project_id:str,draft_id:str,payload:dict):return editorial.approve(project_id,draft_id,payload)

    @router.get('/editorial/drafts')
    def editorial_drafts(project_id:str):return editorial.drafts(project_id)

    @router.get('/editorial/drafts/{draft_id}/preview')
    def editorial_preview(project_id:str,draft_id:str,time:float=0):return FileResponse(editorial.preview(project_id,draft_id,time),media_type='image/jpeg')

    @router.get('/advanced')
    def advanced_view(project_id:str):return advanced.get(project_id)

    @router.put('/advanced')
    def advanced_save(project_id:str,payload:dict):return advanced.save(project_id,payload)

    @router.post('/advanced/history/{direction}')
    def advanced_history(project_id:str,direction:str,payload:dict):return advanced.history(project_id,direction,payload)

    @router.get('/advanced/motion-elements/{clip_id}')
    def advanced_motion_elements(project_id:str,clip_id:str):
        from app.editor.motion_objects import scene_for
        return scene_for(advanced,project_id,clip_id)

    @router.post('/advanced/operations')
    def advanced_operations(project_id:str,payload:dict):
        from app.editor.operations import operate
        return operate(advanced,project_id,payload)

    @router.post('/advanced/program-proxy')
    def advanced_proxy(project_id:str,payload:dict):
        from app.editor.proxies import request
        if set(payload)!={'time','quality'} or type(payload['time']) not in (int,float) or not isinstance(payload['quality'],str):raise EditorError('invalid_proxy','Önizleme zamanı ve kalitesini kontrol edin.')
        return request(service,advanced,project_id,payload['time'],payload['quality'])

    @router.get('/advanced/program-proxy-status/{key}')
    def advanced_proxy_status(project_id:str,key:str):
        from app.editor.proxies import status
        return status(service,project_id,key)

    @router.get('/advanced/program-proxy/{key}')
    def advanced_proxy_file(project_id:str,key:str):
        from app.editor.proxies import file
        return FileResponse(file(service,project_id,key),media_type='video/mp4')

    @router.get('/advanced/program-stream-info/{key}')
    def advanced_stream_info(project_id:str,key:str):
        from app.editor.proxies import stream
        return stream(service,project_id,key)[1]

    @router.get('/advanced/program-stream/{key}')
    def advanced_stream_file(project_id:str,key:str):
        from app.editor.proxies import stream
        return FileResponse(stream(service,project_id,key)[0],media_type='video/mp4')

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

    @router.post('/manual/package/prepare')
    def prepare_task_package(project_id:str,payload:dict):
        return service.prepare_task_package(project_id,payload)

    @router.post('/manual/response-draft',status_code=201)
    def response_draft(project_id:str,payload:dict):
        from app.editor.manual_review import parse_response, review
        return review(editorial,project_id,parse_response(payload.get('text')))

    @router.get('/manual/package.zip')
    def task_package_zip(project_id:str):
        content=service.task_package_zip(project_id)
        return Response(content,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="naman-manuel-plan.zip"'})

    @router.post('/manual/validate')
    def validate(project_id:str,payload:dict):
        from app.editor.editorial import manual
        if not manual(service.projects,project_id):return service.validate_import(project_id,payload)
        from app.editor.manual_review import review_validation
        return review_validation(editorial,project_id,payload)

    @router.post('/manual/import',status_code=201)
    def import_plan(project_id:str,payload:dict): return service.import_plan(project_id,payload)

    @router.post('/revisions/{plan_id}/rollback',status_code=201)
    def rollback(project_id:str,plan_id:str,payload:dict): return service.rollback(project_id,plan_id,payload)

    return router

import json
from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.stock.download import asset_path
from app.stock.models import StockError


def stock_router(service):
    router = APIRouter(prefix='/api/projects/{project_id}/production/stock')

    @router.get('')
    def view(project_id: str): return service.view(project_id)

    @router.post('/jobs',status_code=202)
    def start(project_id: str, payload: dict): return service.start(project_id,payload)

    @router.post('/jobs/{job_id}/resume',status_code=202)
    def resume(project_id: str,job_id: str,payload: dict): return service.resume(project_id,job_id,payload)

    @router.post('/slots/{slot_id}/jobs',status_code=202)
    def slot_job(project_id: str,slot_id: str,payload: dict): return service.start(project_id,payload,slot_id=slot_id)

    @router.post('/slots/{slot_id}/actions')
    def action(project_id: str,slot_id: str,payload: dict): return service.mutate(project_id,slot_id,payload)

    @router.get('/slots/{slot_id}/preview')
    def preview(project_id: str,slot_id: str):
        state = service.view(project_id)
        slot = service._slot(state,slot_id)
        media = slot['selected_media']
        if not media: raise StockError('missing_media','Önce medya seçip indirin.',404)
        path = asset_path(service.projects,project_id,media)
        return FileResponse(path,media_type=media['content_type'],headers={'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})

    @router.get('/diagnostics')
    def diagnostics(project_id: str):
        from datetime import datetime
        from fastapi.responses import Response
        from app.stock.director_media import diagnostics as build
        data = build(service, project_id)
        service._guard(data)
        name = f'medya-tanilama-{datetime.now():%Y%m%d-%H%M}.json'
        return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type='application/json',
                        headers={'Content-Disposition': f'attachment; filename="{name}"', 'Cache-Control': 'no-store'})

    @router.post('/translate', status_code=202)
    def retranslate(project_id: str): return service.retranslate(project_id)

    @router.get('/handoff')
    def handoff(project_id: str): return service.handoff(project_id)

    return router

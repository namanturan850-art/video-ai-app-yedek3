from fastapi import APIRouter
from fastapi.responses import FileResponse


def editor_router(service):
    router=APIRouter(prefix='/api/projects/{project_id}/editor')

    @router.get('')
    def view(project_id:str): return service.view(project_id)

    @router.get('/archive')
    def archive(project_id:str): return service.archive(project_id)

    @router.get('/archive/{provider}/{media_id}/preview')
    def archive_preview(project_id:str,provider:str,media_id:str):
        path, _ = service.archive_file(project_id,provider,media_id)
        return FileResponse(path)

    @router.put('/slots/{slot_id}/media')
    def assign(project_id:str,slot_id:str,payload:dict): return service.assign(project_id,slot_id,payload)

    @router.put('/timeline')
    def timeline(project_id:str,payload:dict): return service.update_timeline(project_id,payload)

    @router.post('/slots/{slot_id}/motion',status_code=202)
    def motion(project_id:str,slot_id:str,payload:dict): return service.edit_motion(project_id,slot_id,payload)

    @router.get('/revisions')
    def revisions(project_id:str): return service.revisions(project_id)

    @router.put('/archive/{provider}/{media_id}/range')
    def clip_range(project_id:str,provider:str,media_id:str,payload:dict): return service.set_range(project_id,provider,media_id,payload)

    @router.post('/archive/{provider}/{media_id}/analyze')
    def analyze(project_id:str,provider:str,media_id:str,payload:dict): return service.analyze(project_id,provider,media_id,payload)

    @router.get('/manual/package')
    def task_package(project_id:str): return service.task_package(project_id)

    @router.post('/manual/validate')
    def validate(project_id:str,payload:dict): return service.validate_import(project_id,payload)

    @router.post('/manual/import',status_code=201)
    def import_plan(project_id:str,payload:dict): return service.import_plan(project_id,payload)

    @router.post('/revisions/{plan_id}/rollback',status_code=201)
    def rollback(project_id:str,plan_id:str,payload:dict): return service.rollback(project_id,plan_id,payload)

    return router

from fastapi import APIRouter
from fastapi.responses import FileResponse


def editor_router(service):
    router=APIRouter(prefix='/api/projects/{project_id}/editor')

    @router.get('')
    def view(project_id:str): return service.view(project_id)

    @router.get('/archive')
    def archive(project_id:str): return service.archive(project_id)

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

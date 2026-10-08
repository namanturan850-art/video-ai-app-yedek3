from fastapi import APIRouter
from fastapi.responses import FileResponse


def subtitle_router(service):
    router=APIRouter(prefix='/api/projects/{project_id}/subtitles')

    @router.get('')
    def view(project_id:str):return service.view(project_id)

    @router.post('/duration')
    def duration(project_id:str):return service.refresh_duration(project_id)

    @router.post('/versions',status_code=201)
    def create(project_id:str,payload:dict):return service.create(project_id,payload)

    @router.post('/versions/{version_id}/edit',status_code=201)
    def edit(project_id:str,version_id:str,payload:dict):return service.edit(project_id,version_id,payload)

    @router.post('/versions/{version_id}/activate')
    def activate(project_id:str,version_id:str,payload:dict):return service.activate(project_id,version_id,payload)

    @router.get('/versions/{version_id}/files/{format}')
    def file(project_id:str,version_id:str,format:str):
        path=service.export(project_id,version_id,format)
        return FileResponse(path,media_type='text/vtt' if format=='vtt' else 'application/x-subrip',
                            filename=path.name,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @router.get('/handoff')
    def handoff(project_id:str):return service.handoff(project_id)

    return router

from fastapi import APIRouter


def router(bridge):
    result=APIRouter(prefix='/api/settings/openmontage')
    @result.get('')
    def status(refresh:bool=False):return bridge.status(refresh)
    @result.post('')
    def save(payload:dict):return bridge.save(payload)
    from app.integrations.openmontage.engine_status import components,Installer
    installer=Installer()
    result.installer=installer
    @result.get('/engine')
    def engine():return {**components(bridge),'install':installer.view()}
    @result.post('/engine/install')
    def install(payload:dict):
        if payload.get('confirm') is not True:
            from fastapi.responses import JSONResponse
            return JSONResponse({'message':'Kurulum için açık onay gerekli.'},status_code=422)
        return installer.start()
    return result

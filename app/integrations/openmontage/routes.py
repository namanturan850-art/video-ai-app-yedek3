from fastapi import APIRouter


def router(bridge):
    result=APIRouter(prefix='/api/settings/openmontage')
    @result.get('')
    def status(refresh:bool=False):return bridge.status(refresh)
    @result.post('')
    def save(payload:dict):return bridge.save(payload)
    return result

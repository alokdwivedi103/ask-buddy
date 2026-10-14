"""Authenticated diagnostics for optional infrastructure."""
from fastapi import APIRouter, Depends
from clients import get_redis_client, get_elasticsearch_client
from dependencies import verify_api_key

router = APIRouter(prefix='/health', dependencies=[Depends(verify_api_key)])


@router.get('/infrastructure')
def infrastructure_health():
    result = {'service': 'reflect', 'optional': True}
    for name, factory in (('redis', get_redis_client), ('elasticsearch', get_elasticsearch_client)):
        client = factory()
        result[name] = 'connected' if client is not None else 'unavailable'
        if client is not None:
            client.close()
    return result

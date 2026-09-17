from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.services.api_key_client import probe
from backend.services.auth_service import Session, require_admin
from backend.services.secret_store import SERVICES

router = APIRouter(prefix='/api/integrations', tags=['Integrations'])


class Credentials(BaseModel):
    url: str = Field(min_length=1, max_length=512)
    secret: str = Field(min_length=1, max_length=512)


async def _test_iptv_gtw(request: Request, url: str, token: str) -> None:
    # Fetching the playlist (rather than the unauthenticated /healthz) validates
    # the export token itself, not just that the host is reachable.
    await probe('iptv-gtw', request.app.state.upstream_transport, 'GET', url, 'playlist.m3u', params={'token': token})


@router.get('/status')
async def status(request: Request, session: Session):
    await require_admin(request, session)
    return request.app.state.secrets.status()


@router.post('/{service}')
async def save(service: str, data: Credentials, request: Request, session: Session):
    await require_admin(request, session)
    if service not in SERVICES:
        raise HTTPException(404, 'Unknown integration')
    if service == 'iptv_gtw':
        await _test_iptv_gtw(request, data.url, data.secret)
    else:
        await getattr(request.app.state, service).test_connection(data.url, data.secret)
    request.app.state.secrets.save(service, data.url, data.secret)
    return {'saved': True}

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.services.auth_service import Session, require_admin

router = APIRouter(prefix='/api/livetv', tags=['Live TV'])


class Recording(BaseModel):
    program_id: str = Field(min_length=1)
    series: bool = False


@router.get('/channels')
async def channels(request: Request, session: Session):
    return await request.app.state.jellyfin.request('GET', 'LiveTv/Channels', session,
        params={'UserId': session['user_id'], 'AddCurrentProgram': True}, cache=True)


@router.get('/guide')
async def guide(request: Request, session: Session, channel_id: str, start: str, end: str):
    return await request.app.state.jellyfin.request('GET', 'LiveTv/Programs', session,
        params={'UserId': session['user_id'], 'ChannelIds': channel_id,
                'MinEndDate': start, 'MaxStartDate': end}, cache=True)


@router.get('/recordings')
async def recordings(request: Request, session: Session):
    return await request.app.state.jellyfin.request('GET', 'LiveTv/Recordings', session,
        params={'UserId': session['user_id']})


@router.get('/timers')
async def timers(request: Request, session: Session):
    return await request.app.state.jellyfin.request('GET', 'LiveTv/Timers', session)


@router.post('/recordings', status_code=201)
async def record(data: Recording, request: Request, session: Session):
    client = request.app.state.jellyfin
    defaults = await client.request('GET', 'LiveTv/Timers/Defaults', session, params={'ProgramId': data.program_id})
    defaults['ProgramId'] = data.program_id
    return await client.request('POST', 'LiveTv/SeriesTimers' if data.series else 'LiveTv/Timers', session, body=defaults)


@router.delete('/timers/{timer_id}', status_code=204)
async def cancel(timer_id: str, request: Request, session: Session):
    await request.app.state.jellyfin.request('DELETE', f'LiveTv/Timers/{timer_id}', session)


@router.post('/configure-iptv')
async def configure_iptv(request: Request, session: Session):
    from fastapi import HTTPException
    await require_admin(request, session)
    settings = request.app.state.settings
    if not settings.iptv_m3u_url or not settings.iptv_xmltv_url:
        raise HTTPException(422, 'Configure IPTV_M3U_URL and IPTV_XMLTV_URL on the server first')
    client = request.app.state.jellyfin
    info = await client.request('GET', 'LiveTv/Info', session)
    tuner = next((t for t in info.get('TunerHosts', []) if t.get('Url') == settings.iptv_m3u_url), None)
    if not tuner:
        tuner = await client.request('POST', 'LiveTv/TunerHosts', session,
            body={'Type': 'm3u', 'Url': settings.iptv_m3u_url, 'FriendlyName': 'iptv-gtw', 'EnableAllTuners': True})
    providers = info.get('ListingProviders', [])
    if not any(p.get('Path') == settings.iptv_xmltv_url for p in providers):
        await client.request('POST', 'LiveTv/ListingProviders', session,
            body={'Type': 'xmltv', 'Path': settings.iptv_xmltv_url, 'EnableAllTuners': True})
    return {'configured': True, 'tuner': tuner}

import asyncio
from urllib.parse import urlencode, urlsplit

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.background import BackgroundTask
from starlette.responses import Response, StreamingResponse

from backend.services.auth_service import COOKIE, Session

router = APIRouter(tags=['Jellyfin compatibility'])
RESPONSE_HEADERS = {'content-type', 'content-length', 'content-range', 'accept-ranges',
                    'etag', 'last-modified', 'content-disposition', 'content-encoding'}
REQUEST_HEADERS = {'range', 'if-range', 'if-none-match', 'if-modified-since', 'content-type', 'accept'}


@router.api_route('/api/jellyfin/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'])
async def proxy(path: str, request: Request, session: Session):
    client = request.app.state.jellyfin
    path = client.safe_path(path)
    params = [(k, v) for k, v in request.query_params.multi_items()
              if k.lower() not in ('api_key', 'apikey', 'access_token')]
    headers = {k: v for k, v in request.headers.items() if k in REQUEST_HEADERS}
    headers.update(client.headers(session))
    upstream = client.http.build_request(request.method, path, params=params, headers=headers,
                                         content=request.stream() if request.method not in ('GET', 'HEAD') else None)
    try:
        result = await client.http.send(upstream, stream=True)
    except httpx.TimeoutException as exc:
        raise HTTPException(504, 'Jellyfin timed out') from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, 'Jellyfin is unavailable') from exc
    if result.is_redirect:
        await result.aclose()
        raise HTTPException(502, 'Upstream redirects are disabled')
    returned_headers = {k: v for k, v in result.headers.items() if k in RESPONSE_HEADERS}
    returned_headers['Cache-Control'] = 'private, no-store'
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and result.is_success:
        await client.redis.incr('cache:generation')
    if request.method != 'HEAD' and ('mpegurl' in result.headers.get('content-type', '').lower() or path.endswith('.m3u8')) and result.is_success:
        try:
            chunks = bytearray()
            async for chunk in result.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > 2 * 1024 * 1024:
                    raise HTTPException(502, 'Upstream playlist is too large')
            body = client.rewrite_playlist(chunks.decode(), path)
        finally:
            await result.aclose()
        return Response(body, status_code=result.status_code, media_type='application/vnd.apple.mpegurl',
                        headers={'Cache-Control': 'private, no-store'})
    async def stream_body():
        try:
            if result.is_stream_consumed:
                yield result.content
            else:
                async for chunk in result.aiter_raw():
                    yield chunk
        finally:
            await result.aclose()

    return StreamingResponse(stream_body(), status_code=result.status_code,
                             headers=returned_headers, background=BackgroundTask(result.aclose))


@router.websocket('/api/socket')
async def socket(websocket: WebSocket):
    state = websocket.app.state
    if websocket.headers.get('origin') != state.settings.public_url:
        await websocket.close(code=1008)
        return
    try:
        token = websocket.cookies.get(COOKIE, '')
        session = await state.auth.resolve(token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    parts = urlsplit(state.settings.jellyfin_url)
    url = ('wss' if parts.scheme == 'https' else 'ws') + '://' + parts.netloc + parts.path + '/socket?'
    url += urlencode({'deviceId': session['device_id']})
    try:
        async with websockets.connect(url, additional_headers=state.jellyfin.headers(session), max_size=2**20) as upstream:
            await websocket.accept()

            async def from_browser():
                while True:
                    data = await websocket.receive_text()
                    await state.auth.resolve(token)
                    await upstream.send(data)

            async def from_server():
                async for data in upstream:
                    await state.auth.resolve(token)
                    if isinstance(data, bytes):
                        await websocket.send_bytes(data)
                    else:
                        await websocket.send_text(data)

            tasks = [asyncio.create_task(from_browser()), asyncio.create_task(from_server())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except (websockets.WebSocketException, WebSocketDisconnect, OSError, HTTPException):
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass

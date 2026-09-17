"""Official SDK SSE server with per-user, revocable authentication."""
import re
from contextvars import ContextVar
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.services.auth_service import is_administrator

identity: ContextVar[str] = ContextVar('mcp_identity')


def create_mcp(state, settings):
    host = urlsplit(settings.public_url).netloc
    mcp = FastMCP('Jishflix Cinematic', sse_path='/sse', message_path='/messages/',
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=[host], allowed_origins=[settings.public_url]))

    async def context():
        # Resolve each call, so an open SSE connection cannot outlive revoked credentials.
        session = await state.auth.resolve(identity.get())
        return state.jellyfin, session

    async def require_admin(client, session):
        user = await client.request('GET', 'Users/Me', session)
        if not is_administrator(user):
            raise ValueError('Administrator access required')

    @mcp.tool()
    async def search_media_library(query: str, limit: int = 20) -> dict:
        """Search media visible to the authenticated user, respecting Jellyfin parental controls."""
        client, session = await context()
        return await client.request('GET', 'Items', session, params={
            'UserId': session['user_id'], 'SearchTerm': query[:512], 'Recursive': True,
            'Limit': max(1, min(limit, 100)), 'Fields': 'Overview,Genres'})

    @mcp.tool()
    async def get_continue_watching(limit: int = 20) -> dict:
        """Return the authenticated user's resumable media and saved progress."""
        client, session = await context()
        return await client.request('GET', f'Users/{session["user_id"]}/Items/Resume', session,
                                    params={'Limit': max(1, min(limit, 100))})

    @mcp.tool()
    async def check_stream_status() -> list[dict]:
        """List this user's active playback sessions without exposing device addresses or tokens."""
        client, session = await context()
        sessions = await client.request('GET', 'Sessions', session)
        return [{'id': s['Id'], 'device': s.get('DeviceName'),
                 'item': s.get('NowPlayingItem', {}).get('Name'),
                 'position_ticks': s.get('PlayState', {}).get('PositionTicks'),
                 'paused': s.get('PlayState', {}).get('IsPaused')}
                for s in sessions if s.get('UserId') == session['user_id']]

    @mcp.tool()
    async def trigger_media_sync() -> dict:
        """Request a Jellyfin library scan. Requires a current administrator role; changes server state."""
        client, session = await context()
        await require_admin(client, session)
        await client.request('POST', 'Library/Refresh', session)
        return {'accepted': True}

    @mcp.tool()
    async def request_movie_or_show(title: str, media_type: str = 'movie') -> dict:
        """Search Seerr and request a movie or TV show to be added to the library.
        Requires a current administrator role. media_type must be 'movie' or 'tv'."""
        client, session = await context()
        await require_admin(client, session)
        if not state.seerr.configured:
            raise ValueError('Seerr is not configured on this server')
        if media_type not in ('movie', 'tv'):
            raise ValueError("media_type must be 'movie' or 'tv'")
        results = await state.seerr.search(title)
        match = next((r for r in results if r.get('mediaType') == media_type), None)
        if not match:
            raise ValueError(f'No {media_type} match found on Seerr for "{title}"')
        result = await state.seerr.request_media(media_type, match['id'])
        return {'requested': True, 'title': match.get('title') or match.get('name'), 'seerr_id': result.get('id')}

    @mcp.tool()
    async def request_adult_scene(title: str) -> dict:
        """Search Whisparr and add a matching adult scene/studio release. Requires a current
        administrator role; this triggers an automatic search and download with no approval step."""
        client, session = await context()
        await require_admin(client, session)
        if not state.whisparr.configured:
            raise ValueError('Whisparr is not configured on this server')
        results = await state.whisparr.lookup(title)
        if not results:
            raise ValueError(f'No match found on Whisparr for "{title}"')
        added = await state.whisparr.add(results[0])
        return {'added': True, 'title': added.get('title'), 'whisparr_id': added.get('id')}

    return mcp


class MCPGuard:
    """Bind message POSTs to the bearer credential that opened their SSE stream."""
    def __init__(self, app, state):
        self.app, self.state = app, state

    async def __call__(self, scope, receive, send):
        request = Request(scope)
        auth = request.headers.get('authorization', '')
        try:
            if not auth.lower().startswith('bearer '):
                raise HTTPException(401, 'An MCP bearer token is required')
            token = auth[7:]
            session = await self.state.auth.resolve(token)
            if session['kind'] != 'mcp':
                raise HTTPException(403, 'Use a dedicated MCP token')
            await self.state.auth.rate_limit('mcp:' + self.state.auth.key(token), limit=120)
            owner = self.state.auth.key(token)
            if request.method == 'POST':
                sid = request.query_params.get('session_id', '')
                existing = await self.state.redis.get('mcp:' + sid)
                if not existing or existing.decode() != owner:
                    raise HTTPException(403, 'MCP session does not belong to this credential')
        except HTTPException as exc:
            await JSONResponse({'detail': exc.detail}, status_code=exc.status_code)(scope, receive, send)
            return
        marker = identity.set(token)
        opened = []

        async def capture(message):
            if message['type'] == 'http.response.body':
                body = message.get('body', b'').decode(errors='ignore')
                found = re.search(r'data: ([^\r\n]*session_id=[^\r\n]+)', body)
                if found:
                    sid = parse_qs(urlsplit(found[1]).query).get('session_id', [''])[0]
                    if sid:
                        opened.append(sid)
                        await self.state.redis.setex('mcp:' + sid, self.state.settings.session_ttl, owner)
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            identity.reset(marker)
            for sid in opened:
                await self.state.redis.delete('mcp:' + sid)

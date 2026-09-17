import logging
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Request
from pydantic import SecretStr
from redis.exceptions import RedisError
from starlette.responses import FileResponse, JSONResponse

from backend.config import get_settings
from backend.routers import auth, integrations, livetv, media, playback, proxy
from backend.services.auth_service import AuthService
from backend.services.jellyfin_client import JellyfinClient
from backend.services.mcp_server import MCPGuard, create_mcp
from backend.services.secret_store import SecretStore, load_or_create_key
from backend.services.seerr_client import SeerrClient
from backend.services.whisparr_client import WhisparrClient

logger = logging.getLogger('jishflix')


class SecurityHeaders:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        unsafe = request.method not in ('GET', 'HEAD', 'OPTIONS')
        bearer = request.headers.get('authorization', '').lower().startswith('bearer ')
        if unsafe and not bearer:
            origin = request.headers.get('origin')
            if request.headers.get('x-requested-with') != 'Jishflix' or (origin and origin != self.settings.public_url):
                return await JSONResponse({'detail': 'Invalid request origin or CSRF header'}, status_code=403)(scope, receive, send)
        if request.url.path.startswith(('/sse', '/messages')):
            origin = request.headers.get('origin')
            if origin and origin != self.settings.public_url:
                return await JSONResponse({'detail': 'Invalid MCP origin'}, status_code=403)(scope, receive, send)

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers.extend([(b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY'), (b'referrer-policy', b'no-referrer'),
                    (b'permissions-policy', b'camera=(), microphone=(), geolocation=()'),
                    (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")])
                if not any(k.lower() == b'cache-control' for k, _ in headers):
                    headers.append((b'cache-control', b'no-store'))
                if self.settings.cookie_secure:
                    headers.append((b'strict-transport-security', b'max-age=31536000'))
                message['headers'] = headers
            await send(message)
        await self.app(scope, receive, secure_send)


def create_app(settings=None, redis_client=None, upstream_transport=None):
    settings = settings or get_settings()
    if not settings.secret_key:
        settings.secret_key = SecretStr(load_or_create_key(Path(settings.data_dir) / 'master.key'))
    secret_store = SecretStore(settings.secret_key.get_secret_value(), Path(settings.data_dir) / 'integrations.json')

    @asynccontextmanager
    async def lifespan(app):
        app.state.redis = redis_client or redis.from_url(settings.redis_url)
        await app.state.redis.ping()
        app.state.jellyfin = JellyfinClient(settings, app.state.redis, upstream_transport)
        app.state.auth = AuthService(settings, app.state.redis, app.state.jellyfin)
        try:
            yield
        finally:
            await app.state.jellyfin.close()
            await app.state.redis.aclose()

    app = FastAPI(title='Jishflix Cinematic', version='1.0.0', lifespan=lifespan,
                  description='Cinematic Jellyfin gateway. Complete upstream API is available under /api/jellyfin/.')
    app.state.settings = settings
    app.state.secrets = secret_store
    app.state.upstream_transport = upstream_transport
    app.state.seerr = SeerrClient(secret_store, upstream_transport)
    app.state.whisparr = WhisparrClient(secret_store, upstream_transport)
    app.add_middleware(SecurityHeaders, settings=settings)

    @app.exception_handler(RedisError)
    async def cache_unavailable(request, exc):
        logger.error('Redis unavailable: %s', type(exc).__name__)
        return JSONResponse({'detail': 'Session storage is unavailable'}, status_code=503)

    @app.get('/health/live', include_in_schema=False)
    async def live():
        return {'status': 'ok'}

    @app.get('/health/ready', include_in_schema=False)
    async def ready():
        await app.state.redis.ping()
        await app.state.jellyfin.request('GET', 'System/Info/Public')
        return {'status': 'ready'}

    for router in (auth.router, media.router, playback.router, livetv.router, proxy.router, integrations.router):
        app.include_router(router)

    mcp = create_mcp(app.state, settings)
    guard = MCPGuard(mcp.sse_app(), app.state)
    app.state.mcp = mcp
    dist = Path(settings.frontend_dist).resolve()

    async def frontend_or_mcp(scope, receive, send):
        if scope['type'] != 'http':
            return
        path = scope['path']
        if path == '/sse' or path.startswith('/messages/'):
            return await guard(scope, receive, send)
        if path.startswith(('/api/', '/health/', '/messages')) or scope['method'] not in ('GET', 'HEAD'):
            return await JSONResponse({'detail': 'Not found'}, status_code=404)(scope, receive, send)
        target = (dist / path.lstrip('/')).resolve()
        if not target.is_relative_to(dist):
            raise HTTPException(404)
        if not target.is_file():
            target = dist / 'index.html'
        if not target.exists():
            return await JSONResponse({'detail': 'Build the frontend or run the Vite development server'}, status_code=503)(scope, receive, send)
        await FileResponse(target)(scope, receive, send)

    app.mount('/', frontend_or_mcp)
    return app

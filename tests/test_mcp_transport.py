"""Exercise the actual SSE wire protocol with the official SDK, not tool mocks."""
import asyncio
import socket

import httpx
import uvicorn
from fakeredis.aioredis import FakeRedis
from mcp import ClientSession
from mcp.client.sse import sse_client

from backend.config import Settings
from backend.main import create_app


async def test_sse_initialize_tools_revocation_and_identity(tmp_path):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    calls = []
    is_admin = False

    def upstream(request):
        calls.append(request)
        path = request.url.path
        if path == '/Users/Me':
            return httpx.Response(200, json={'Id': 'alice', 'Policy': {'IsAdministrator': is_admin}})
        if path == '/Sessions':
            return httpx.Response(200, json=[{'Id': 'a', 'UserId': 'alice', 'RemoteEndPoint': 'secret'}, {'Id': 'b', 'UserId': 'bob'}])
        if path == '/api/v1/search':
            return httpx.Response(200, json={'results': [{'id': 603, 'mediaType': 'movie', 'title': 'The Matrix'}]})
        if path == '/api/v1/request':
            return httpx.Response(200, json={'id': 42})
        if path == '/api/v3/series/lookup':
            return httpx.Response(200, json=[{'title': 'Example Studio', 'foreignId': 'abc'}])
        if path == '/api/v3/rootfolder':
            return httpx.Response(200, json=[{'id': 1, 'path': '/data/adult'}])
        if path == '/api/v3/qualityprofile':
            return httpx.Response(200, json=[{'id': 1, 'name': 'HD'}])
        if path == '/api/v3/series':
            return httpx.Response(200, json={'id': 7, 'title': 'Example Studio'})
        return httpx.Response(200, json={'Items': [{'Id': 'film', 'Name': 'A Film'}]})

    settings = Settings(secret_key='mcp-test-key-' * 4, public_url=origin, jellyfin_url='http://upstream',
                         cookie_secure=False, data_dir=str(tmp_path))
    app = create_app(settings, FakeRedis(), httpx.MockTransport(upstream))
    app.state.secrets.save('seerr', 'http://seerr', 'seerr-key')
    app.state.secrets.save('whisparr', 'http://whisparr', 'whisparr-key')
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='on', ws='none'))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(.02)
        assert server.started
        token, _ = await app.state.auth.create({'AccessToken': 'alice-token', 'User': {'Id': 'alice'}}, 'device', kind='mcp')
        other, _ = await app.state.auth.create({'AccessToken': 'bob-token', 'User': {'Id': 'bob'}}, 'other', kind='mcp')
        headers = {'Authorization': 'Bearer ' + token}
        async with sse_client(origin + '/sse', headers=headers) as streams:
            async with ClientSession(*streams) as client:
                result = await client.initialize()
                assert result.serverInfo.name == 'Jishflix Cinematic'
                names = {t.name for t in (await client.list_tools()).tools}
                assert names == {'search_media_library', 'get_continue_watching', 'check_stream_status',
                                  'trigger_media_sync', 'request_movie_or_show', 'request_adult_scene'}
                found = await client.call_tool('search_media_library', {'query': 'film'})
                assert not found.isError
                assert calls[-1].url.params['UserId'] == 'alice'
                assert 'alice-token' in calls[-1].headers['authorization']
                sessions = await client.call_tool('check_stream_status')
                assert 'secret' not in str(sessions.content)
                denied = await client.call_tool('trigger_media_sync')
                assert denied.isError
                assert not any(r.url.path == '/Library/Refresh' for r in calls)
                assert (await client.call_tool('request_movie_or_show', {'title': 'Matrix'})).isError
                assert (await client.call_tool('request_adult_scene', {'title': 'Example'})).isError
                assert not any(r.url.path in ('/api/v1/request', '/api/v3/series') for r in calls)
                is_admin = True
                requested = await client.call_tool('request_movie_or_show', {'title': 'Matrix'})
                assert not requested.isError
                assert any(r.url.path == '/api/v1/request' for r in calls)
                added = await client.call_tool('request_adult_scene', {'title': 'Example'})
                assert not added.isError
                assert any(r.url.path == '/api/v3/series' for r in calls)
                session_keys = [key async for key in app.state.redis.scan_iter('mcp:*')]
                assert len(session_keys) == 1
                sid = session_keys[0].decode().split(':', 1)[1]
                async with httpx.AsyncClient() as raw:
                    hijack = await raw.post(origin + '/messages/?session_id=' + sid, headers={'Authorization': 'Bearer ' + other}, json={})
                    assert hijack.status_code == 403
                # Revoke underlying session but leave transport open: tool execution must re-check identity.
                await app.state.auth.revoke(token)
                # POST authorization also refuses revoked tokens, so prove the per-tool path separately.
                from backend.services.mcp_server import identity
                marker = identity.set(token)
                try:
                    tool = await app.state.mcp._tool_manager.get_tool('get_continue_watching').run({})
                    assert tool is None, 'Revoked token unexpectedly authorized'
                except Exception as exc:
                    assert 'Session expired' in str(exc)
                finally:
                    identity.reset(marker)
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()

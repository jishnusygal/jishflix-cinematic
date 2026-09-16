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


async def test_sse_initialize_tools_revocation_and_identity():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    calls = []

    def upstream(request):
        calls.append(request)
        if request.url.path == '/Users/Me':
            return httpx.Response(200, json={'Id': 'alice', 'Policy': {'IsAdministrator': False}})
        if request.url.path == '/Sessions':
            return httpx.Response(200, json=[{'Id': 'a', 'UserId': 'alice', 'RemoteEndPoint': 'secret'}, {'Id': 'b', 'UserId': 'bob'}])
        return httpx.Response(200, json={'Items': [{'Id': 'film', 'Name': 'A Film'}]})

    app = create_app(Settings(secret_key='mcp-test-key-' * 4, public_url=origin, jellyfin_url='http://upstream', cookie_secure=False), FakeRedis(), httpx.MockTransport(upstream))
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
                assert names == {'search_media_library', 'get_continue_watching', 'check_stream_status', 'trigger_media_sync'}
                found = await client.call_tool('search_media_library', {'query': 'film'})
                assert not found.isError
                assert calls[-1].url.params['UserId'] == 'alice'
                assert 'alice-token' in calls[-1].headers['authorization']
                sessions = await client.call_tool('check_stream_status')
                assert 'secret' not in str(sessions.content)
                denied = await client.call_tool('trigger_media_sync')
                assert denied.isError
                assert not any(r.url.path == '/Library/Refresh' for r in calls)
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

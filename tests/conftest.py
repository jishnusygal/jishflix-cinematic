import httpx
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from backend.config import Settings
from backend.main import create_app

USER = {'Id': 'alice', 'Name': 'Alice', 'Policy': {'IsAdministrator': True}}
ITEM = {'Id': 'movie', 'Name': 'Test Movie', 'Type': 'Movie'}


@pytest_asyncio.fixture
async def environment():
    calls = []

    def upstream(request):
        calls.append(request)
        path = request.url.path
        if path.endswith('/Users/AuthenticateByName'):
            return httpx.Response(200, json={'AccessToken': 'upstream-private-token', 'User': USER})
        if path.endswith('/Users/Me'):
            return httpx.Response(200, json=USER)
        if path.endswith('/System/Info/Public'):
            return httpx.Response(200, json={'ServerName': 'Fixture'})
        if path.endswith('/PlaybackInfo'):
            return httpx.Response(200, json={'PlaySessionId': 'play-1', 'MediaSources': [{
                'Id': 'source-1', 'SupportsDirectPlay': True, 'MediaStreams': [
                    {'Type': 'Video', 'Index': 0, 'Codec': 'h264'}, {'Type': 'Audio', 'Index': 1, 'Codec': 'aac'}]}]})
        if path.endswith('/master.m3u8'):
            return httpx.Response(200, text='#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key?api_key=secret"\nchild/list.m3u8?api_key=secret\n', headers={'Content-Type': 'application/vnd.apple.mpegurl'})
        if path.endswith('/stream'):
            return httpx.Response(206, content=b'abcd', headers={'Content-Range': 'bytes 0-3/20', 'Accept-Ranges': 'bytes', 'Content-Type': 'video/mp4'})
        if path.endswith('/denied'):
            return httpx.Response(403, json={'detail': 'denied'})
        if path.endswith('/Sessions'):
            return httpx.Response(200, json=[{'Id': 's1', 'UserId': 'alice', 'DeviceName': 'Browser', 'RemoteEndPoint': 'private', 'NowPlayingItem': ITEM}, {'Id': 's2', 'UserId': 'bob'}])
        if path.endswith('/Latest'):
            return httpx.Response(200, json=[ITEM])
        if request.method != 'GET':
            return httpx.Response(204)
        return httpx.Response(200, json={'Items': [ITEM], 'TotalRecordCount': 1})

    settings = Settings(secret_key='test-secret-' * 4, jellyfin_url='http://jellyfin/base', public_url='http://testserver', cookie_secure=False)
    redis = FakeRedis()
    app = create_app(settings, redis, httpx.MockTransport(upstream))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver',
                                   headers={'X-Requested-With': 'Jishflix'}) as client:
            yield app, client, calls


@pytest_asyncio.fixture
async def logged_in(environment):
    app, client, calls = environment
    result = await client.post('/api/auth/login', json={'username': 'alice', 'password': 'test'})
    assert result.status_code == 200
    return app, client, calls

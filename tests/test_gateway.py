import json
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from backend.services.auth_service import COOKIE


async def test_authentication_required(environment):
    _, client, _ = environment
    for path in ['/api/media/home', '/api/jellyfin/Users', '/api/livetv/channels']:
        assert (await client.get(path)).status_code == 401


async def test_cookie_secure_attributes_and_no_token_leak(environment):
    app, client, _ = environment
    response = await client.post('/api/auth/login', json={'username': 'alice', 'password': 'test'})
    assert response.json()['Name'] == 'Alice'
    assert 'token' not in response.text.lower()
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=strict' in response.headers['set-cookie']
    token = client.cookies[COOKIE]
    stored = await app.state.redis.get(app.state.auth.key(token))
    assert b'upstream-private-token' not in stored
    assert (await app.state.auth.resolve(token))['token'] == 'upstream-private-token'


async def test_csrf_rejects_missing_header_and_foreign_origin(environment):
    _, client, _ = environment
    for headers in [{'X-Requested-With': ''}, {'Origin': 'https://evil.example'}]:
        result = await client.post('/api/auth/login', json={'username': 'alice', 'password': ''}, headers=headers)
        assert result.status_code == 403


async def test_home_and_user_scoped_cache(logged_in):
    app, client, calls = logged_in
    result = await client.get('/api/media/home')
    assert result.status_code == 200
    assert set(result.json()) == {'continue', 'next_up', 'recent', 'favorites', 'discover'}
    count = len(calls)
    await client.get('/api/media/home')
    assert len(calls) == count
    session = await app.state.auth.resolve(client.cookies[COOKIE])
    other = {**session, 'user_id': 'bob', 'token': 'bob-secret'}
    await app.state.jellyfin.request('GET', 'Shows/NextUp', other, params={'UserId': 'bob'}, cache=True)
    assert len(calls) == count + 1


async def test_mutation_invalidates_cache(logged_in):
    _, client, calls = logged_in
    await client.get('/api/media/home')
    await client.post('/api/media/items/movie/favorite')
    count = len(calls)
    await client.get('/api/media/home')
    assert len(calls) == count + 5


async def test_proxy_range_and_token_stripping(logged_in):
    _, client, calls = logged_in
    result = await client.get('/api/jellyfin/Videos/movie/stream?api_key=attacker&static=true', headers={'Range': 'bytes=0-3'})
    assert result.status_code == 206
    assert result.content == b'abcd'
    assert result.headers['content-range'] == 'bytes 0-3/20'
    assert calls[-1].headers['range'] == 'bytes=0-3'
    assert 'api_key' not in calls[-1].url.params
    assert 'upstream-private-token' in calls[-1].headers['authorization']


async def test_proxy_preserves_repeated_query_and_body(logged_in):
    _, client, calls = logged_in
    result = await client.post('/api/jellyfin/Custom/Action?x=1&x=2', content=b'{"custom":true}', headers={'Content-Type': 'application/json'})
    assert result.status_code == 204
    assert calls[-1].url.params.get_list('x') == ['1', '2']
    assert calls[-1].content == b'{"custom":true}'


async def test_hls_rewrite(logged_in):
    _, client, _ = logged_in
    result = await client.get('/api/jellyfin/Videos/movie/master.m3u8')
    assert result.status_code == 200
    assert 'api_key' not in result.text
    assert 'URI="/api/jellyfin/Videos/movie/key"' in result.text
    assert '/api/jellyfin/Videos/movie/child/list.m3u8' in result.text


@pytest.mark.parametrize('path', ['../Users', '%2e%2e/Users', '%252e%252e/Users', '//evil/Users', 'http://evil', 'Users\\Admin', 'Users?api_key=x'])
async def test_path_rejects_traversal(environment, path):
    app, _, _ = environment
    with pytest.raises(HTTPException):
        app.state.jellyfin.safe_path(path)


async def test_media_uri_rejects_external_host(environment):
    app, _, _ = environment
    with pytest.raises(HTTPException):
        app.state.jellyfin.local_url('https://evil.example/video')
    assert app.state.jellyfin.local_url('/base/Videos/1/stream?api_key=secret&static=true') == '/api/jellyfin/Videos/1/stream?static=true'


async def test_playback_negotiation_and_progress(logged_in):
    _, client, calls = logged_in
    response = await client.post('/api/playback/movie/info', json={'start_ticks': 120000000})
    assert response.status_code == 200
    info = response.json()
    assert info['url'].startswith('/api/jellyfin/Videos/movie/stream?')
    assert 'token' not in info['url']
    negotiated = json.loads(calls[-1].content)
    assert negotiated['UserId'] == 'alice'
    assert negotiated['DeviceProfile']['TranscodingProfiles'][0]['Protocol'] == 'hls'
    progress = {'ItemId': 'movie', 'MediaSourceId': info['source_id'], 'PlaySessionId': info['play_session_id'], 'PositionTicks': 140000000}
    for event in ['start', 'progress', 'stop']:
        assert (await client.post('/api/playback/events/' + event, json=progress)).status_code == 204
    assert calls[-1].url.path.endswith('/Sessions/Playing/Stopped')
    progress['PositionTicks'] = -1
    assert (await client.post('/api/playback/events/progress', json=progress)).status_code == 422


async def test_transcode_stop_closes_live_stream(logged_in):
    _, client, calls = logged_in
    response = await client.post('/api/playback/events/stop', json={'ItemId': 'live', 'MediaSourceId': 's',
        'PlaySessionId': 'p', 'PositionTicks': 0, 'PlayMethod': 'Transcode', 'LiveStreamId': 'live-1'})
    assert response.status_code == 204
    assert calls[-2].url.path.endswith('/LiveStreams/Close')
    assert calls[-1].url.path.endswith('/Videos/ActiveEncodings')


async def test_mcp_child_token_revoked_on_logout(logged_in):
    app, client, _ = logged_in
    result = await client.post('/api/auth/mcp-token')
    token = result.json()['token']
    assert (await app.state.auth.resolve(token))['kind'] == 'mcp'
    assert (await client.post('/api/auth/logout')).status_code == 204
    with pytest.raises(HTTPException):
        await app.state.auth.resolve(token)
    assert (await client.get('/api/auth/me')).status_code == 401


async def test_mcp_requires_dedicated_token_and_binds_messages(logged_in):
    _, client, _ = logged_in
    assert (await client.get('/sse')).status_code == 401
    browser = client.cookies[COOKIE]
    assert (await client.get('/sse', headers={'Authorization': 'Bearer ' + browser})).status_code == 403
    token = (await client.post('/api/auth/mcp-token')).json()['token']
    assert (await client.post('/messages/?session_id=unknown', headers={'Authorization': 'Bearer ' + token}, json={})).status_code == 403


async def test_rate_limit(environment):
    app, _, _ = environment
    for _ in range(2):
        await app.state.auth.rate_limit('ip', limit=2)
    with pytest.raises(HTTPException) as error:
        await app.state.auth.rate_limit('ip', limit=2)
    assert error.value.status_code == 429


async def test_configure_iptv_requires_configuration(logged_in):
    _, client, _ = logged_in
    result = await client.post('/api/livetv/configure-iptv')
    assert result.status_code == 422


async def test_configure_iptv_derives_urls_from_gateway(logged_in):
    app, client, calls = logged_in
    app.state.secrets.save('iptv_gtw', 'http://iptv-gtw:8000', 'gateway-export-token')
    result = await client.post('/api/livetv/configure-iptv')
    assert result.status_code == 200
    tuner_body = json.loads(next(c for c in calls if c.url.path.endswith('/LiveTv/TunerHosts')).content)
    assert tuner_body['Url'] == 'http://iptv-gtw:8000/playlist.m3u?token=gateway-export-token'
    listing_body = json.loads(next(c for c in calls if c.url.path.endswith('/LiveTv/ListingProviders')).content)
    assert listing_body['Path'] == 'http://iptv-gtw:8000/epg.xml?token=gateway-export-token'


async def test_integrations_status_and_save_roundtrip(logged_in):
    app, client, _ = logged_in
    before = (await client.get('/api/integrations/status')).json()
    assert before['seerr'] == {'configured': False, 'url': None}
    result = await client.post('/api/integrations/seerr', json={'url': 'http://seerr', 'secret': 'seerr-key'})
    assert result.status_code == 200
    after = (await client.get('/api/integrations/status')).json()
    assert after['seerr'] == {'configured': True, 'url': 'http://seerr'}
    assert 'seerr-key' not in str(after)


async def test_integrations_save_tests_iptv_gtw_with_real_playlist_response(logged_in):
    app, client, _ = logged_in
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(200, text='#EXTM3U\n', headers={'Content-Type': 'audio/x-mpegurl'})

    app.state.upstream_transport = httpx.MockTransport(upstream)
    result = await client.post('/api/integrations/iptv_gtw', json={'url': 'http://iptv-gtw:8000', 'secret': 'export-token'})
    assert result.status_code == 200
    assert calls[-1].url.path == '/playlist.m3u'
    assert calls[-1].url.params['token'] == 'export-token'
    assert (await client.get('/api/integrations/status')).json()['iptv_gtw'] == {'configured': True, 'url': 'http://iptv-gtw:8000'}


async def test_integrations_save_rejects_failed_connection_test(logged_in):
    app, client, _ = logged_in
    app.state.seerr.transport = httpx.MockTransport(lambda request: httpx.Response(401, json={'detail': 'bad key'}))
    result = await client.post('/api/integrations/seerr', json={'url': 'http://seerr', 'secret': 'wrong-key'})
    assert result.status_code == 401
    assert (await client.get('/api/integrations/status')).json()['seerr'] == {'configured': False, 'url': None}


async def test_upstream_timeout_and_status(environment):
    app, _, _ = environment
    with pytest.raises(HTTPException) as error:
        await app.state.jellyfin.request('GET', 'denied')
    assert error.value.status_code == 403
    async def timeout(request):
        raise httpx.ReadTimeout('timeout', request=request)
    app.state.jellyfin.http._transport = httpx.MockTransport(timeout)
    with pytest.raises(HTTPException) as error:
        await app.state.jellyfin.request('GET', 'Items')
    assert error.value.status_code == 504


async def test_health_and_spa(environment):
    _, client, _ = environment
    assert (await client.get('/health/ready')).json() == {'status': 'ready'}
    assert (await client.get('/api/does-not-exist')).status_code == 404
    result = await client.get('/')
    assert result.headers['x-content-type-options'] == 'nosniff'
    assert 'frame-src https://www.youtube-nocookie.com' in result.headers['content-security-policy']


async def test_static_assets_cached_but_index_revalidates(environment):
    _, client, _ = environment
    assert (await client.get('/')).headers['cache-control'] == 'no-cache'
    assert (await client.get('/some/unknown/spa/route')).headers['cache-control'] == 'no-cache'
    asset = next((Path('frontend/dist/assets').glob('index-*.js')), None)
    assert asset, 'frontend must be built for this test (npm run build)'
    result = await client.get(f'/assets/{asset.name}')
    assert result.status_code == 200
    assert result.headers['cache-control'] == 'public, max-age=31536000, immutable'

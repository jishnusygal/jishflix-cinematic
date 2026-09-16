"""Pooled upstream transport. Never follow redirects or accept caller-selected hosts."""
import hashlib
import json
import re
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit

import httpx
from fastapi import HTTPException

from backend.config import Settings


class JellyfinClient:
    def __init__(self, settings: Settings, redis, transport=None):
        self.settings = settings
        self.redis = redis
        self.http = httpx.AsyncClient(
            base_url=settings.jellyfin_url + '/', transport=transport,
            timeout=httpx.Timeout(30, connect=10, read=120),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=40),
            follow_redirects=False,
        )

    @staticmethod
    def safe_path(path: str) -> str:
        decoded = path
        for _ in range(5):
            newer = unquote(decoded)
            if newer == decoded:
                break
            decoded = newer
        if ('%' in decoded or '\\' in decoded or '?' in decoded or '#' in decoded
                or ':' in decoded or any(part in ('.', '..') for part in decoded.split('/'))
                or decoded.startswith('//') or any(ord(c) < 32 for c in decoded)):
            raise HTTPException(400, 'Invalid upstream path')
        return path.lstrip('/')

    @staticmethod
    def headers(session=None):
        device = session['device_id'] if session else 'jishflix-login'
        value = f'MediaBrowser Client="Jishflix Cinematic", Device="Web", DeviceId="{device}", Version="1.0.0"'
        if session:
            value += f', Token="{session["token"]}"'
        return {'Authorization': value, 'Accept-Encoding': 'identity'}

    async def request(self, method: str, path: str, session=None, *, params=None, body=None, cache=False):
        path = self.safe_path(path)
        key = None
        if cache and method == 'GET' and self.settings.cache_ttl:
            generation = await self.redis.get('cache:generation') or b'0'
            digest = hashlib.sha256(json.dumps([path, params, session, str(generation)], sort_keys=True).encode()).hexdigest()
            key = 'response:' + digest
            cached = await self.redis.get(key)
            if cached:
                return json.loads(cached)
        try:
            result = await self.http.request(method, path, headers=self.headers(session), params=params, json=body)
        except httpx.TimeoutException as exc:
            raise HTTPException(504, 'Jellyfin timed out') from exc
        except httpx.RequestError as exc:
            raise HTTPException(502, 'Jellyfin is unavailable') from exc
        if result.is_error or result.is_redirect:
            status = result.status_code if result.is_error else 502
            raise HTTPException(status, f'Jellyfin rejected the request ({result.status_code})')
        data = result.json() if result.content else None
        if key:
            await self.redis.setex(key, self.settings.cache_ttl, json.dumps(data))
        if method != 'GET':
            await self.redis.incr('cache:generation')
        return data

    def local_url(self, url: str, base_path: str = '') -> str:
        """Translate an upstream relative/absolute URI into the authenticated proxy."""
        base = self.settings.jellyfin_url + '/'
        resolved = urlsplit(urljoin(base + base_path, url))
        upstream = urlsplit(base)
        if (resolved.scheme, resolved.netloc) != (upstream.scheme, upstream.netloc):
            raise HTTPException(502, 'Upstream returned an external media URI')
        prefix = upstream.path.rstrip('/') + '/'
        if not resolved.path.startswith(prefix):
            raise HTTPException(502, 'Upstream media URI escaped the configured base path')
        path = self.safe_path(resolved.path[len(prefix):])
        query = [(k, v) for k, v in parse_qsl(resolved.query, keep_blank_values=True)
                 if k.lower() not in ('api_key', 'apikey', 'access_token')]
        return '/api/jellyfin/' + path + ('?' + urlencode(query) if query else '')

    def rewrite_playlist(self, text: str, path: str) -> str:
        lines = []
        for line in text.splitlines():
            if line and not line.startswith('#'):
                line = self.local_url(line.strip(), path)
            elif 'URI="' in line:
                line = re.sub(r'URI="([^"]+)"', lambda m: 'URI="' + self.local_url(m[1], path) + '"', line)
            lines.append(line)
        return '\n'.join(lines) + '\n'

    async def close(self):
        await self.http.aclose()

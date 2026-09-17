"""Base for thin, API-key-authenticated clients to optional upstream services.

Credentials are re-read from the SecretStore on every call rather than cached
at construction, so configuring a service through the setup wizard takes
effect immediately, with no restart. That also rules out a persistent pooled
client (its base_url would go stale the moment credentials change), so each
call opens a short-lived client instead. That's an acceptable tradeoff for
these low-frequency, admin-triggered actions.
"""
import httpx
from fastapi import HTTPException


async def probe(display_name: str, transport, method: str, url: str, path: str, **kwargs):
    """Make one request to an upstream service, translating transport/HTTP errors uniformly."""
    async with httpx.AsyncClient(base_url=url.rstrip('/') + '/', transport=transport,
                                  timeout=httpx.Timeout(30, connect=10)) as client:
        try:
            response = await client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise HTTPException(502, f'{display_name} is unavailable') from exc
    if response.is_error:
        raise HTTPException(response.status_code, f'{display_name} rejected the request ({response.status_code})')
    try:
        return response.json()
    except ValueError:
        return None


class ApiKeyClient:
    header = 'X-Api-Key'
    service = 'upstream'
    display_name = 'Upstream service'

    def __init__(self, store, transport=None):
        self.store = store
        self.transport = transport

    @property
    def configured(self) -> bool:
        url, secret = self.store.get(self.service)
        return bool(url and secret)

    async def _probe(self, url: str, secret: str, method: str, path: str, **kwargs):
        return await probe(self.display_name, self.transport, method, url, path, headers={self.header: secret}, **kwargs)

    async def _call(self, method: str, path: str, **kwargs):
        url, secret = self.store.get(self.service)
        if not url or not secret:
            raise HTTPException(422, f'{self.display_name} is not configured')
        return await self._probe(url, secret, method, path, **kwargs)

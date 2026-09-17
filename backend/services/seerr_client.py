"""Thin client for searching and creating media requests through a Seerr instance."""
from backend.services.api_key_client import ApiKeyClient


class SeerrClient(ApiKeyClient):
    service = 'seerr'
    display_name = 'Seerr'

    async def test_connection(self, url: str, secret: str) -> None:
        await self._probe(url, secret, 'GET', 'api/v1/search', params={'query': 'test'})

    async def search(self, query: str) -> list[dict]:
        result = await self._call('GET', 'api/v1/search', params={'query': query})
        return result.get('results', [])

    async def request_media(self, media_type: str, media_id: int) -> dict:
        return await self._call('POST', 'api/v1/request', json={'mediaType': media_type, 'mediaId': media_id})

"""Thin client for searching and adding content through Whisparr v3.

Whisparr v3 uses Sonarr's series/episode data model (a "series" here is a studio
or site, with releases tracked as episodes), so adding content follows Sonarr's
lookup-then-add flow: enrich a /series/lookup result with the management fields
Whisparr requires and POST it back to /series.
"""
import asyncio

from fastapi import HTTPException

from backend.services.api_key_client import ApiKeyClient


class WhisparrClient(ApiKeyClient):
    service = 'whisparr'
    display_name = 'Whisparr'

    async def test_connection(self, url: str, secret: str) -> None:
        await self._probe(url, secret, 'GET', 'api/v3/system/status')

    async def lookup(self, term: str) -> list[dict]:
        return await self._call('GET', 'api/v3/series/lookup', params={'term': term})

    async def add(self, series: dict) -> dict:
        root_folders, profiles = await asyncio.gather(
            self._call('GET', 'api/v3/rootfolder'), self._call('GET', 'api/v3/qualityprofile'))
        if not root_folders:
            raise HTTPException(422, 'Whisparr has no root folder configured')
        if not profiles:
            raise HTTPException(422, 'Whisparr has no quality profile configured')
        # No UI exists to pick a profile/folder for this tool; a single-admin
        # deployment typically only has one of each, so take the first.
        body = {**series, 'qualityProfileId': profiles[0]['id'], 'rootFolderPath': root_folders[0]['path'],
                'monitored': True, 'addOptions': {'searchForMissingEpisodes': True}}
        return await self._call('POST', 'api/v3/series', json=body)

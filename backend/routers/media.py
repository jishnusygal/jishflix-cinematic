import asyncio
from typing import Annotated

from fastapi import APIRouter, Query, Request

from backend.services.auth_service import Session

router = APIRouter(prefix='/api/media', tags=['Media'])
FIELDS = 'Overview,Genres,MediaSources,Chapters,PrimaryImageAspectRatio,DateCreated,RemoteTrailers'


@router.get('/home')
async def home(request: Request, session: Session):
    client = request.app.state.jellyfin
    uid = session['user_id']
    paths = [('continue', f'Users/{uid}/Items/Resume', {'Limit': 16, 'MediaTypes': 'Video', 'Fields': FIELDS}),
             ('next_up', 'Shows/NextUp', {'UserId': uid, 'Limit': 16, 'Fields': FIELDS}),
             ('recent', f'Users/{uid}/Items/Latest', {'Limit': 20, 'Fields': FIELDS}),
             ('favorites', 'Items', {'UserId': uid, 'Recursive': True, 'IsFavorite': True, 'Limit': 20, 'Fields': FIELDS}),
             ('discover', 'Items', {'UserId': uid, 'Recursive': True, 'IncludeItemTypes': 'Movie,Series',
                                  'SortBy': 'CommunityRating', 'SortOrder': 'Descending', 'Limit': 20, 'Fields': FIELDS})]
    results = await asyncio.gather(*(client.request('GET', path, session, params=params, cache=True)
                                    for _, path, params in paths))
    return {key: (value.get('Items', []) if isinstance(value, dict) else value)
            for (key, _, _), value in zip(paths, results)}


@router.get('/libraries')
async def libraries(request: Request, session: Session):
    return await request.app.state.jellyfin.request('GET', f'Users/{session["user_id"]}/Views', session, cache=True)


@router.get('/items')
async def items(request: Request, session: Session, search: str = '', types: str = '', parent: str = '',
                start: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 40,
                sort: str = 'SortName', order: str = 'Ascending', genre: str = '', favorite: bool = False):
    params = {'UserId': session['user_id'], 'StartIndex': start, 'Limit': limit, 'SortBy': sort,
              'SortOrder': order, 'Recursive': True, 'Fields': FIELDS, 'EnableTotalRecordCount': True}
    for key, value in [('SearchTerm', search), ('IncludeItemTypes', types), ('ParentId', parent), ('Genres', genre)]:
        if value:
            params[key] = value
    if favorite:
        params['IsFavorite'] = True
    return await request.app.state.jellyfin.request('GET', 'Items', session, params=params, cache=True)


@router.get('/items/{item_id}')
async def item(item_id: str, request: Request, session: Session):
    return await request.app.state.jellyfin.request('GET', f'Users/{session["user_id"]}/Items/{item_id}', session, params={'Fields': FIELDS})


@router.get('/items/{item_id}/children')
async def children(item_id: str, request: Request, session: Session):
    return await request.app.state.jellyfin.request('GET', 'Items', session, params={
        'UserId': session['user_id'], 'ParentId': item_id, 'SortBy': 'ParentIndexNumber,IndexNumber,SortName',
        'Fields': FIELDS, 'Limit': 100})


@router.post('/items/{item_id}/favorite')
async def favorite_item(item_id: str, request: Request, session: Session):
    return await request.app.state.jellyfin.request('POST', f'Users/{session["user_id"]}/FavoriteItems/{item_id}', session)


@router.delete('/items/{item_id}/favorite')
async def unfavorite_item(item_id: str, request: Request, session: Session):
    return await request.app.state.jellyfin.request('DELETE', f'Users/{session["user_id"]}/FavoriteItems/{item_id}', session)

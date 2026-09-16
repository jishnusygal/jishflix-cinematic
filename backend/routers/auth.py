import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.services.auth_service import COOKIE, Session, credential

router = APIRouter(prefix='/api/auth', tags=['Authentication'])


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(max_length=1024)


class TokenExchange(BaseModel):
    token: str = Field(min_length=1, max_length=4096, pattern=r'^[A-Za-z0-9._~+/-]+={0,2}$')


class QuickSecret(BaseModel):
    secret: str = Field(min_length=1, max_length=256)


async def establish(request, response, result, device):
    old = credential(request)
    token, session = await request.app.state.auth.create(result, device)
    if old:
        await request.app.state.auth.revoke(old)
    settings = request.app.state.settings
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.cookie_secure,
                        samesite='strict', max_age=settings.session_ttl, path='/')
    return session['user']


@router.post('/login')
async def login(data: Login, request: Request, response: Response):
    await request.app.state.auth.rate_limit('login:' + request.client.host)
    device = secrets.token_hex(16)
    result = await request.app.state.jellyfin.request('POST', 'Users/AuthenticateByName',
        {'token': '', 'device_id': device}, body={'Username': data.username, 'Pw': data.password})
    return await establish(request, response, result, device)


@router.post('/exchange')
async def exchange(data: TokenExchange, request: Request, response: Response):
    await request.app.state.auth.rate_limit('login:' + request.client.host)
    device = secrets.token_hex(16)
    user = await request.app.state.jellyfin.request('GET', 'Users/Me', {'token': data.token, 'device_id': device})
    return await establish(request, response, {'AccessToken': data.token, 'User': user}, device)


@router.get('/me')
async def me(request: Request, session: Session):
    return await request.app.state.jellyfin.request('GET', 'Users/Me', session)


@router.post('/logout', status_code=204)
async def logout(request: Request, response: Response, session: Session):
    await request.app.state.auth.revoke(credential(request))
    response.delete_cookie(COOKIE, path='/')
    # Child MCP tokens share this upstream token and are invalidated by parent revocation.
    try:
        await request.app.state.jellyfin.request('POST', 'Sessions/Logout', session)
    except HTTPException:
        pass


@router.post('/mcp-token')
async def mcp_token(request: Request, session: Session):
    if session['kind'] != 'browser':
        raise HTTPException(403, 'Sign in through the browser to create an MCP token')
    token, _ = await request.app.state.auth.create(
        {'AccessToken': session['token'], 'User': session['user']}, session['device_id'],
        kind='mcp', parent=request.app.state.auth.key(credential(request)))
    return {'token': token, 'expires_in': request.app.state.settings.session_ttl}


@router.post('/quick-connect')
async def quick_start(request: Request):
    await request.app.state.auth.rate_limit('quick:' + request.client.host)
    return await request.app.state.jellyfin.request('POST', 'QuickConnect/Initiate')


@router.post('/quick-connect/poll')
async def quick_poll(data: QuickSecret, request: Request, response: Response):
    await request.app.state.auth.rate_limit('quick-poll:' + request.client.host, limit=40)
    result = await request.app.state.jellyfin.request('GET', 'QuickConnect/Connect', params={'secret': data.secret})
    if not result.get('Authenticated'):
        return {'pending': True}
    device = secrets.token_hex(16)
    result = await request.app.state.jellyfin.request('POST', 'Users/AuthenticateWithQuickConnect',
        {'token': '', 'device_id': device}, body={'Secret': data.secret})
    return {'user': await establish(request, response, result, device)}

import base64
import hashlib
import json
import secrets
from typing import Annotated

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request

from backend.config import Settings

COOKIE = 'jishflix_session'


class AuthService:
    def __init__(self, settings: Settings, redis, jellyfin):
        self.settings, self.redis, self.jellyfin = settings, redis, jellyfin
        self.cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.get_secret_value().encode()).digest()))

    @staticmethod
    def key(token: str) -> str:
        return 'session:' + hashlib.sha256(token.encode()).hexdigest()

    async def create(self, upstream: dict, device_id: str, *, kind='browser', parent=None):
        token = secrets.token_urlsafe(32)
        session = {'token': upstream['AccessToken'], 'user_id': upstream['User']['Id'],
                   'user': upstream['User'], 'device_id': device_id, 'kind': kind, 'parent': parent}
        await self.redis.setex(self.key(token), self.settings.session_ttl, self.cipher.encrypt(json.dumps(session).encode()))
        return token, session

    async def resolve(self, token: str):
        if not token or len(token) > 256:
            raise HTTPException(401, 'Sign in to continue')
        value = await self.redis.get(self.key(token))
        if not value:
            raise HTTPException(401, 'Session expired. Sign in again')
        try:
            session = json.loads(self.cipher.decrypt(value))
        except (InvalidToken, ValueError) as exc:
            raise HTTPException(401, 'Invalid session') from exc
        if session.get('parent') and not await self.redis.exists(session['parent']):
            raise HTTPException(401, 'Parent session has expired')
        return session

    async def revoke(self, token):
        await self.redis.delete(self.key(token))

    async def rate_limit(self, identity: str, limit=15, window=60):
        key = 'rate:' + hashlib.sha256(identity.encode()).hexdigest()
        # Atomic expiry prevents immortal counters after worker cancellation.
        async with self.redis.pipeline(transaction=True) as pipe:
            count, _ = await pipe.incr(key).expire(key, window, nx=True).execute()
        if count > limit:
            raise HTTPException(429, 'Too many attempts. Try again shortly', headers={'Retry-After': str(window)})


def credential(request: Request) -> str:
    auth = request.headers.get('authorization', '')
    if auth.lower().startswith('bearer '):
        return auth[7:]
    return request.cookies.get(COOKIE, '')


async def current_session(request: Request):
    return await request.app.state.auth.resolve(credential(request))


Session = Annotated[dict, Depends(current_session)]


async def require_admin(request: Request, session: dict):
    # Always revalidate upstream policy for privileged operations; never trust cached roles.
    user = await request.app.state.jellyfin.request('GET', 'Users/Me', session)
    if not user.get('Policy', {}).get('IsAdministrator'):
        raise HTTPException(403, 'Administrator access required')
    return user

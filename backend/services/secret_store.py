"""Local, encrypted persistence for the app's root key and optional integration secrets.

The root key (used to encrypt everything else, including sessions in
AuthService) is generated on first run and written to its own file if not
supplied via SECRET_KEY, so no secret needs to be supplied via the environment
at all. Integration secrets (Seerr, Whisparr, iptv-gtw) are entered through the
setup wizard and stored in a separate file, encrypted with a key derived from
the root key, so a leaked config file alone doesn't expose them.
"""
import base64
import hashlib
import json
import secrets
import stat
from pathlib import Path
from urllib.parse import urlencode

from cryptography.fernet import Fernet, InvalidToken

SERVICES = ('seerr', 'whisparr', 'iptv_gtw')


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600: owner read/write only


def load_or_create_key(path: Path) -> str:
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    _write_private(path, key)
    return key


def derive_cipher(key: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


def iptv_gtw_urls(url: str, token: str) -> tuple[str, str]:
    """Playlist and guide URLs an iptv-gtw instance exposes for a given export token."""
    query = urlencode({'token': token})
    return f'{url}/playlist.m3u?{query}', f'{url}/epg.xml?{query}'


class SecretStore:
    def __init__(self, root_key: str, path: Path):
        self.path = path
        self.cipher = derive_cipher(root_key)
        self._cache: dict | None = None

    def _read(self) -> dict:
        # Cached in memory: this is the only writer (save(), below, updates the
        # cache directly), so nothing outside this process can change the file.
        if self._cache is None:
            if not self.path.exists():
                self._cache = {}
            else:
                try:
                    self._cache = json.loads(self.path.read_text())
                except (json.JSONDecodeError, OSError):
                    self._cache = {}
        return self._cache

    def get(self, service: str) -> tuple[str | None, str | None]:
        """Return (url, decrypted secret) for a configured service, or (None, None)."""
        entry = self._read().get(service)
        if not entry:
            return None, None
        try:
            return entry['url'], self.cipher.decrypt(entry['secret'].encode()).decode()
        except (InvalidToken, KeyError):
            return None, None

    def save(self, service: str, url: str, secret: str) -> None:
        if service not in SERVICES:
            raise ValueError(f'Unknown service: {service}')
        stored = {**self._read(), service: {'url': url.rstrip('/'), 'secret': self.cipher.encrypt(secret.encode()).decode()}}
        _write_private(self.path, json.dumps(stored))
        self._cache = stored

    def status(self) -> dict[str, dict]:
        stored = self._read()
        return {service: {'configured': service in stored, 'url': stored.get(service, {}).get('url')}
                for service in SERVICES}

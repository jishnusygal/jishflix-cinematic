import stat

import httpx
from fakeredis.aioredis import FakeRedis

from backend.config import Settings
from backend.main import create_app
from backend.services.secret_store import SecretStore, load_or_create_key


def test_load_or_create_key_persists_and_restricts_permissions(tmp_path):
    path = tmp_path / 'master.key'
    first = load_or_create_key(path)
    assert len(first) > 32
    assert stat.S_IMODE(path.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR
    assert load_or_create_key(path) == first


def test_secret_store_encrypts_at_rest_and_round_trips(tmp_path):
    path = tmp_path / 'integrations.json'
    store = SecretStore('a-root-key-for-testing-only', path)
    store.save('seerr', 'http://seerr', 'super-secret-key')
    assert 'super-secret-key' not in path.read_text()
    assert store.get('seerr') == ('http://seerr', 'super-secret-key')
    assert store.get('whisparr') == (None, None)


def test_secret_store_rejects_ciphertext_from_a_different_root_key(tmp_path):
    path = tmp_path / 'integrations.json'
    SecretStore('root-key-one', path).save('seerr', 'http://seerr', 'super-secret-key')
    assert SecretStore('root-key-two', path).get('seerr') == (None, None)


async def test_create_app_generates_and_reuses_secret_key(tmp_path):
    # _env_file=None: isolate from any real .env in the current working directory,
    # since that's exactly the plaintext-secret source this bootstrap replaces.
    settings = Settings(_env_file=None, jellyfin_url='http://jellyfin', public_url='http://testserver',
                         cookie_secure=False, data_dir=str(tmp_path))
    create_app(settings, FakeRedis(), httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    assert settings.secret_key.get_secret_value()
    assert (tmp_path / 'master.key').exists()

    again = Settings(_env_file=None, jellyfin_url='http://jellyfin', public_url='http://testserver',
                      cookie_secure=False, data_dir=str(tmp_path))
    create_app(again, FakeRedis(), httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    assert again.secret_key.get_secret_value() == settings.secret_key.get_secret_value()

"""Browser journeys against deterministic Jellyfin-shaped responses."""
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
USER = {'Id': 'alice', 'Name': 'Alice', 'Policy': {'IsAdministrator': True}}
MOVIE = {'Id': 'arrival', 'Name': 'Arrival', 'Type': 'Movie', 'ProductionYear': 2016,
         'OfficialRating': 'PG-13', 'CommunityRating': 7.9, 'RunTimeTicks': 69600000000,
         'Overview': 'When mysterious spacecraft touch down across the globe, a linguist searches for meaning in an unfamiliar language.',
         'Genres': ['Science Fiction', 'Drama'], 'UserData': {'PlaybackPositionTicks': 1200000000, 'PlayedPercentage': 20}}
MOVIES = [MOVIE] + [{**MOVIE, 'Id': f'movie-{i}', 'Name': title} for i, title in enumerate(['Interstellar', 'The Grand Budapest Hotel', 'Dune', 'Past Lives', 'Blade Runner 2049', 'The Bear', 'Perfect Days'])]


@pytest.fixture(scope='module')
def browser():
    server = subprocess.Popen(['npm', 'run', 'preview', '--', '--host', '127.0.0.1', '--port', '4178'], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen('http://127.0.0.1:4178', timeout=1)
                break
            except OSError:
                time.sleep(.1)
        with sync_playwright() as p:
            chromium = p.chromium.launch(headless=True)
            yield chromium
            chromium.close()
    finally:
        server.terminate()
        server.wait(timeout=5)


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    state = {'authenticated': True, 'requests': [], 'errors': []}
    page.on('pageerror', lambda error: state['errors'].append(str(error)))
    page.route_web_socket('**/api/socket', lambda ws: ws.close())

    def route(request_route):
        request = request_route.request
        path = request.url.split('/api/', 1)[-1]
        state['requests'].append((path, request.method, request.post_data))
        status = 200
        if path == 'auth/me':
            body = USER if state['authenticated'] else {'detail': 'Sign in to continue'}
            status = 200 if state['authenticated'] else 401
        elif path == 'auth/login':
            state['authenticated'] = True
            body = USER
        elif path == 'auth/logout':
            state['authenticated'] = False
            body, status = None, 204
        elif path == 'media/home':
            body = {'continue': MOVIES[:3], 'next_up': [], 'recent': MOVIES, 'discover': MOVIES, 'favorites': []}
        elif path.startswith('media/items?'):
            body = {'Items': MOVIES[:1] if 'search=' in path else MOVIES, 'TotalRecordCount': 1 if 'search=' in path else len(MOVIES)}
        elif path.endswith('/favorite'):
            body = {'IsFavorite': request.method == 'POST'}
        elif path.startswith('media/items/'):
            body = MOVIE
        elif path == 'media/libraries':
            body = {'Items': [{'Id': 'movies', 'Name': 'Movies', 'CollectionType': 'movies'}]}
        elif path == 'auth/mcp-token':
            body = {'token': 'fixture-mcp-token', 'expires_in': 3600}
        elif path.startswith('livetv/'):
            body = {'Items': []}
        elif path.startswith('playback/'):
            body, status = {'detail': 'Fixture stream unavailable'}, 422
        else:
            body = {}
        request_route.fulfill(status=status, content_type='application/json', body=json.dumps(body) if body is not None else '')

    page.route('**/api/**', route)
    yield page, state
    assert state['errors'] == []
    page.close()


def test_login_and_home(page):
    page, state = page
    state['authenticated'] = False
    page.goto('http://127.0.0.1:4178')
    expect(page.get_by_role('heading', name='Welcome home.')).to_be_visible()
    page.get_by_label('Username').fill('alice')
    page.get_by_label('Password', exact=True).fill('secret')
    page.get_by_role('button', name='Enter your cinema').click()
    expect(page.get_by_role('heading', name='Arrival', exact=True).first).to_be_visible()
    expect(page.get_by_role('heading', name='Pick up where you left off')).to_be_visible()
    assert next(r for r in state['requests'] if r[0] == 'auth/login')[1] == 'POST'


def test_dpad_modal_focus_back_and_search(page):
    page, _ = page
    page.goto('http://127.0.0.1:4178')
    page.get_by_role('button', name='More info').click()
    dialog = page.get_by_role('dialog', name='Arrival')
    expect(dialog).to_be_visible()
    expect(page.get_by_role('button', name='Close details')).to_be_focused()
    page.keyboard.press('ArrowDown')
    assert page.evaluate("document.querySelector('[role=dialog]').contains(document.activeElement)")
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    expect(page.get_by_role('button', name='More info')).to_be_focused()
    page.get_by_role('link', name='Search', exact=True).first.click()
    page.get_by_role('searchbox').fill('Arrival')
    page.get_by_role('button', name='Search', exact=True).click()
    expect(page).to_have_url('http://127.0.0.1:4178/browse?search=Arrival')
    expect(page.get_by_role('button', name='Open Arrival')).to_be_visible()
    page.get_by_role('button', name='Open Arrival').focus()
    page.keyboard.press('Enter')
    expect(page.get_by_role('dialog')).to_be_visible()


def test_settings_token_and_logout(page):
    page, _ = page
    page.goto('http://127.0.0.1:4178/settings')
    expect(page.get_by_role('heading', name='Settings', exact=True)).to_be_visible()
    page.get_by_role('button', name='Create access token').click()
    expect(page.get_by_label('Bearer token')).to_have_value('fixture-mcp-token')
    page.get_by_role('button', name='Switch user / Sign out').click()
    expect(page.get_by_role('heading', name='Welcome home.')).to_be_visible()


def test_live_tv_empty_and_player_failure(page):
    page, _ = page
    page.goto('http://127.0.0.1:4178/live')
    expect(page.get_by_role('heading', name='Your live lineup starts here.')).to_be_visible()
    page.goto('http://127.0.0.1:4178')
    page.get_by_role('button', name='Resume', exact=True).click()
    expect(page.get_by_role('dialog', name='Playing Arrival')).to_be_visible()
    expect(page.get_by_role('alert')).to_have_text('Fixture stream unavailable')
    page.keyboard.press('Escape')
    expect(page.get_by_role('dialog')).not_to_be_visible()


def test_mobile_no_horizontal_overflow(page):
    page, state = page
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto('http://127.0.0.1:4178/browse')
    expect(page.get_by_role('button', name='Open Arrival')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Browse page overflows horizontally'
    page.goto('http://127.0.0.1:4178/settings')
    expect(page.get_by_role('heading', name='Settings', exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    state['authenticated'] = False
    page.goto('http://127.0.0.1:4178')
    expect(page.get_by_role('heading', name='Welcome home.')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path='/tmp/jishflix-mobile-auth.png', full_page=True)


def test_visual_capture(page):
    page, _ = page
    page.goto('http://127.0.0.1:4178')
    expect(page.get_by_role('heading', name='Worth a night in')).to_be_visible()
    page.screenshot(path='/tmp/jishflix-home.png', full_page=True)

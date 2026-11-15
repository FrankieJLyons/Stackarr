"""Owner-only title browsing and explicit requests through the connected Seerr.

Only normalized public title fields leave this boundary. Credentials and upstream
links never reach the browser. Plex links are rebuilt after a live identity and
metadata check; no playback or download is started implicitly.
"""
import asyncio
import json
import re
import secrets
import time
from urllib.parse import quote, urlencode, urlsplit

import httpx
from pydantic import Field

from .adapters import require_write
from .config import CATALOG, Model, container_port
from .integrations import IntegrationError, bounded_response
from .quality import label as quality_label

KIND = r"^(movie|tv)$"
ART = r"^/[A-Za-z0-9_-]+\.(jpg|png)$"


class HomeError(ValueError):
    pass


class TitleRequest(Model):
    seasons: list[int] = Field(default_factory=list, max_length=100)
    quality: str = Field(default='', max_length=64)


def text(value, limit=600):
    return value[:limit] if isinstance(value, str) else ''


def number(value):
    return value if type(value) is int and 0 < value < 2_147_483_647 else None


def rows(value):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise HomeError('The connected app returned unexpected title data. Try again or check Apps.')
    return value


def artwork(path, size='w342'):
    return f'/api/home/art/{size}{path}' if isinstance(path, str) and re.fullmatch(ART, path) else ''


def progress(media, request=None):
    status = media.get('status')
    request_status = (request or {}).get('status')
    if (request or {}).get('is4k'):
        status = media.get('status4k')
    if status == 5:
        return {'state': 'available', 'label': 'Available', 'detail': 'In your Seerr library. Open details to check Plex.'}
    if status == 4:
        return {'state': 'partial', 'label': 'Some episodes available', 'detail': 'Your library has part of this show. Plex shows which episodes can play.'}
    if request_status in (3, 4):
        return {'state': 'attention', 'label': 'Declined' if request_status == 3 else 'Needs attention',
                'detail': 'Open Seerr to review this request.'}
    if status == 6:
        return {'state': 'blocked', 'label': 'Not requestable', 'detail': 'This title is blocked in Seerr.'}
    if status == 7:
        return {'state': 'deleted', 'label': 'Removed from library', 'detail': 'Open Seerr to review this title.'}
    downloads = media.get('downloadStatus4k' if (request or {}).get('is4k') else 'downloadStatus') or []
    if isinstance(downloads, list) and downloads:
        # Preserve native queue states. Never invent an ETA or a percentage.
        queue = next((row for row in downloads if isinstance(row, dict)), {})
        state = queue.get('status')
        tracked = queue.get('trackedDownloadState')
        if tracked in ('importBlocked', 'importFailed') or state in ('warning', 'failed'):
            return {'state': 'attention', 'label': 'Needs attention', 'detail': 'The download or import needs help. Open Seerr for details.'}
        if tracked in ('importPending', 'importing') or state == 'completed':
            return {'state': 'importing', 'label': 'Adding to library', 'detail': 'Waiting for import and Plex library recognition.'}
        if state in ('paused', 'queued'):
            return {'state': state, 'label': 'Paused' if state == 'paused' else 'Queued',
                    'detail': 'Seerr reports the download is ' + state + '. Open Seerr for details.'}
        return {'state': 'downloading', 'label': 'Downloading', 'detail': 'Seerr reports an active download.'}
    if status == 2 or request_status == 1:
        return {'state': 'pending', 'label': 'Awaiting approval', 'detail': 'Your request is saved and waiting for approval in Seerr.'}
    if status == 3 or request_status == 2:
        return {'state': 'requested', 'label': 'Requested', 'detail': 'Your request is being processed. It may be waiting for a matching release, an import or the next library check.'}
    if request_status == 5:
        return {'state': 'checking', 'label': 'Checking availability', 'detail': 'The request completed, but current library availability is not confirmed.'}
    return {'state': 'discover', 'label': 'Request', 'detail': 'Choose a download quality and request this title.'}


def title(data, kind=None):
    kind = kind or data.get('mediaType')
    identity = number(data.get('id'))
    if kind not in ('movie', 'tv') or not identity or data.get('adult') is True:
        return None
    media = data.get('mediaInfo') if isinstance(data.get('mediaInfo'), dict) else {}
    date = text(data.get('releaseDate') if kind == 'movie' else data.get('firstAirDate'), 10)
    return {'id': identity, 'kind': kind, 'title': text(data.get('title') or data.get('name'), 200) or 'Untitled',
            'year': date[:4] if re.match(r'^\d{4}', date) else '', 'overview': text(data.get('overview'), 2000),
            'poster': artwork(data.get('posterPath')), 'backdrop': artwork(data.get('backdropPath'), 'w1280'),
            'progress': progress(media)}


class Home:
    def __init__(self, store, transport=None):
        self.store, self.transport = store, transport
        self.request_lock = asyncio.Lock()
        self.limit = asyncio.Semaphore(8)
        self.art_cache = {}
        self.quality_choices = {}
        self.profile_names = {}
        from .quality_rules import QualityRules

        self.rules = QualityRules(store, self.call)
        self.mapping = None

    def connection(self, app):
        config = self.store.config()[1].integrations[app]
        secret = self.store.secret(app).get('api_key', '')
        if not config.enabled or not secret:
            raise HomeError(f'Connect {CATALOG[app]["name"]} in Apps to use this feature.')
        base = config.url or f'http://{app}:{container_port(app, config)}'
        if urlsplit(base).hostname in ('169.254.169.254', 'metadata.google.internal'):
            raise HomeError('Check the saved application address in Apps.')
        return config, base, secret

    async def call(self, path, method='GET', params=None, body=None, app='seerr', image=False):
        if method != 'GET':
            from .native_import import require_writable

            try:
                # A title request writes to Arr, not to Plex. A native Plex library
                # can remain read-only while separate owned Arr apps receive requests.
                protected = [key for key, value in self.store.config()[1].integrations.items()
                             if value.enabled and value.read_only and not (path == '/api/v1/request' and key == 'plex')]
                require_writable(self.store, app, *(protected if app == 'seerr' else []))
            except ValueError as exc:
                raise HomeError(str(exc)) from None
        integration, base, secret = self.connection(app)
        cache_key = (self.store.config()[0], path)
        if image:
            cached = self.art_cache.get(cache_key)
            if cached and cached[0] > time.monotonic():
                return cached[1], cached[2]
        headers = {'Accept': 'application/json', 'X-Plex-Token' if app == 'plex' else 'X-Api-Key': secret}
        if integration.request_host:
            headers['Host'] = integration.request_host
        try:
            async with self.limit, httpx.AsyncClient(transport=self.transport, trust_env=False,
                    follow_redirects=False, timeout=8, headers=headers) as client:
                # Seerr's OpenAPI validator rejects '+' as a reserved character
                # in search values. Encode spaces as %20, as its own UI does.
                url = base + path + ('?' + urlencode(params, quote_via=quote) if params else '')
                response, content = await bounded_response(client, method, url,
                    **({'json': body} if body is not None else {}))
            if response.status_code in (401, 403):
                raise HomeError(f'{CATALOG[app]["name"]} needs attention. Check its login, permissions and saved connection in Apps.')
            if response.status_code == 409:
                raise HomeError('This title is already requested. Refresh your requests to see its progress.')
            if not response.is_success:
                raise HomeError(f'{CATALOG[app]["name"]} could not finish this action. Try again or open the app for details.')
            if image:
                mime = response.headers.get('content-type', '').split(';')[0]
                if mime == 'image/jpg':
                    mime = 'image/jpeg'  # Seerr uses the file extension as MIME subtype.
                if mime not in ('image/jpeg', 'image/png', 'image/webp'):
                    raise HomeError('Artwork is unavailable.')
                if not (content.startswith(b'\xff\xd8\xff') or content.startswith(b'\x89PNG\r\n\x1a\n') or
                        (content.startswith(b'RIFF') and content[8:12] == b'WEBP')):
                    raise HomeError('Artwork is unavailable.')
                self.art_cache[cache_key] = (time.monotonic() + 600, content, mime)
                while len(self.art_cache) > 100 or sum(len(row[1]) for row in self.art_cache.values()) > 16_000_000:
                    self.art_cache.pop(next(iter(self.art_cache)))
                return content, mime
            result = json.loads(content)
            list_paths = ('/api/v1/service/radarr', '/api/v1/service/sonarr', '/api/v1/settings/radarr', '/api/v1/settings/sonarr')
            if app in {'sonarr', 'radarr'}:
                list_paths += ('/api/v3/qualityprofile', '/api/v3/customformat', '/api/v3/customformat/schema', '/api/v3/series', '/api/v3/movie',
                               '/api/v3/series/lookup', '/api/v3/movie/lookup', '/api/v3/series/editor', '/api/v3/movie/editor')
            if not isinstance(result, dict) and not (path in list_paths and isinstance(result, list)):
                raise HomeError('The connected app returned unexpected title data.')
            return result
        except (httpx.HTTPError, IntegrationError, ValueError) as exc:
            if isinstance(exc, HomeError):
                raise
            message = ('The request may have been saved. Check your requests before trying again.' if method == 'POST' and app == 'seerr'
                       else f'{CATALOG[app]["name"]} is not responding. Try again or check Apps.')
            raise HomeError(message) from None

    async def catalog(self, source='trending', page=1, query=''):
        path = '/api/v1/search' if query else '/api/v1/discover/' + source
        result = await self.call(path, params={'page': page, **({'query': query} if query else {})})
        return {'items': [item for row in rows(result.get('results'))[:40] if (item := title(row))],
                'page': page, 'pages': min(500, max(1, number(result.get('totalPages')) or 1)), 'checked_at': time.time()}

    async def detail(self, kind, identity, check_plex=False):
        data = await self.call(f'/api/v1/{kind}/{identity}')
        item = title(data, kind)
        if not item or item['id'] != identity:
            raise HomeError('This title is unavailable. Try another title.')
        media = data.get('mediaInfo') or {}
        if not isinstance(media, dict):
            raise HomeError('The connected app returned unexpected title data.')
        requests = rows(media.get('requests') or [])
        regular = [row for row in requests if not row.get('is4k')]
        # A historical declined/failed request must remain visible until resolved.
        latest = max(regular, key=lambda row: number(row.get('id')) or 0, default=None)
        item['progress'] = progress(media, latest)
        item['seasons'] = []
        if kind == 'tv':
            statuses = {row.get('seasonNumber'): row.get('status') for row in rows(media.get('seasons') or [])}
            covered = {season.get('seasonNumber') for request in regular if request.get('status') in (1, 2, 5)
                       for season in rows(request.get('seasons') or [])}
            for season in rows(data.get('seasons') or [])[:100]:
                n = number(season.get('seasonNumber'))
                if not n:
                    continue  # Specials are available in Seerr's advanced controls.
                available = statuses.get(n) == 5
                item['seasons'].append({'number': n, 'name': text(season.get('name'), 100) or f'Season {n}',
                    'label': 'Available' if available else 'Requested' if n in covered else 'Not requested',
                    'requestable': not available and n not in covered and item['progress']['state'] not in ('blocked', 'deleted', 'attention')})
        item['can_request'] = (any(row['requestable'] for row in item['seasons']) if kind == 'tv'
                               else item['progress']['state'] == 'discover')
        item['quality_options'] = []
        item['quality_notice'] = ''
        item['existing_series'] = kind == 'tv' and (bool(regular) or media.get('status') in (2, 3, 4, 5))
        if check_plex and item['can_request']:
            if item['existing_series']:
                item['quality_notice'] = 'Additional seasons keep this show’s existing Sonarr quality settings.'
            else:
                try:
                    item['quality_options'] = await self.quality_options(kind, identity, data)
                    item['quality_notice'] = next((row['reason'] for row in item['quality_options'] if row.get('reason')), '')
                except HomeError as exc:
                    item['quality_notice'] = str(exc)
        item['play_url'] = ''
        item['play_notice'] = ''
        item['requested_quality'] = await self.request_quality(kind, latest) if check_plex else ''
        if check_plex:
            item['progress'] = await self.import_progress(media, kind, identity, item['progress'], latest)
        if check_plex and item['progress']['state'] in ('available', 'partial'):
            try:
                item['play_url'] = await self.plex_link(media, kind)
                if item['progress']['state'] == 'available':
                    item['progress']['detail'] = 'Plex confirmed this item is in your library.'
            except HomeError as exc:
                item['play_notice'] = str(exc)
        return item

    async def request_quality(self, kind, request):
        request = request or {}
        profile, server = number(request.get('profileId')), request.get('serverId')
        if not profile or type(server) is not int or not 0 <= server < 2_147_483_647:
            return ''
        key = (self.store.config()[0], kind, server)
        cached = self.profile_names.get(key)
        try:
            if not cached or cached[0] < time.monotonic():
                app = 'radarr' if kind == 'movie' else 'sonarr'
                data = await self.call('/api/v1/service/' + app + '/' + str(server))
                names = {row['id']: text(row.get('name'), 160) for row in rows(data.get('profiles')) if number(row.get('id'))}
                if len(self.profile_names) >= 30:
                    self.profile_names.pop(next(iter(self.profile_names)))
                self.profile_names[key] = cached = (time.monotonic() + 30, names)
            name = cached[1].get(profile, '')
            return quality_label(name)
        except HomeError:
            return ''

    async def import_progress(self, media, kind, identity, current, request=None):
        """Distinguish a verified Arr import from Plex availability, without scanning."""
        if current['state'] not in ('requested', 'checking', 'importing') or (request or {}).get('is4k'):
            return current
        app = 'radarr' if kind == 'movie' else 'sonarr'
        config = self.store.config()[1].integrations[app]
        secret = self.store.secret(app).get('api_key')
        external = number(media.get('externalServiceId'))
        if not config.enabled or not secret or not external:
            return current
        try:
            servers = rows(await self.call('/api/v1/settings/' + app))
            server = next((row for row in servers if row.get('id') == media.get('serviceId') and row.get('is4k') is False), None)
            peer = urlsplit(config.peer_url or config.url)
            if not server or server.get('hostname') != peer.hostname or server.get('port') != (peer.port or (443 if peer.scheme == 'https' else 80)) or server.get('apiKey') != secret:
                return current
            resource = 'movie' if kind == 'movie' else 'series'
            item = await self.call('/api/v3/' + resource + '/' + str(external), app=app)
            if (kind == 'movie' and item.get('tmdbId') != identity) or (kind == 'tv' and
                    (not number(media.get('tvdbId')) or item.get('tvdbId') != media['tvdbId'])):
                return current
            imported = False
            if kind == 'movie':
                file = item.get('movieFile') or {}
                imported = item.get('hasFile') is True and isinstance(file, dict) and bool(number(file.get('id')))
            else:
                wanted = {row.get('seasonNumber') for row in rows((request or {}).get('seasons') or [])}
                seasons = {row.get('seasonNumber'): row.get('statistics') or {} for row in rows(item.get('seasons') or [])}
                imported = bool(wanted) and all(isinstance(seasons.get(n), dict) and
                    type(seasons[n].get('episodeCount')) is int and seasons[n]['episodeCount'] > 0 and
                    type(seasons[n].get('episodeFileCount')) is int and seasons[n]['episodeFileCount'] >= seasons[n]['episodeCount'] for n in wanted)
            if imported:
                return {'state': 'imported', 'label': 'Adding to Plex',
                        'detail': 'The download is imported. Waiting for Plex to match it and Seerr to confirm availability. This updates automatically when library connections are configured.'}
        except HomeError:
            # An unavailable optional Arr must not hide a saved Seerr request.
            pass
        return current

    async def quality_snapshot(self, kind):
        """Read real profiles through Seerr; never edit a server or guess a profile ID."""
        app = 'radarr' if kind == 'movie' else 'sonarr'
        path = '/api/v1/service/' + app
        servers = rows(await self.call(path))
        defaults = [row for row in servers if row.get('isDefault') is True and row.get('is4k') is False]
        if len(defaults) != 1:
            raise HomeError('Finish connecting your movie or TV request service in Setup, then reopen this title to choose quality.')
        server = defaults[0]
        identity = server.get('id')
        if type(identity) is not int or not 0 <= identity < 2_147_483_647:
            raise HomeError('The request service needs attention. Review its connection in Setup.')
        data = await self.call(path + '/' + str(identity))
        if data.get('server') != server:
            # Sonarr's detail response contains additional anime/tag settings.
            detail = data.get('server')
            if not isinstance(detail, dict) or any(detail.get(key) != server.get(key) for key in
                    ('id', 'isDefault', 'is4k', 'activeProfileId', 'activeDirectory')):
                raise HomeError('Request settings changed. Reopen the title before requesting it.')
        profiles = rows(data.get('profiles'))
        if not profiles or len(profiles) > 100 or any(not number(row.get('id')) for row in profiles):
            raise HomeError('Quality profiles could not be checked. Review your request service in Setup.')
        profiles = [{'id': row.get('id'), 'name': text(row.get('name'), 160)} for row in profiles]
        if len({row['id'] for row in profiles}) != len(profiles) or any(not row['name'] for row in profiles):
            raise HomeError('Quality profiles could not be checked. Review your request service in Setup.')
        directory = server.get('activeDirectory')
        if not isinstance(directory, str) or not directory or directory not in [row.get('path') for row in rows(data.get('rootFolders'))]:
            raise HomeError('Choose a valid movie or TV library folder in your request service, then reopen this title.')
        if server.get('activeProfileId') not in [row['id'] for row in profiles]:
            raise HomeError('The default quality is missing. Review your request service in Setup.')
        return {'revision': self.store.config()[0], 'server': server, 'profiles': profiles}

    async def quality_options(self, kind, identity, data=None):
        snapshot = await self.quality_snapshot(kind)
        rule = await self.rule_snapshot(kind, identity, snapshot, data)
        now = time.monotonic()
        self.quality_choices = {key: value for key, value in self.quality_choices.items() if value['expires'] > now}
        options = []
        labels = {'HD-1080p': '1080p · Full HD', 'Ultra-HD': '4K · Ultra HD', 'HD-720p': '720p · HD', 'SD': 'SD · smaller files'}
        for profile in snapshot['profiles']:
            if rule and profile['id'] not in rule['profiles'].values():
                continue
            token = secrets.token_urlsafe(24)
            self.quality_choices[token] = {'expires': now + 600, 'kind': kind, 'identity': identity,
                                          'snapshot': snapshot, 'profile': profile}
            options.append({'value': token, 'label': labels.get(profile['name'], quality_label(profile['name'])),
                            'profile': profile['name'], 'default': profile['id'] == (rule['profile_id'] if rule else snapshot['server']['activeProfileId']),
                            'reason': ('Quality rule: ' + rule['reason'] + (f" → {rule['tier']}" if rule['tier'] else ' Choose quality below.')) if rule else ''})
        while len(self.quality_choices) > 400:
            self.quality_choices.pop(next(iter(self.quality_choices)))
        return sorted(options, key=lambda row: not row['default'])

    async def rule_snapshot(self, kind, identity, snapshot, data=None):
        app = 'sonarr' if kind == 'tv' else 'radarr'
        if not self.rules.saved(app)[1].enabled:
            return None
        try:
            data = data or await self.call(f'/api/v1/{kind}/{identity}')
            rule = await self.rules.request_choice(kind, data, snapshot['server'])
            # Seerr's rolling cache can omit newly created profiles. request_choice
            # has checked the server binding, live Arr profiles and their filters.
            # Only those managed profiles are offered while rules are enabled;
            # normalizing here also keeps choices valid when Seerr's cache catches up.
            snapshot['profiles'] = rule['verified_profiles']
            snapshot['rule'] = rule
            return rule
        except ValueError as exc:
            raise HomeError(str(exc)) from None

    async def selected_quality(self, kind, identity, token):
        choice = self.quality_choices.get(token)
        if not choice or choice['expires'] <= time.monotonic() or (choice['kind'], choice['identity']) != (kind, identity):
            raise HomeError('Your quality choice expired. Close and reopen this title to choose again.')
        current = await self.quality_snapshot(kind)
        await self.rule_snapshot(kind, identity, current)
        if choice['snapshot'] != current:
            raise HomeError('Request settings changed. Close and reopen this title to check the quality again.')
        server, profile = choice['snapshot']['server'], choice['profile']
        return {'serverId': server['id'], 'profileId': profile['id'], 'rootFolder': server['activeDirectory']}, profile['name']

    async def plex_link(self, media, kind):
        config, _, _ = self.connection('plex')
        key = str(media.get('ratingKey') or '')
        if not re.fullmatch(r'[0-9]{1,18}', key):
            raise HomeError('Seerr has no Plex link for this title yet. Wait for the library check or open Plex.')
        settings, identity = await asyncio.gather(self.call('/api/v1/settings/plex'), self.call('/identity', app='plex'))
        machine = settings.get('machineId')
        plex = identity.get('MediaContainer') or {}
        if not isinstance(plex, dict):
            raise HomeError('Plex returned unexpected server information. Check its connection in Apps.')
        if not isinstance(machine, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', machine) or plex.get('machineIdentifier') != machine:
            raise HomeError('Plex and Seerr point to different servers. Check their connections in Apps.')
        data = await self.call('/library/metadata/' + key, app='plex')
        container = data.get('MediaContainer') or {}
        if not isinstance(container, dict):
            raise HomeError('Plex returned unexpected library information. Try again or check Apps.')
        metadata = rows(container.get('Metadata') or [])
        if not any(str(row.get('ratingKey')) == key and row.get('type') == ('movie' if kind == 'movie' else 'show') for row in metadata):
            raise HomeError('Plex cannot find this library item yet. Wait for its library check and try again.')
        matched = next(row for row in metadata if str(row.get('ratingKey')) == key)
        tmdb = [row.get('id') for row in rows(matched.get('Guid') or []) if str(row.get('id', '')).startswith('tmdb://')]
        if tmdb and 'tmdb://' + str(media.get('tmdbId')) not in tmdb:
            raise HomeError('Plex and Seerr disagree about this title. Refresh the library connection in Seerr.')
        from .lan import browser_url

        base = browser_url('plex', config.browser_url or f'http://localhost:{config.port or CATALOG["plex"]["port"]}')
        if not base:
            raise HomeError('Plex has no verified home-network address. Open Stackarr on the server to finish network setup.')
        # Match Seerr's native Plex Web preplay handoff, using our saved browser address.
        base = base.rstrip('/')
        if not base.endswith(('/web', '/web/index.html', '/desktop')):
            base += '/web/index.html'
        return base + '#!/server/' + machine + '/details?key=' + quote('/library/metadata/' + key, safe='')

    async def hydrate(self, media, request=None):
        if not isinstance(media, dict):
            raise HomeError('Seerr returned unexpected library information. Try again or check Apps.')
        kind, identity = media.get('mediaType'), number(media.get('tmdbId'))
        if kind not in ('movie', 'tv') or not identity:
            return None
        try:
            item = await self.detail(kind, identity)
        except HomeError:
            item = {'id': identity, 'kind': kind, 'title': 'Title details unavailable', 'year': '',
                    'overview': '', 'poster': '', 'backdrop': '', 'metadata_unavailable': True}
        item['progress'] = await self.import_progress(media, kind, identity, progress(media, request), request)
        if request:
            item['request_id'] = number(request.get('id'))
            item['requested_seasons'] = [row.get('seasonNumber') for row in rows(request.get('seasons') or []) if number(row.get('seasonNumber'))]
            item['is4k'] = bool(request.get('is4k'))
            item['requested_quality'] = await self.request_quality(kind, request)
        return item

    async def requests(self, page=1):
        data = await self.call('/api/v1/request', params={'take': 12, 'skip': (page - 1) * 12, 'sort': 'added', 'filter': 'all'})
        items = await asyncio.gather(*(self.hydrate(row.get('media') or {}, row) for row in rows(data.get('results'))[:12]))
        return {'items': [item for item in items if item], 'page': page,
                'pages': max(1, number((data.get('pageInfo') or {}).get('pages')) or 1), 'checked_at': time.time()}

    async def available(self):
        data = await self.call('/api/v1/media', params={'take': 12, 'skip': 0, 'filter': 'allavailable', 'sort': 'mediaAdded'})
        items = await asyncio.gather(*(self.hydrate(row) for row in rows(data.get('results'))[:12]))
        return {'items': [item for item in items if item], 'checked_at': time.time()}

    async def home(self):
        self.connection('seerr')
        async def rail(key, work):
            try:
                async with asyncio.timeout(25):
                    return key, await work
            except (HomeError, TimeoutError):
                return key, {'items': [], 'error': 'Could not load this row. Try refreshing or check Apps.'}
        result = await asyncio.gather(rail('available', self.available()), rail('requests', self.requests()),
            rail('trending', self.catalog()), rail('movies', self.catalog('movies')), rail('tv', self.catalog('tv')))
        return dict(result) | {'checked_at': time.time()}

    async def request(self, kind, identity, intent):
        require_write('seerr', 'media-request.create')
        if any(type(n) is not int or n < 1 or n > 10000 for n in intent.seasons) or len(set(intent.seasons)) != len(intent.seasons):
            raise HomeError('Choose each season once from the title details.')
        if kind == 'movie' and intent.seasons:
            raise HomeError('Movies do not have seasons.')
        async with self.request_lock:
            item = await self.detail(kind, identity)
            if not item['can_request']:
                raise HomeError('This title is already tracked or needs attention. Refresh your requests or open Seerr.')
            if kind == 'tv' and (not intent.seasons or not set(intent.seasons) <= {row['number'] for row in item['seasons'] if row['requestable']}):
                raise HomeError('Choose available seasons from the title details. Already requested seasons stay tracked.')
            quality, profile_name = {}, ''
            app = 'sonarr' if kind == 'tv' else 'radarr'
            if not intent.quality and not item['existing_series'] and self.rules.saved(app)[1].enabled:
                options = await self.quality_options(kind, identity)
                default = next((row for row in options if row['default']), None)
                if not default:
                    raise HomeError('This title has no known year. Reopen it and choose a quality explicitly.')
                intent.quality = default['value']
            if intent.quality:
                if item['existing_series']:
                    raise HomeError('This show is already tracked. Reopen it to request seasons using its existing quality settings.')
                quality, profile_name = await self.selected_quality(kind, identity, intent.quality)
                reviewed = self.quality_choices[intent.quality]['snapshot']
                if (reviewed['revision'] != self.store.config()[0] or
                        ('rule' in reviewed and reviewed['rule']['revision'] != self.rules.saved(app)[0])):
                    raise HomeError('Settings changed during this check. Reopen the title before requesting it.')
            if self.mapping and self.mapping.saved(app) and not item['existing_series']:
                try:
                    snapshot = await self.quality_snapshot(kind)
                    root = await self.mapping.request_root(app, snapshot['server'])
                    if root:
                        quality = {'serverId': snapshot['server']['id'], 'profileId': snapshot['server']['activeProfileId'], **quality, 'rootFolder': root}
                except ValueError as exc:
                    raise HomeError(str(exc)) from None
            data = await self.call('/api/v1/request', 'POST', body={'mediaType': kind, 'mediaId': identity, 'is4k': False, **quality,
                **({'seasons': intent.seasons} if kind == 'tv' else {})})
            if not number(data.get('id')) or data.get('status') not in (1, 2, 3, 4, 5):
                raise HomeError('The request result is uncertain. Check your requests before trying again.')
            self.store.audit('home.request.created', 'seerr')
            result_progress = progress(data.get('media') if isinstance(data.get('media'), dict) else {}, data)
            confirmed = not quality or all(data.get(key) == quality[key] for key in ('serverId', 'profileId'))
            message = ('Request saved' + (' with ' + quality_label(profile_name) if profile_name and confirmed else '') + '. Follow its progress in Your requests.')
            if not confirmed:
                message = 'Request saved, but its quality could not be confirmed. Check this request in Seerr before trying again.'
            elif data['status'] not in (1, 2, 5):
                message = 'Request saved, but it needs attention. Open Seerr to review it.'
            return {'request_id': data['id'], 'progress': result_progress,
                    'quality': profile_name if confirmed else '', 'quality_confirmed': confirmed, 'message': message}

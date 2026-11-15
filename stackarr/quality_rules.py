"""Reviewed quality preferences and reversible title assignments; never searches."""

import copy
import json
import secrets
import time
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from . import format_preferences as formats
from .adapters import require_write
from .config import Model
from .format_preferences import FormatPreferences
from .native_import import require_writable
from .store import Conflict

Tier = Literal['SD', '720p', '1080p', '4K']
App = Literal['sonarr', 'radarr']
TIERS = ('SD', '1080p', '4K')
ALLOWED = {
    'SD': {'SDTV', 'DVD', 'WEBRip-480p', 'WEBDL-480p', 'Bluray-480p', 'Bluray-576p'},
    '720p': {'HDTV-720p', 'WEBRip-720p', 'WEBDL-720p', 'Bluray-720p'},
    '1080p': {'HDTV-1080p', 'WEBRip-1080p', 'WEBDL-1080p', 'Bluray-1080p'},
    '4K': {'HDTV-2160p', 'WEBRip-2160p', 'WEBDL-2160p', 'Bluray-2160p'},
}
NOTICE = ('Rules select download profiles; they do not shrink or transcode existing files. '
          'Saving rules affects new requests made through Stackarr. Existing titles require a separate preview and apply. '
          'No search, file move or deletion is started. Monitored titles remain subject to the app’s normal release processing.')


class ExceptionRule(Model):
    media_id: int = Field(gt=0, le=2_147_483_646, strict=True)
    title: str = Field(min_length=1, max_length=200)
    tier: Tier = '4K'


class Policy(Model):
    enabled: bool = True
    selected_profiles: bool = False
    before_year: int = Field(default=2000, ge=1888, le=2200, strict=True)
    older: Tier = 'SD'
    newer: Tier = '1080p'
    exceptions: list[ExceptionRule] = Field(default_factory=list, max_length=200)
    formats: FormatPreferences = Field(default_factory=FormatPreferences)

    @model_validator(mode='after')
    def unique(self):
        if len({row.media_id for row in self.exceptions}) != len(self.exceptions):
            raise ValueError('Choose each title only once.')
        return self


class ReviewIntent(Model):
    app: App
    revision: int = Field(ge=0)
    policy: Policy
    scope: Literal['future', 'library'] = 'future'


def decide(policy, media_id, year):
    if not policy.enabled:
        return None, 'Rules are paused; keep the current profile.'
    exception = next((row for row in policy.exceptions if row.media_id == media_id), None)
    if exception:
        return exception.tier, 'Specific title exception'
    if policy.older == policy.newer:
        return policy.newer, 'Same quality for all years'
    if type(year) is not int or not 1888 <= year <= 2200:
        return None, 'Year unknown; keep the current profile and review manually.'
    return (policy.older, f'Before {policy.before_year}') if year < policy.before_year else (
        policy.newer, f'{policy.before_year} or later')


def resource(app):
    return 'series' if app == 'sonarr' else 'movie'


def media_key(app):
    return 'tvdbId' if app == 'sonarr' else 'tmdbId'


def valid_id(value):
    return type(value) is int and 0 < value < 2_147_483_647


def title_row(app, value):
    external = value.get(media_key(app))
    if not valid_id(external):
        raise ValueError('A title has no verified media identity. Review it in the app.')
    return {'id': value.get('id'), 'media_id': external, 'title': str(value.get('title') or 'Untitled')[:200],
            'year': value.get('year') if type(value.get('year')) is int else None,
            'profile_id': value.get('qualityProfileId')}


def curated(schema, tier):
    """Resolve actual IDs from the upstream schema, including nested quality groups."""
    if not isinstance(schema, dict) or not isinstance(schema.get('items'), list):
        raise ValueError('This app’s quality schema is unsupported. No profiles were changed.')
    result = copy.deepcopy(schema)
    result.pop('id', None)
    result.update(name='Stackarr ' + tier + ' v1', upgradeAllowed=False, minFormatScore=0,
                  cutoffFormatScore=0, minUpgradeFormatScore=1,
                  formatItems=[{**item, 'score': 0} for item in schema.get('formatItems', [])])
    names = []

    def visit(items):
        for item in items:
            children = item.get('items') or []
            if children:
                visit(children)
                item['allowed'] = any(child['allowed'] for child in children)
            else:
                quality = item.get('quality') or {}
                item['allowed'] = quality.get('name') in ALLOWED[tier] and quality.get('modifier', 'none') == 'none'
                if item['allowed']:
                    if not valid_id(quality.get('id')):
                        raise ValueError('The quality schema contains an invalid ID.')
                    names.append(quality['name'])
    visit(result['items'])
    enabled = [item for item in result['items'] if item['allowed']]
    if not enabled or not names:
        raise ValueError(f'This app has no supported {tier} qualities.')
    last = enabled[-1]
    result['cutoff'] = last['id'] if last.get('items') else last['quality']['id']
    return result, names


def profile_matches(actual, expected):
    # Ignore server-generated IDs and added display metadata, never permission flags.
    def items(rows):
        return [{'id': row.get('id') if row.get('items') else (row.get('quality') or {}).get('id'),
                 'allowed': row.get('allowed'), 'items': items(row.get('items') or [])} for row in rows]
    return (isinstance(actual, dict) and all(actual.get(key) == value for key, value in expected.items()
            if key not in {'items', 'id', 'formatItems'}) and items(actual.get('items') or []) == items(expected['items'])
            and formats.score_signature(actual.get('formatItems', [])) is not None
            and formats.score_signature(actual.get('formatItems', [])) == formats.score_signature(expected.get('formatItems', [])))


class QualityRules:
    def __init__(self, store, call):
        self.store, self.call = store, call

    def binding(self, app):
        return {'integration': self.store.config()[1].integrations[app].model_dump(),
                'credential': self.store.secret(app)}

    def saved(self, app):
        with self.store.db() as db:
            table = db.execute("SELECT 1 FROM sqlite_master WHERE name='quality_rules'").fetchone()
            row = db.execute('SELECT revision,policy,binding,profiles FROM quality_rules WHERE app=?', (app,)).fetchone() if table else None
        return (row[0], Policy.model_validate_json(row[1]), json.loads(self.store.cipher.decrypt(row[2])), json.loads(row[3])) if row else (
            0, Policy(enabled=False), None, {})

    def read(self, app):
        revision, policy, binding, _ = self.saved(app)
        config = self.store.config()[1].integrations[app]
        with self.store.db() as db:
            table = db.execute("SELECT 1 FROM sqlite_master WHERE name='quality_runs'").fetchone()
            history = [{'id': row[0], 'created': row[1]} for row in db.execute(
                'SELECT id,created FROM quality_runs WHERE app=? ORDER BY created DESC LIMIT 20', (app,))] if table else []
        return {'app': app, 'revision': revision, 'policy': policy.model_dump(), 'read_only': config.read_only,
                'connection_changed': binding is not None and binding != self.binding(app), 'history': history,
                'can_restore_rules': self.previous_policy(app) is not None, 'notice': NOTICE}

    def previous_policy(self, app):
        """Only offer the last snapshot while its connection and revision still match."""
        with self.store.db() as db:
            table = db.execute("SELECT 1 FROM sqlite_master WHERE name='quality_rule_restore'").fetchone()
            row = db.execute('SELECT revision,value FROM quality_rule_restore WHERE app=?', (app,)).fetchone() if table else None
        if not row or row[0] != self.saved(app)[0]:
            return None
        previous = json.loads(self.store.cipher.decrypt(row[1]))
        if previous['binding'] != self.binding(app) or previous['previous_binding'] not in (None, previous['binding']):
            return None
        return Policy.model_validate(previous['policy'])

    def restore_intent(self, app):
        previous = self.previous_policy(app)
        if previous is None:
            raise Conflict('Previous rules are unavailable or the app connection changed. Reload settings.')
        return ReviewIntent(app=app, revision=self.saved(app)[0], policy=previous)

    async def titles(self, app, query=''):
        data = await self.call('/api/v3/' + resource(app) + ('/lookup' if query else ''), app=app,
                               params={'term': query} if query else None)
        if not isinstance(data, list) or len(data) > 10000:
            raise ValueError('The title list is too large or could not be checked.')
        return [title_row(app, row) for row in data[:100] if valid_id(row.get(media_key(app)))] if query else [title_row(app, row) for row in data]

    async def profiles(self, app):
        profiles = await self.call('/api/v3/qualityprofile', app=app)
        if (not isinstance(profiles, list) or len(profiles) > 200
                or any(not isinstance(row, dict) or not valid_id(row.get('id')) for row in profiles)
                or len({row['id'] for row in profiles}) != len(profiles)):
            raise ValueError('Quality profiles could not be verified.')
        return profiles

    async def review(self, intent):
        app = intent.app
        revision, saved, _, _ = self.saved(app)
        if revision != intent.revision:
            raise Conflict('Rules changed. Reload them before reviewing.')
        if intent.scope == 'library' and (revision == 0 or saved != intent.policy or not saved.enabled):
            raise ValueError('Save your new-request rules first, then preview existing titles.')
        config_revision = self.store.config()[0]
        binding = self.binding(app)
        profiles = await self.profiles(app)
        schema = await self.call('/api/v3/qualityprofile/schema', app=app)
        format_plans = await formats.review(self.call, app, intent.policy.formats)
        plans = {}
        tiers = ({intent.policy.older, intent.policy.newer} | {row.tier for row in intent.policy.exceptions}
                 if intent.policy.selected_profiles else set(TIERS) | {row.tier for row in intent.policy.exceptions}
                 | {intent.policy.older, intent.policy.newer})
        for tier in ('SD', '720p', '1080p', '4K'):
            if tier not in tiers:
                continue
            expected, names = curated(schema, tier)
            expected = formats.profile(expected, intent.policy.formats, format_plans)
            matches = [row for row in profiles if row.get('name') == expected['name']]
            if len(matches) > 1 or (matches and not profile_matches(matches[0], expected)):
                raise ValueError(f'{expected["name"]} was edited in the app. Restore it or rename it before reviewing rules; existing profiles are preserved.')
            plans[tier] = {'payload': expected, 'qualities': names, 'id': matches[0]['id'] if matches else None}
        changes = []
        if intent.scope == 'library':
            if any(not row['id'] for row in plans.values()):
                raise ValueError('A rule profile is missing. Review and save new-request rules again.')
            names = {row['id']: row['name'] for row in profiles}
            for row in await self.titles(app):
                if not valid_id(row['id']) or row['profile_id'] not in names:
                    raise ValueError('A library title or its profile changed. Review it in the app.')
                tier, reason = decide(intent.policy, row['media_id'], row['year'])
                changes.append({**row, 'tier': tier, 'reason': reason, 'old': row['profile_id'],
                                'new': plans[tier]['id'] if tier else row['profile_id'],
                                'old_name': names[row['profile_id']], 'new_name': tier or names[row['profile_id']]})
        previous_formats = await formats.snapshot(self.call, app,
            [row for row in profiles if row['id'] in {change['old'] for change in changes if change['old'] != change['new']}])
        return {'app': app, 'revision': revision, 'config_revision': config_revision, 'binding': binding,
                'policy': intent.policy.model_dump(), 'scope': intent.scope, 'profiles': profiles, 'schema': schema,
                'plans': plans, 'changes': changes, 'format_plans': format_plans, 'previous_formats': previous_formats}

    def public(self, plan):
        return {'app': plan['app'], 'scope': plan['scope'], 'policy': plan['policy'], 'notice': NOTICE,
                'read_only': plan['binding']['integration']['read_only'],
                'format_notice': formats.NOTICE,
                'formats': [{'label': row['label'], 'action': 'Block' if row['score'] < 0 else 'Prefer'}
                            for row in plan['format_plans']],
                'profiles': [{'tier': tier, 'name': row['payload']['name'], 'qualities': row['qualities'],
                              'action': 'Use verified profile' if row['id'] else 'Create dedicated profile',
                              'upgrades': False} for tier, row in plan['plans'].items()],
                'changes': plan['changes'], 'change_count': sum(row['old'] != row['new'] for row in plan['changes'])}

    def check_binding(self, plan):
        if self.binding(plan['app']) != plan['binding']:
            raise Conflict('The app connection changed. Review again before applying.')
        require_writable(self.store, plan['app'])

    async def apply(self, plan):
        self.check_binding(plan)
        fresh = await self.review(ReviewIntent(app=plan['app'], revision=plan['revision'], policy=plan['policy'], scope=plan['scope']))
        if fresh != plan:
            raise Conflict('Rules, profiles or titles changed. Review again before applying.')
        if plan['scope'] == 'library':
            return await self.apply_library(plan)
        app = plan['app']
        resolved = {}
        if plan['policy']['enabled']:
            format_plans = copy.deepcopy(plan['format_plans'])
            if format_plans:
                require_write(app, 'custom-format.create')
            for row in format_plans:
                self.check_binding(plan)
                if row['id'] is None:
                    current = await formats.listing(self.call, app)
                    if any(item['name'] == row['payload']['name'] for item in current):
                        raise Conflict('A custom format appeared during setup. Review the rules again.')
                    self.check_binding(plan)
                    created = await self.call('/api/v3/customformat', 'POST', body=row['payload'], app=app)
                    if not valid_id(created.get('id')) or not formats.matches(created, row['payload']):
                        raise ValueError('A created format could not be verified. Review again; existing settings are preserved.')
                    row['id'] = created['id']
            await formats.verify(self.call, app, format_plans)
            schema = await self.call('/api/v3/qualityprofile/schema', app=app) if format_plans else plan['schema']
            require_write(app, 'quality-profile.create')
            for tier, row in plan['plans'].items():
                payload = formats.profile(curated(schema, tier)[0], Policy.model_validate(plan['policy']).formats, format_plans)
                # A new custom format adds zero-score entries upstream. No other
                # schema change is allowed between preview and profile creation.
                before = {k: v for k, v in row['payload'].items() if k != 'formatItems'}
                if {k: v for k, v in payload.items() if k != 'formatItems'} != before:
                    raise Conflict('The quality schema changed during setup. Review again.')
                await formats.verify(self.call, app, format_plans)
                self.check_binding(plan)
                if row['id']:
                    identity = row['id']
                else:
                    # Never update an existing profile. A failed save can safely reuse these on a new review.
                    current = await self.profiles(app)
                    if any(p['name'] == row['payload']['name'] for p in current):
                        raise Conflict('A profile appeared during setup. Review the rules again.')
                    self.check_binding(plan)
                    created = await self.call('/api/v3/qualityprofile', 'POST', body=payload, app=app)
                    identity = created.get('id')
                verified = await self.call('/api/v3/qualityprofile/' + str(identity), app=app) if valid_id(identity) else None
                if not profile_matches(verified, payload):
                    raise ValueError('A created profile could not be verified. Existing settings are preserved; review again.')
                resolved[tier] = {'id': identity, 'payload': payload,
                                  'formats': [{'id': f['id'], 'payload': f['payload']} for f in format_plans]}
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS quality_rules (app TEXT PRIMARY KEY, revision INTEGER,
                policy TEXT, binding BLOB, profiles TEXT)''')
            current = db.execute('SELECT revision,policy,binding FROM quality_rules WHERE app=?', (app,)).fetchone()
            if ((current[0] if current else 0) != plan['revision'] or
                    db.execute('SELECT revision FROM settings WHERE id=1').fetchone()[0] != plan['config_revision']):
                raise Conflict('Settings changed during setup. Review again; dedicated profiles already created are retained.')
            previous = {'policy': json.loads(current[1]) if current else Policy(enabled=False).model_dump(),
                        'binding': plan['binding'],
                        'previous_binding': json.loads(self.store.cipher.decrypt(current[2])) if current else None}
            db.execute('''CREATE TABLE IF NOT EXISTS quality_rule_restore
                (app TEXT PRIMARY KEY, revision INTEGER, value BLOB)''')
            db.execute('INSERT OR REPLACE INTO quality_rule_restore VALUES(?,?,?)',
                       (app, plan['revision'] + 1, self.store.cipher.encrypt(json.dumps(previous).encode())))
            db.execute('INSERT OR REPLACE INTO quality_rules VALUES(?,?,?,?,?)', (app, plan['revision'] + 1,
                       json.dumps(plan['policy']), self.store.cipher.encrypt(json.dumps(plan['binding']).encode()), json.dumps(resolved)))
        self.store.audit('quality.rules-saved', app)
        return {'message': 'Rules saved for new Stackarr requests. Existing titles keep their profiles.', **self.read(app)}

    def save_run(self, identity, app, run):
        with self.store.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS quality_runs (id TEXT PRIMARY KEY, app TEXT, created REAL, value BLOB)''')
            db.execute('INSERT INTO quality_runs VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',
                       (identity, app, time.time(), self.store.cipher.encrypt(json.dumps(run).encode())))

    async def apply_library(self, plan):
        app, identity = plan['app'], secrets.token_hex(16)
        require_write(app, 'title-quality.update')
        run = {'binding': plan['binding'], 'profiles': plan['profiles'], 'previous_formats': plan['previous_formats'],
               'rows': [dict(row, state='pending') for row in plan['changes'] if row['old'] != row['new']]}
        self.save_run(identity, app, run)  # Durable undo intent before any external write.
        for row in run['rows']:
            try:
                self.check_binding(plan)
                current = title_row(app, await self.call('/api/v3/' + resource(app) + '/' + str(row['id']), app=app))
                if any(current[key] != row[key] for key in ('id', 'media_id', 'year', 'profile_id')):
                    raise Conflict('This title changed after preview.')
                if await self.profiles(app) != plan['profiles']:
                    raise Conflict('Quality profiles changed after preview.')
                await formats.verify(self.call, app, plan['format_plans'])
                row['state'] = 'applying'
                self.save_run(identity, app, run)
                await self.write_title(app, row['id'], row['new'], plan['binding'])
                confirmed = title_row(app, await self.call('/api/v3/' + resource(app) + '/' + str(row['id']), app=app))
                if confirmed['media_id'] != row['media_id'] or confirmed['profile_id'] != row['new']:
                    raise ValueError('The new title profile could not be confirmed.')
                row['state'] = 'applied'
            except (ValueError, Conflict):
                row['state'] = 'uncertain' if row['state'] == 'applying' else 'skipped'
                self.save_run(identity, app, run)
                break  # Keep completed work and a precise, recoverable checkpoint.
            self.save_run(identity, app, run)
        self.store.audit('quality.library-applied', app)
        return self.run_result(identity, run)

    async def write_title(self, app, identity, profile, binding):
        # The editor supports a partial update; omit monitoring, paths and search commands.
        self.check_binding({'app': app, 'binding': binding})
        await self.call('/api/v3/' + resource(app) + '/editor', 'PUT', app=app,
                        body={resource(app) + 'Ids': [identity], 'qualityProfileId': profile, 'moveFiles': False})

    def run(self, app, identity):
        with self.store.db() as db:
            table = db.execute("SELECT 1 FROM sqlite_master WHERE name='quality_runs'").fetchone()
            row = db.execute('SELECT value FROM quality_runs WHERE id=? AND app=?', (identity, app)).fetchone() if table else None
        if not row:
            raise ValueError('Choose a saved quality change from history.')
        return json.loads(self.store.cipher.decrypt(row[0]))

    @staticmethod
    def run_result(identity, run):
        return {'id': identity, 'rows': [{key: row[key] for key in ('id', 'title', 'old_name', 'new_name', 'state')} for row in run['rows']],
                'message': 'Profile assignment results are saved below. Undo checks each title and preserves later edits.'}

    async def undo(self, app, identity):
        run = self.run(app, identity)
        self.check_binding({'app': app, 'binding': run['binding']})
        require_write(app, 'title-quality.update')
        profiles = await self.profiles(app)
        for row in run['rows']:
            if row['state'] not in {'applied', 'applying', 'uncertain', 'undoing', 'undo-conflict'}:
                continue
            try:
                self.check_binding({'app': app, 'binding': run['binding']})
                current = title_row(app, await self.call('/api/v3/' + resource(app) + '/' + str(row['id']), app=app))
                if current['media_id'] != row['media_id']:
                    raise Conflict('The title identity changed.')
                if current['profile_id'] == row['old']:
                    row['state'] = 'undone'
                else:
                    old = next((p for p in run['profiles'] if p['id'] == row['old']), None)
                    actual = next((p for p in profiles if p['id'] == row['old']), None)
                    if current['profile_id'] != row['new'] or old is None or not profile_matches(actual, old):
                        raise Conflict('A title or its original profile changed; preserve the later edit.')
                    await formats.verify(self.call, app, run.get('previous_formats', {}).get(str(row['old']), []))
                    row['state'] = 'undoing'
                    self.save_run(identity, app, run)
                    await self.write_title(app, row['id'], row['old'], run['binding'])
                    checked = title_row(app, await self.call('/api/v3/' + resource(app) + '/' + str(row['id']), app=app))
                    if checked['media_id'] != row['media_id'] or checked['profile_id'] != row['old']:
                        raise ValueError('Undo could not be confirmed.')
                    row['state'] = 'undone'
            except (ValueError, Conflict):
                row['state'] = 'undo-conflict'
            self.save_run(identity, app, run)
        self.store.audit('quality.library-undone', app)
        return self.run_result(identity, run)

    async def request_choice(self, kind, data, server):
        """Bind future-request rules to the same Arr instance Seerr actually uses."""
        app = 'sonarr' if kind == 'tv' else 'radarr'
        revision, policy, binding, profiles = self.saved(app)
        if not policy.enabled:
            return None
        if binding != self.binding(app):
            raise ValueError('The rule’s app connection changed. Review quality rules in Apps.')
        settings = await self.call('/api/v1/settings/' + app)
        actual = next((row for row in settings if row.get('id') == server['id']), None)
        integration = self.store.config()[1].integrations[app]
        peer = urlsplit(integration.peer_url or integration.url)
        if (not actual or actual.get('hostname') != peer.hostname or actual.get('port') != (peer.port or (443 if peer.scheme == 'https' else 80))
                or actual.get('useSsl', False) != (peer.scheme == 'https') or (actual.get('baseUrl') or '').rstrip('/') != peer.path.rstrip('/')
                or actual.get('apiKey') != binding['credential'].get('api_key')):
            raise ValueError('Seerr points to a different app. Review its connection before using quality rules.')
        current = await self.profiles(app)
        expected_formats = {row['id']: row for saved in profiles.values() for row in saved.get('formats', [])}
        await formats.verify(self.call, app, list(expected_formats.values()))
        for saved in profiles.values():
            profile = next((row for row in current if row['id'] == saved['id']), None)
            if not profile_matches(profile, saved['payload']):
                raise ValueError('A rule profile changed. Review quality rules in Apps.')
        external = (data.get('externalIds') or {}).get('tvdbId') if kind == 'tv' else data.get('id')
        if not valid_id(external):
            raise ValueError('This title has no verified TVDB or TMDB identity. Check its metadata before requesting it.')
        date = data.get('firstAirDate' if kind == 'tv' else 'releaseDate') or ''
        year = int(date[:4]) if isinstance(date, str) and date[:4].isdigit() and len(date) >= 4 else None
        tier, reason = decide(policy, external, year)
        return {'revision': revision, 'external': external, 'year': year,
                'profiles': {key: row['id'] for key, row in profiles.items()}, 'tier': tier,
                'verified_profiles': sorted(
                    [{'id': row['id'], 'name': row['payload']['name']} for row in profiles.values()],
                    key=lambda row: row['id']),
                'profile_id': profiles[tier]['id'] if tier else None, 'reason': reason}

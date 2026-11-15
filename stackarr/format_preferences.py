"""Immutable release-label custom formats for reviewed download preferences."""

import copy
import hashlib
import json
from typing import Literal

from pydantic import Field

from .config import Model

Preference = Literal['any', 'prefer', 'avoid']
PREFER_SCORE = 100
BLOCK_SCORE = -10000  # Greater than every possible positive preference combined.
PATTERNS = {
    'dolby_vision': r'(?<![a-zA-Z0-9])(?:DV|DoVi|Dolby[ ._-]?Vision|dvhe|dvh1)(?![a-zA-Z0-9])|(?<![a-zA-Z0-9])(?:DV|DoVi)(?=HDR(?:10)?(?![a-zA-Z0-9]))',
    'ten_bit': r'(?<![a-zA-Z0-9])(?:10[ ._-]?bit|hi10p|main[ ._-]?10)(?![a-zA-Z0-9])',
    'h264': r'(?<![a-zA-Z0-9])(?:[xh][ ._-]?264|AVC)(?![a-zA-Z0-9])',
    'hevc': r'(?<![a-zA-Z0-9])(?:[xh][ ._-]?265|HEVC)(?![a-zA-Z0-9])',
    'av1': r'(?<![a-zA-Z0-9])AV1(?![a-zA-Z0-9])',
    'vp9': r'(?<![a-zA-Z0-9])VP[ ._-]?9(?![a-zA-Z0-9])',
}
NAMES = {'dolby_vision': 'Dolby Vision', 'ten_bit': '10-bit', 'h264': 'H.264 / AVC',
         'hevc': 'H.265 / HEVC', 'av1': 'AV1', 'vp9': 'VP9'}
NOTICE = ('Block and Avoid reject labelled matches, even when other preferences match. '
          'Prefer ranks releases within an allowed quality; it does not require that format or enable upgrades. '
          'Matching uses release names. Missing or incorrect labels can bypass these filters. '
          '10-bit matching needs a 10-bit, Hi10P or Main10 label; HDR alone is not treated as a bit-depth label.')


class CodecPreferences(Model):
    h264: Preference = 'any'
    hevc: Preference = 'any'
    av1: Preference = 'any'
    vp9: Preference = 'any'


class FormatPreferences(Model):
    block_dolby_vision: bool = False
    ten_bit: Preference = 'any'
    codecs: CodecPreferences = Field(default_factory=CodecPreferences)

    def scores(self):
        result = {'dolby_vision': BLOCK_SCORE} if self.block_dolby_vision else {}
        for key, value in {'ten_bit': self.ten_bit, **self.codecs.model_dump()}.items():
            if value != 'any':
                result[key] = PREFER_SCORE if value == 'prefer' else BLOCK_SCORE
        return result

    def suffix(self):
        if not self.scores():
            return 'v1'
        # Include detector definitions: changing a matcher must never silently
        # change the meaning of an existing profile or its library assignments.
        value = {'preferences': self.model_dump(), 'patterns': PATTERNS, 'version': 1}
        return 'v2 ' + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:12]


def definition(key):
    digest = hashlib.sha256(PATTERNS[key].encode()).hexdigest()[:8]
    return {'name': 'Stackarr ' + NAMES[key] + ' v1 ' + digest, 'includeCustomFormatWhenRenaming': False,
            'specifications': [{'name': NAMES[key], 'implementation': 'ReleaseTitleSpecification',
                'negate': False, 'required': False, 'fields': [{'name': 'value', 'value': PATTERNS[key]}]}]}


def canonical(value):
    if not isinstance(value, dict):
        return None
    return {'name': value.get('name'), 'includeCustomFormatWhenRenaming': value.get('includeCustomFormatWhenRenaming'),
            'specifications': [{'name': spec.get('name'), 'implementation': spec.get('implementation'),
                'negate': spec.get('negate'), 'required': spec.get('required'),
                'fields': sorted([(f.get('name'), f.get('value')) for f in spec.get('fields', [])], key=lambda f: str(f[0]))}
                for spec in value.get('specifications', [])]}


def matches(actual, expected):
    try:
        return canonical(actual) == canonical(expected)
    except (AttributeError, TypeError):
        return False


async def review(call, app, preferences):
    wanted = preferences.scores()
    if not wanted:
        return []
    schema = await call('/api/v3/customformat/schema', app=app)
    if not isinstance(schema, list) or not any(row.get('implementation') == 'ReleaseTitleSpecification'
            and any(f.get('name') == 'value' for f in row.get('fields', [])) for row in schema):
        raise ValueError('This app does not support release-label format preferences. No settings were changed.')
    current = await listing(call, app)
    result = []
    for index, (key, score) in enumerate(wanted.items()):
        payload = definition(key)
        found = [row for row in current if row.get('name') == payload['name']]
        if len(found) > 1 or (found and not matches(found[0], payload)):
            raise ValueError(f'The {NAMES[key]} format was edited in the app. Restore or rename it before reviewing preferences.')
        result.append({'key': key, 'label': NAMES[key], 'score': score, 'payload': payload,
                       'id': found[0]['id'] if found else None, 'placeholder': -index - 1})
    return result


async def listing(call, app):
    rows = await call('/api/v3/customformat', app=app)
    if (not isinstance(rows, list) or len(rows) > 1000 or any(not isinstance(row, dict)
            or type(row.get('id')) is not int or row['id'] <= 0 for row in rows)
            or len({row['id'] for row in rows}) != len(rows)):
        raise ValueError('Custom formats could not be verified.')
    return rows


async def verify(call, app, expected):
    if not expected:
        return
    current = await listing(call, app)
    for row in expected:
        actual = next((item for item in current if item['id'] == row['id']), None)
        if not matches(actual, row['payload']):
            raise ValueError('A download format filter changed. Review quality rules in Apps before requesting.')


async def snapshot(call, app, profiles):
    """Keep the meaning of original profiles so undo preserves later filter edits."""
    wanted = {}
    for row in profiles:
        signature = score_signature(row.get('formatItems', []))
        if signature is None:
            raise ValueError('Original profile format scores could not be verified.')
        if signature:
            wanted[str(row['id'])] = [identity for identity, _ in signature]
    current = await listing(call, app) if wanted else []
    by_id = {row['id']: row for row in current}
    if any(identity not in by_id for ids in wanted.values() for identity in ids):
        raise ValueError('An original profile format is missing. Review it in the app.')
    return {profile: [{'id': identity, 'payload': by_id[identity]} for identity in ids]
            for profile, ids in wanted.items()}


def profile(payload, preferences, plans):
    result = copy.deepcopy(payload)
    result['name'] = result['name'].removesuffix('v1') + preferences.suffix()
    by_id = {row['format']: row for row in result.get('formatItems', [])}
    for row in plans:
        identity = row['id'] or row['placeholder']
        by_id[identity] = {'format': identity, 'name': row['payload']['name'], 'score': row['score']}
    result['formatItems'] = list(by_id.values())
    return result


def score_signature(items):
    """Arr automatically adds neutral entries when any custom format is created."""
    if not isinstance(items, list) or any(not isinstance(row, dict) or type(row.get('format')) is not int
            or type(row.get('score')) is not int for row in items):
        return None
    if len({row['format'] for row in items}) != len(items):
        return None
    return sorted((row['format'], row['score']) for row in items if row['score'] != 0)

import copy
import re

import pytest
from pydantic import ValidationError
from test_quality_rules import fixture as arr_fixture
from test_quality_rules import save_rules

from stackarr.format_preferences import BLOCK_SCORE, PATTERNS, FormatPreferences
from stackarr.quality import label
from stackarr.quality_rules import Policy, ReviewIntent, profile_matches

fixture = arr_fixture


@pytest.mark.parametrize('release,match', [
    ('Film.2020.2160p.WEB-DL.DV.HEVC', True), ('Film.2020.DoVi.HDR10.x265', True),
    ('Film.Dolby.Vision.Main10', True), ('Film.dolby-vision.x265', True),
    ('Film_DV_HDR10_HEVC', True), ('Film.DVHDR10.HEVC', True), ('Film.dvh1.05.06', True), ('Film.dvhe.08.06', True),
    ('Film.Dolby.Atmos.HEVC', False), ('Film.DVDRip.x264', False),
    ('Film.HDR10Plus.HEVC', False), ('Film.HLG.HEVC', False), ('Film.ADVENTURE.x264', False),
])
def test_dolby_labels_and_false_positives(release, match):
    assert bool(re.search(PATTERNS['dolby_vision'], release, re.I)) is match


@pytest.mark.parametrize('key,release,match', [
    ('ten_bit', 'Film.10bit.HEVC', True), ('ten_bit', 'Film.10-bit.x265', True),
    ('ten_bit', 'Film.Hi10P', True), ('ten_bit', 'Film.Main.10.HEVC', True),
    ('ten_bit', 'Film.HDR10', False), ('ten_bit', 'Film_10bit_HEVC', True), ('ten_bit', 'Film.12bit', False),
    ('h264', 'Film.H.264', True), ('h264', 'Film.AVC', True), ('h264', 'Film.HEVC', False),
    ('hevc', 'Film_x265_10bit', True), ('hevc', 'Film.x265', True), ('hevc', 'Film.H.265', True), ('hevc', 'Film.HEVC', True),
    ('av1', 'Film.AV1', True), ('av1', 'Film.AVI', False), ('vp9', 'Film.VP9', True),
])
def test_codec_and_bit_depth_labels(key, release, match):
    assert bool(re.search(PATTERNS[key], release, re.I)) is match


def test_blocks_cannot_be_outvoted_by_all_preferences():
    prefs = FormatPreferences(block_dolby_vision=True, ten_bit='prefer',
        codecs={key: 'prefer' for key in ['h264', 'hevc', 'av1', 'vp9']})
    assert sum(prefs.scores().values()) < 0
    assert FormatPreferences(ten_bit='avoid', codecs={'hevc': 'prefer'}).scores()['ten_bit'] == BLOCK_SCORE
    with pytest.raises(ValidationError):
        FormatPreferences(codecs={'unknown': 'prefer'})
    with pytest.raises(ValidationError):
        FormatPreferences(ten_bit='require')


async def test_preferences_create_verified_profiles_and_never_update_existing_ones(fixture):
    _, app, arr, home = fixture
    original = copy.deepcopy(arr.profiles[0])
    policy = Policy(formats={'block_dolby_vision': True, 'ten_bit': 'prefer', 'codecs': {'hevc': 'prefer', 'av1': 'avoid'}})
    await save_rules(fixture, policy)
    assert len(arr.formats) == 4 and len(arr.profiles) == 4
    assert profile_matches(arr.profiles[0], original)
    assert all(method == 'POST' for method, _, _ in arr.writes)
    assert all(row['qualityProfileId'] == 7 for row in arr.titles)
    saved = home.rules.saved(app)[3]
    for tier, row in saved.items():
        assert label(row['payload']['name']) == tier
        assert row['payload']['minFormatScore'] == 0 and row['payload']['upgradeAllowed'] is False
        scores = {item['format']: item['score'] for item in row['payload']['formatItems']}
        assert sorted(scores.values()) == [-10000, -10000, 100, 100]
        assert len(row['formats']) == 4
    count = len(arr.writes)
    await save_rules(fixture, policy)
    assert len(arr.writes) == count
    changed = policy.model_copy(deep=True)
    changed.formats.ten_bit = 'avoid'
    before = copy.deepcopy(arr.profiles)
    await save_rules(fixture, changed)
    assert arr.profiles[:len(before)] == before and len(arr.formats) == 4
    assert len(arr.profiles) == 7
    assert not {row['id'] for row in saved.values()} & {row['id'] for row in home.rules.saved(app)[3].values()}


async def test_filter_tampering_blocks_review_apply_and_request(fixture):
    from stackarr.format_preferences import verify

    _, app, arr, home = fixture
    policy = Policy(formats={'block_dolby_vision': True})
    await save_rules(fixture, policy)
    plan = await home.rules.review(ReviewIntent(app=app, revision=1, policy=policy))
    arr.writes.clear()
    arr.formats[0]['specifications'][0]['fields'][0]['value'] = 'NEVER_MATCH'
    with pytest.raises(ValueError, match='edited'):
        await home.rules.apply(plan)
    with pytest.raises(ValueError, match='filter changed'):
        await verify(home.call, app, home.rules.saved(app)[3]['4K']['formats'])
    assert not arr.writes


async def test_interrupted_custom_format_creation_can_be_reviewed_without_duplicates(fixture):
    _, _, arr, _ = fixture
    arr.fail_format_write = True
    policy = Policy(formats={'block_dolby_vision': True, 'ten_bit': 'avoid'})
    with pytest.raises(ValueError):
        await save_rules(fixture, policy)
    assert len(arr.formats) == 1 and len(arr.profiles) == 1
    await save_rules(fixture, policy)
    assert len(arr.formats) == 2 and len(arr.profiles) == 4


async def test_imported_read_only_formats_are_preview_only(fixture):
    store, app, arr, home = fixture
    revision, config = store.config()
    config.integrations[app].read_only = True
    store.save(config, revision)
    plan = await home.rules.review(ReviewIntent(app=app, revision=0, policy=Policy(formats={'block_dolby_vision': True})))
    assert home.rules.public(plan)['formats'] == [{'label': 'Dolby Vision', 'action': 'Block'}]
    with pytest.raises(ValueError, match='read-only'):
        await home.rules.apply(plan)
    assert not arr.writes


async def test_added_neutral_formats_preserve_old_profiles_and_library_undo(fixture):
    _, app, arr, home = fixture
    policy = await save_rules(fixture)
    result = await home.rules.apply(await home.rules.review(ReviewIntent(app=app, revision=1, policy=policy, scope='library')))
    original = copy.deepcopy(arr.profiles)
    await save_rules(fixture, Policy(formats={'ten_bit': 'prefer'}))
    assert all(profile_matches(actual, expected) for actual, expected in zip(arr.profiles, original))
    undone = await home.rules.undo(app, result['id'])
    assert all(row['state'] == 'undone' for row in undone['rows'])
    edited = copy.deepcopy(arr.profiles[0])
    edited['formatItems'][0]['score'] = 100
    assert not profile_matches(edited, original[0])

async def test_undo_preserves_later_original_custom_format_edits(fixture):
    _, app, arr, home = fixture
    original = Policy(formats={'block_dolby_vision': True})
    await save_rules(fixture, original)
    original_id = home.rules.saved(app)[3]['1080p']['id']
    for row in arr.titles:
        row['qualityProfileId'] = original_id
    changed = Policy(formats={'ten_bit': 'prefer'})
    await save_rules(fixture, changed)
    result = await home.rules.apply(await home.rules.review(ReviewIntent(app=app, revision=2, policy=changed, scope='library')))
    arr.writes.clear()
    arr.formats[0]['specifications'][0]['fields'][0]['value'] = 'EDITED_LATER'
    undone = await home.rules.undo(app, result['id'])
    assert undone['rows'] and all(row['state'] == 'undo-conflict' for row in undone['rows'])
    assert not arr.writes

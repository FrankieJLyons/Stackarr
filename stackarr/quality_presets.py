"""Versioned beginner recipes. No upstream guide database or live guide sync."""

from .quality_rules import Policy

VERSION = '2026-11-14.1'
SOURCES = [
    {'label': 'Sonarr profiles · TRaSH Guides', 'url': 'https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles/'},
    {'label': 'Radarr profiles · TRaSH Guides', 'url': 'https://trash-guides.info/Radarr/radarr-setup-quality-profiles/'},
    {'label': 'Sonarr settings · Servarr', 'url': 'https://wiki.servarr.com/sonarr/settings'},
]


def catalog():
    recipes = [
        ('everyday-1080p', 'Everyday 1080p', '1080p', True,
         'A starting point for most HD libraries. Allows 1080p WEB, HDTV and Blu-ray encodes. No remuxes or disc images.'),
        ('smaller-720p', 'Smaller 720p', '720p', False,
         'Choose a lower resolution when space or bandwidth matters. Actual file size still depends on the release and your app-wide limits.'),
        ('high-resolution-4k', 'High resolution 4K', '4K', False,
         'For a 4K library and tested playback devices. Larger downloads and HDR or codec compatibility need extra care; 4K does not guarantee HDR.'),
    ]
    return {'version': VERSION, 'sources': SOURCES, 'presets': [
        {'id': key, 'name': name, 'tier': tier, 'recommended': recommended, 'description': description,
         'policy': Policy(older=tier, newer=tier, selected_profiles=True).model_dump()}
        for key, name, tier, recommended, description in recipes
    ], 'scope': 'New requests made through Stackarr only. Requests made directly in Seerr or the other apps keep their own defaults.',
        'tradeoffs': ['Automatic quality and custom-format upgrades are off for these profiles.',
                      'No codec, language or HDR preference is imposed. Existing app language rules still apply.',
                      'App-wide file-size limits, naming, seeding and deletion settings are kept.',
                      'Existing title exceptions are replaced in the preview. Cancel to keep them, or edit the rules before applying.',
                      'Existing titles require a separate library preview. No search, file move or deletion is started.']}

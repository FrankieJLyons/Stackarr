"""Explicit request quality choices, resolved against the app's real profiles."""

import re
from typing import Literal

QualityProfile = Literal["", "HD-1080p", "Ultra-HD", "SD", "HD-720p"]
LABELS = {"HD-1080p": "1080p", "Ultra-HD": "4K / UHD", "SD": "SD", "HD-720p": "720p",
          "Stackarr SD v1": "SD", "Stackarr 720p v1": "720p", "Stackarr 1080p v1": "1080p", "Stackarr 4K v1": "4K"}


def label(name):
    managed = re.fullmatch(r'Stackarr (SD|720p|1080p|4K) v2 [0-9a-f]{12}', name)
    return managed[1] if managed else LABELS.get(name, name)


def select_profile(profiles, name):
    """Never substitute another profile for an explicitly reviewed preference."""
    if not isinstance(profiles, list):
        raise ValueError("The app did not return quality profiles")
    matches = [row for row in profiles if isinstance(row, dict) and row.get("name") == name]
    if len(matches) != 1 or type(matches[0].get("id")) is not int or matches[0]["id"] <= 0:
        raise ValueError("The selected quality profile is unavailable or ambiguous")
    return matches[0]

"""Session-bound preset previews, with an independent live-deletion gate."""

import secrets
import time
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import Field, field_validator

from .cleanup_presets import CleanupPresets, Intent
from .config import Model


class Apply(Model):
    review_token: str = Field(min_length=20, max_length=128)


class Saved(Model):
    run_id: str = Field(pattern=r'^[0-9a-f]{32}$')


class LiveApply(Apply):
    confirmation: Literal['ENABLE LIVE DELETION']
    acknowledge_irreversible: bool = Field(strict=True)

    @field_validator('acknowledge_irreversible')
    @classmethod
    def acknowledged(cls, value):
        if value is not True:
            raise ValueError('Acknowledge that live cleanup can permanently delete downloads or files.')
        return value


def register(app, session, lock, request_lock, store, transport):
    feature = CleanupPresets(store, transport)
    app.state.cleanup_presets = feature
    reviews = {}

    @app.get('/api/cleanuparr-presets')
    async def status(request: Request):
        session(request)
        try:
            return await feature.status()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    async def preview(kind, body, request):
        _, owner = session(request)
        async with lock:
            # A new preview invalidates this session's previous cleanup preview of any kind.
            reviews.pop(owner, None)
            try:
                plan = await feature.review(body) if kind == 'preset' else await (
                    feature.live_review(body.run_id) if kind == 'live' else feature.restore_review(body.run_id))
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
            now = time.monotonic()
            for key in list(reviews):
                if reviews[key][1] <= now:
                    del reviews[key]
            if len(reviews) >= 100:
                raise HTTPException(429, 'Too many pending previews. Try again shortly.')
            token = secrets.token_urlsafe(32)
            reviews[owner] = (token, now + 600, plan)
            return feature.public(plan) | {'review_token': token}

    @app.post('/api/cleanuparr-presets/review')
    async def preset_preview(body: Intent, request: Request):
        return await preview('preset', body, request)

    @app.post('/api/cleanuparr-presets/live/review')
    async def live_preview(body: Saved, request: Request):
        return await preview('live', body, request)

    @app.post('/api/cleanuparr-presets/restore/review')
    async def restore_preview(body: Saved, request: Request):
        return await preview('restore', body, request)

    async def apply(kind, body, request):
        _, owner = session(request)
        async with lock, request_lock:
            row = reviews.get(owner)
            if (not row or not secrets.compare_digest(row[0], body.review_token) or row[1] <= time.monotonic()
                    or (row[2]['kind'] == 'live') != (kind == 'live')):
                raise HTTPException(409, 'Preview this Cleanuparr action again before applying it.')
            del reviews[owner]
            try:
                return await feature.apply(row[2])
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None

    @app.post('/api/cleanuparr-presets/apply')
    async def preset_apply(body: Apply, request: Request):
        return await apply('preset', body, request)

    @app.post('/api/cleanuparr-presets/live/apply')
    async def live_apply(body: LiveApply, request: Request):
        return await apply('live', body, request)

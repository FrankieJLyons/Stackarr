"""Owner-only, session-bound media setup previews. Plans never cross into the browser."""

import secrets
import time
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import Field

from .config import Model
from .download_protection import ProtectionIntent
from .library_mapping import MappingIntent


class Apply(Model):
    review_token: str = Field(min_length=20, max_length=128)


def register(app, session, lock, request_lock, protection, mapping):
    reviews = {}

    async def review(kind, intent, request):
        _, owner = session(request)
        async with lock:
            reviews.pop((kind, owner), None)
            try:
                feature = protection if kind == 'protection' else mapping
                plan = await feature.review(intent)
                if plan.get('needs_choice'):
                    return feature.public(plan)
                now = time.monotonic()
                for key in list(reviews):
                    if reviews[key][1] <= now:
                        del reviews[key]
                if len(reviews) >= 100:
                    raise HTTPException(429, 'Too many pending reviews. Try again shortly.')
                token = secrets.token_urlsafe(32)
                reviews[kind, owner] = (token, now + 600, plan)
                return feature.public(plan) | {'review_token': token}
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None

    @app.post('/api/download-protection/review')
    async def protection_review(body: ProtectionIntent, request: Request):
        return await review('protection', body, request)

    @app.post('/api/library-mapping/review')
    async def mapping_review(body: MappingIntent, request: Request):
        return await review('mapping', body, request)

    async def apply(kind, body, request):
        _, owner = session(request)
        async with lock, request_lock:
            row = reviews.get((kind, owner))
            if not row or not secrets.compare_digest(row[0], body.review_token) or row[1] <= time.monotonic():
                raise HTTPException(409, 'This review expired or was used. Preview the settings again.')
            del reviews[kind, owner]
            try:
                return await (protection if kind == 'protection' else mapping).apply(row[2])
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None

    @app.post('/api/download-protection/apply')
    async def protection_apply(body: Apply, request: Request):
        return await apply('protection', body, request)

    @app.post('/api/library-mapping/apply')
    async def mapping_apply(body: Apply, request: Request):
        return await apply('mapping', body, request)

    @app.get('/api/download-protection/history')
    def protection_history(request: Request):
        session(request)
        return {'history': protection.history()}

    @app.post('/api/download-protection/history/{identity}/undo')
    async def protection_undo(identity: str, request: Request):
        session(request)
        async with lock:
            try:
                return await protection.undo(identity)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None

    @app.get('/api/library-mapping')
    def mapping_status(request: Request):
        session(request)
        return mapping.status()

    @app.post('/api/library-mapping/{key}/pause')
    async def mapping_pause(key: Literal['sonarr', 'radarr'], request: Request):
        session(request)
        async with lock, request_lock:
            return mapping.pause(key)

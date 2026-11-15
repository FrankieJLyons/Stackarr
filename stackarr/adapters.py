"""Capabilities implemented by this build, not promises about upstream products."""

from dataclasses import asdict, dataclass

from .config import APP_IDS


@dataclass(frozen=True)
class Adapter:
    tables: tuple[str, ...]
    authentication: str
    api: str
    writes: tuple[str, ...] = ()
    status: str = "preview"
    install: str = "compose-plan"
    backup: str = "not-implemented"
    discovery: str = "manual-address"


ADAPTERS = {
    "plex": Adapter(("streams",), "token", "sessions JSON", ("library.create", "library.scan")),
    "sonarr": Adapter(("health", "queue", "blocklist"), "api-key", "v3", ("download-client.create", "root-folder.create", "initial-login.create", "plex-notification.create", "quality-profile.create", "custom-format.create", "title-quality.update", "completed-imports.configure")),
    "radarr": Adapter(("health", "queue", "blocklist"), "api-key", "v3", ("download-client.create", "root-folder.create", "initial-login.create", "plex-notification.create", "quality-profile.create", "custom-format.create", "title-quality.update", "completed-imports.configure")),
    "prowlarr": Adapter(("health", "sources"), "api-key", "v1", ("application.create", "initial-login.create", "indexer.create")),
    "qbittorrent": Adapter(("downloads",), "session-login", "v2", ("category.create", "protection.configure", "category-paths.configure")),
    "cleanuparr": Adapter(("health",), "api-key", "configuration safety status", ("initial-login.create", "connection.create", "safe-mode.configure", "presets.configure")),
    "tautulli": Adapter(("streams",), "api-key", "v2 get_activity", ("initial-login.create", "plex-connection.configure")),
    "kuma": Adapter(("monitoring",), "metrics-key", "Prometheus metrics", ("initial-login.create", "monitor.create", "metrics-key.create")),
    "seerr": Adapter(("health", "requests"), "api-key", "v1 status, titles and requests", ("arr-connection.create", "plex-scan-schedule.configure", "media-request.create", "initial-plex-setup.configure")),
}


def capabilities():
    if set(ADAPTERS) != set(APP_IDS):
        raise RuntimeError("Every catalog app needs an adapter declaration")
    return {key: asdict(value) for key, value in ADAPTERS.items()}


def require_write(app, action):
    adapter = ADAPTERS.get(app)
    if adapter is None or action not in adapter.writes:
        raise ValueError("This adapter does not support that write action")
CLEANUP_FLAGS = {job: ("searchEnabled", "proactiveSearchEnabled") if job == "seeker" else ("enabled",)
                 for job in ("queue_cleaner", "download_cleaner", "malware_blocker", "seeker", "blacklist_sync")}

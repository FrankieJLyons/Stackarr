"""Single versioned configuration contract. Credentials live separately."""

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .quality import QualityProfile

APP_IDS = ("plex", "sonarr", "radarr", "prowlarr", "qbittorrent", "cleanuparr", "tautulli", "kuma", "seerr")
CATALOG = {
    "plex": {"name": "Plex", "port": 32400, "image": "plexinc/pms-docker:1.43.4.10903-e5521bd8c", "config": "/config"},
    "sonarr": {
        "name": "Sonarr",
        "port": 8989,
        "image": "lscr.io/linuxserver/sonarr:latest",
        "config": "/config",
    },
    "radarr": {
        "name": "Radarr",
        "port": 7878,
        "image": "lscr.io/linuxserver/radarr:latest",
        "config": "/config",
    },
    "prowlarr": {
        "name": "Prowlarr",
        "port": 9696,
        "image": "lscr.io/linuxserver/prowlarr:latest",
        "config": "/config",
    },
    "qbittorrent": {
        "name": "qBittorrent",
        "port": 8080,
        "image": "lscr.io/linuxserver/qbittorrent:latest",
        "config": "/config",
    },
    "cleanuparr": {
        "name": "Cleanuparr",
        "port": 11011,
        "image": "ghcr.io/cleanuparr/cleanuparr:latest",
        "config": "/config",
    },
    "tautulli": {
        "name": "Tautulli",
        "port": 8181,
        "image": "ghcr.io/tautulli/tautulli:latest",
        "config": "/config",
    },
    "kuma": {"name": "Uptime Kuma", "port": 3001, "image": "louislam/uptime-kuma:2", "config": "/app/data"},
    "seerr": {"name": "Seerr", "port": 5055, "image": "stackarr-seerr:3.5.0-stackarr.2", "config": "/app/config"},
}


def container_port(key, integration):
    # LinuxServer qBittorrent requires matching WebUI host/container ports for CSRF.
    return (integration.port or CATALOG[key]["port"]) if key == "qbittorrent" else CATALOG[key]["port"]


def validate_url(value: str, origin_only: bool = False) -> str:
    if not value:
        return value
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or any(c.isspace() for c in value)
    ):
        raise ValueError("Use an HTTP(S) address without credentials, query parameters, or fragments")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Port must be between 1 and 65535") from exc
    if origin_only and parsed.path not in ("", "/"):
        raise ValueError("Use an origin without a path; subpath hosting is not supported yet")
    return value.rstrip("/")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Integration(Model):
    enabled: bool = False
    read_only: bool = False
    request_host: str = Field(default="", max_length=32)
    mode: Literal["connect", "install"] = "connect"
    url: str = ""
    browser_url: str = ""
    peer_url: str = ""
    port: int = Field(default=0, ge=0, le=65535)
    visible: bool = True
    quality_profile: QualityProfile = ""

    @model_validator(mode="after")
    def native_connection_only(self):
        if self.read_only and self.mode != "connect":
            raise ValueError("Read-only imported apps must stay connected to their existing installation")
        if self.request_host:
            parsed = urlsplit(self.url)
            if (not self.read_only or not re.fullmatch(r"127\.0\.0\.1:[1-9][0-9]{0,4}", self.request_host)
                    or parsed.scheme != "http" or parsed.hostname != "host.docker.internal"
                    or parsed.port != int(self.request_host.split(":")[1])):
                raise ValueError("Native Host routing must match a read-only Docker-to-host connection")
        return self

    @field_validator("url", "browser_url", "peer_url")
    @classmethod
    def address(cls, value):
        return validate_url(value)


class Storage(Model):
    data_root: str = ""
    container_root: Literal["/data"] = "/data"
    uid: int = Field(default=1000, ge=1)
    gid: int = Field(default=1000, ge=1)
    minimum_free_gb: int = Field(default=10, ge=1, le=100000)

    @field_validator("data_root")
    @classmethod
    def safe_path(cls, value):
        if any(c in value for c in ("\n", "\r", "\0", "$")):
            raise ValueError("Path contains unsupported control or substitution characters")
        return value


class Dashboard(Model):
    refresh_seconds: int = Field(default=30, ge=10, le=3600)
    stale_seconds: int = Field(default=120, ge=20, le=86400)
    appearance: Literal["dark", "light", "system"] = "dark"
    accent: Literal["blue", "red", "yellow", "green", "orange", "purple"] = "blue"
    overview_widgets: list[str] = Field(default_factory=lambda: [
        "downloads", "streams", "sonarr-queue", "radarr-queue", "blocklist", "sources", "storage", "apps"
    ], max_length=12)
    order: list[str] = Field(default_factory=lambda: list(APP_IDS))
    page_size: int = Field(default=10, ge=5, le=100)

    @field_validator("overview_widgets")
    @classmethod
    def valid_widgets(cls, value):
        known = {"apps", "downloads", "queue", "streams", "sonarr-queue", "radarr-queue",
                 "sources", "blocklist", "health", "requests", "monitors", "storage"}
        if len(set(value)) != len(value) or set(value) - known:
            raise ValueError("Choose each supported overview card at most once")
        return value

    @field_validator("order")
    @classmethod
    def valid_order(cls, value):
        if set(value) != set(APP_IDS) or len(value) != len(APP_IDS):
            raise ValueError("Order must contain each integration exactly once")
        if value.index("sonarr") > value.index("radarr"):
            raise ValueError("Sonarr must precede Radarr")
        return value


class StorageGuard(Model):
    """A policy only; no collector or installer may act on it implicitly."""

    enabled: bool = False
    monitored_path: str = ""
    pause_below_gb: int = Field(default=50, ge=1, le=100000)
    resume_at_gb: int = Field(default=100, ge=2, le=100000)
    managed_categories: list[Literal["sonarr", "radarr"]] = Field(
        default_factory=lambda: ["sonarr", "radarr"]
    )

    @field_validator("monitored_path")
    @classmethod
    def guard_path(cls, value):
        if any(c in value for c in ("\n", "\r", "\0", "$")):
            raise ValueError("Path contains unsupported control or substitution characters")
        return value

    @model_validator(mode="after")
    def thresholds(self):
        if self.resume_at_gb <= self.pause_below_gb:
            raise ValueError("Storage Guard resume threshold must exceed its pause threshold")
        if self.enabled and not self.monitored_path:
            raise ValueError("Storage Guard needs a monitored path")
        return self


class Maintenance(Model):
    backups_enabled: bool = False
    backup_retention: int = Field(default=7, ge=1, le=90)
    notifications_enabled: bool = False
    notification_url: str = ""
    recovery_enabled: Literal[False] = False
    delete_downloads: Literal[False] = False
    preserve_partial_downloads: Literal[True] = True
    updates: Literal["manual"] = "manual"
    storage_guard: StorageGuard = Field(default_factory=StorageGuard)

    @field_validator("notification_url")
    @classmethod
    def notification_address(cls, value):
        value = validate_url(value)
        if value and not value.startswith("https://"):
            raise ValueError("Notification webhooks require HTTPS")
        return value


class Config(Model):
    version: Literal[3] = 3

    @model_validator(mode="before")
    @classmethod
    def migrate(cls, value):
        # Copy the input so importing a draft never changes its source object.
        if isinstance(value, dict) and value.get("version") == 1:
            value = {**value, "version": 2}
        if isinstance(value, dict) and value.get("version") == 2:
            value = {**value, "version": 3}
            if "integrations" in value:
                value["integrations"] = {"seerr": Integration().model_dump(), **value["integrations"]}
            if "dashboard" in value and "order" in value["dashboard"]:
                order = list(value["dashboard"]["order"])
                value["dashboard"] = {**value["dashboard"], "order": order if "seerr" in order else order + ["seerr"]}
        return value
    integrations: dict[str, Integration] = Field(default_factory=lambda: {k: Integration() for k in APP_IDS})
    storage: Storage = Field(default_factory=Storage)
    dashboard: Dashboard = Field(default_factory=Dashboard)
    maintenance: Maintenance = Field(default_factory=Maintenance)

    @model_validator(mode="after")
    def validate_apps(self):
        if set(self.integrations) != set(APP_IDS):
            raise ValueError("Configuration must contain every supported integration entry; import older files to upgrade them.")
        ports = []
        for key, item in self.integrations.items():
            if item.quality_profile and key not in {"sonarr", "radarr"}:
                raise ValueError("Request quality profiles belong to Sonarr or Radarr")
            if item.enabled and item.mode == "connect" and not item.url:
                raise ValueError(f"{CATALOG[key]['name']}: an address is required for connect-only mode")
            if item.enabled and item.mode == "install":
                ports.append(item.port or CATALOG[key]["port"])
        if len(ports) != len(set(ports)) or 8787 in ports:
            raise ValueError("Selected installation ports conflict with one another or Stackarr (8787)")
        if self.dashboard.stale_seconds < self.dashboard.refresh_seconds:
            raise ValueError("Stale threshold must be at least the refresh interval")
        return self

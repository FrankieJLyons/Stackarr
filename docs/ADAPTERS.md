# Adapter contract

`stackarr/adapters.py` declares the capabilities implemented by this build. The
authenticated configuration API publishes those declarations for UI consumers.
Every catalog entry must have a declaration, and the wiring executor rejects
undeclared write actions. Authentication login is a transport operation; it does
not grant permission to change downloads or application configuration.

| App | Read views | Explicit writes | Interface |
| --- | --- | --- | --- |
| Plex | Streams | None | Sessions JSON |
| Sonarr, Radarr | Health, queue, blocklist | Create download client | API v3 |
| Prowlarr | Health, sources | Create application | API v1 |
| qBittorrent | Downloads | None | Web API v2 |
| Tautulli | Streams | None | API v2 get_activity |
| Uptime Kuma | Monitoring | None | Prometheus metrics |
| Cleanuparr | Link only | None | No verified collector |
| Seerr | Health, request counts | None | API v1 status and request/count |

All collectors are preview support, not certified upstream-version compatibility.
The current installation capability generates a Compose plan. Discovery is manual
address entry and application backups are not implemented. Seerr is a preview
adapter verified against its published contract with synthetic fixtures. New capabilities must include
sanitized success/failure fixtures and declare the exact write actions allowed.

Disabled apps are omitted from status. Link-only apps remain useful launch links
without pretending that unavailable metrics are a connection failure. Tables and
summary counts must use declared capabilities, never assume every app supplies
every kind of data.

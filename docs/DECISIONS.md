# Product decisions

These decisions were confirmed by the product owner after the awesome-arr research review.

## Installation and existing applications

Stackarr should inspect the selected host for an existing supported application. If the application is already present, Stackarr enters connect/configure mode and offers a safe, reviewable settings integration. If it is absent, Stackarr offers installation and then applies the minimum settings needed for a coherent Stackarr workflow.

Detection must be evidence-based: Compose labels, an owned Stackarr install marker, a successful authenticated API probe, or an explicit user-selected executable/service. A port responding is not enough to identify an application. Stackarr must never overwrite an existing install, silently import secrets, or replace a user’s existing settings. Every proposed setting change is shown as a diff and can be skipped.

The initial automatic configuration scope is deliberately narrow:

- connect Sonarr and Radarr to the selected qBittorrent instance;
- connect Sonarr and Radarr to Prowlarr where the target API advertises the required schema;
- configure Seerr with the selected media server and Arr instances;
- configure safe shared paths only when the user explicitly approves the mount map.

Plex sign-in, indexer selection, download-client credentials, library selection, and any setting with destructive or privacy consequences remain explicit human steps.

## Seerr

Seerr is an optional companion integration. Stackarr should detect an existing Seerr installation, offer to install it when selected and absent, and configure it through supported APIs or documented setup flows. Seerr remains the owner of discovery, requests, user-facing request permissions, and request history. Stackarr links to Seerr and reports its health; it does not duplicate Seerr’s catalog or user-management model.

## Difficult NAS networks

Stackarr will eventually provide a small, narrowly scoped host agent for NAS and segmented-network deployments. The agent is not a general remote shell and does not expose Docker. It will provide:

- authenticated preflight checks for paths, free space, architecture, and local ports;
- an allowlisted Compose operation for a Stackarr-owned project;
- application health probes from the network location where the apps actually run;
- redacted logs and status results.

The agent must use mutual authentication or a one-time enrollment token, rotate credentials, bind to a user-selected interface, require explicit pairing, and record every privileged operation. It must be a separate optional component, disabled by default.

## Notifications and backups

Notifications should be provider-neutral. The first provider model is a user-selected set of destinations with clear event filters: generic HTTPS webhook, email, ntfy, and other compatible providers such as Notifiarr where the user chooses them. Delivery is server-side, retried with bounds, audited, and tested from Settings. No provider is mandatory.

Backups should support local storage, NAS/SMB/NFS paths available to the host, and S3-compatible object storage. Credentials are stored separately from the backup manifest. The UI must show retention, encryption, connectivity, restore test, and whether application-native data is included. A backup is not considered successful until the target acknowledges the completed object or file and Stackarr records its checksum.

## Docker access

Stackarr remains socket-free by default. A future Docker integration may use a narrowly scoped socket proxy that exposes only inspect, health, logs, and lifecycle operations for a Stackarr-owned project. It must not expose arbitrary exec, host filesystem mounts, image deletion, container deletion outside the project, or raw socket access. This is an advanced deployment option and is not required for the first public release.

## Windows first native installer

After the container-first release, Windows is the first native installer target. It should use a signed installer, a per-user or least-privilege service, explicit firewall scope, an uninstall path that preserves media and application data, and a clear relationship to Docker Desktop. Windows support must be tested independently from the Docker Desktop path.

## Adapter schema and interoperability

Stackarr owns its versioned adapter schema. Users may import or export Buildarr and Recyclarr formats through translators and review the resulting Stackarr configuration before applying it. Stackarr must not execute arbitrary YAML, silently adopt another tool’s destructive semantics, or require those projects at runtime.

## Recovery policy

The first public release should support observation, retry, resume, and rollback of Stackarr-owned operations. It should not automatically delete downloads, blocklist releases, restart unrelated applications, or launch replacement searches. Advanced recovery actions can be added later only with previews, stable identifiers from the source application, explicit per-action enablement, cooldowns, audit events, and a reversible or compensating path.

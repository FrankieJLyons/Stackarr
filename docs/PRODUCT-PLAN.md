# Stackarr product plan

Delivery priority: [COMPLETION-PLAN.md](COMPLETION-PLAN.md) sets the proposed remaining work and acceptance gates from the 16 October 2026 source baseline. [ONE-DOWNLOAD-PLAN.md](ONE-DOWNLOAD-PLAN.md) defines the Windows installer, guided fresh setup, LAN playback and startup-before-sign-in experience. These focused plans take priority over the broad milestone order below.

## Product promise

Stackarr should let someone with little technical experience start a private, reliable media stack on a new computer without first becoming a Docker, reverse-proxy, NAS, or Arr expert. It should explain every important choice in plain language, install only what the person selected, keep the services private by default, and make the stack understandable after it is installed.

The product is not a replacement for Plex, Seerr, Sonarr, Radarr, Prowlarr, qBittorrent, Tautulli, Uptime Kuma, or Cleanuparr. It is the safe installation, connection, visibility, and day-two management layer around them. Each specialist product continues to own the domain it is best at.

## Where the project stands

The current private alpha has a good foundation: validated settings, encrypted local credentials, session security, a responsive read-only dashboard, partial-failure handling, a reviewed Compose plan, loopback defaults, a fresh-host bootstrap, and a quarantined legacy snapshot. It is **not** yet a consumer-ready installer.

The current implementation includes a Windows launcher, nine-app Docker installation and monitoring, generated protected app logins, reviewed connections, encrypted app backups/restore, nightly retention and separate-disk copies, core-app updates/rollback, webhook notifications and hosted release builds. The largest remaining gaps are recipient folder/port usability, whole-host recovery, Stackarr/optional-app update acceptance, Docker prerequisite installation, LAN HTTPS, startup certification, host/NAS adapters and clean-machine acceptance. See [PROGRESS.md](PROGRESS.md) for verified scope; this document remains the broader product plan.

## Non-negotiable design principles

1. **Private and safe by default.** Loopback or LAN only, no router changes, no public links, no Docker socket, no deletion, and no background actions that a user did not enable.
2. **Start small.** A person can run only Plex, only Seerr, only an Arr pair, or any supported combination. Missing applications disappear from the interface instead of producing failure alarms.
3. **Every write is understandable.** Show the target, exact setting change, reason, affected service, and rollback option. “Apply” is never the first button in a dangerous workflow.
4. **Stackarr owns only its own files.** It may manage a Stackarr-labeled Compose project and its own state. Existing applications are connected and configured through a reviewed adapter; their files are never replaced.
5. **One source of truth.** The versioned Stackarr adapter schema holds portable intent. Generated Compose, proxy, backup, and host-specific files are artifacts that can be regenerated and compared.
6. **Graceful partial operation.** Failed or slow APIs are explicit, old data is marked stale, and a bad integration cannot make the dashboard blank.
7. **Simple language before technical language.** The UI says “Where are your media files?” before “bind mount,” and provides an advanced detail drawer for people who need it.
8. **Accessibility and small screens are release requirements.** Keyboard use, contrast, screen readers, zoom, touch targets, and a phone-size layout are tested with the same seriousness as APIs.

## The ideal first-day journey

1. Download one signed package for the operating system or NAS platform.
2. Run it and see a short readiness check. It detects the platform, architecture, container runtime, disk space, and a chosen data location. It explains how to fix each failed item without a terminal when possible.
3. Choose a simple starting template: **Plex only**, **Plex + requests**, **Complete private stack**, or **Custom**. Every template is fully editable and describes its trade-offs.
4. Select storage with a visual test: media folder, downloads folder, available space, and a test file. Stackarr explains that all download/import services need the same view of those folders.
5. Choose optional applications. Existing applications are detected only with trustworthy evidence and shown as “connect,” “leave alone,” or “install separately.”
6. Review a plain-English plan: applications, ports, storage access, data locations, network exposure, images, and any configuration writes. The plan can be exported.
7. Install with visible step-by-step progress and durable logs. An interrupted install resumes or rolls back Stackarr-owned changes.
8. Complete only necessary upstream steps in contextual panels: Plex claim, qBittorrent password, Arr root folders/profile choices, Prowlarr indexers, and Seerr users. Stackarr opens the right page and validates completion without collecting more data than needed.
9. Land on a calm Home page that says what is ready, what needs attention, and the single next action. The user can use the stack immediately without learning every advanced setting.

## Workstream 1: real distribution and fresh-machine installation

### Build

- Produce signed, versioned release artifacts: source ZIP, Linux package/container, Windows installer, macOS package where supported, and platform-specific NAS guides or packages.
- Make the installer bootstrap Stackarr only; Docker installation remains a deliberate prerequisite unless a platform vendor offers a supported API and the user explicitly approves it.
- Add a graphical prerequisite checker for Windows and a terminal-free launch path. It must identify Docker Desktop not installed, WSL disabled, Linux containers unavailable, virtualization disabled, blocked ports, no writable storage, insufficient space, unsupported CPU, and unsupported filesystem behavior.
- Ship immutable image digests in released templates, a software bill of materials, checksums, signatures, release notes, and an upgrade compatibility statement.
- Provide an owned installation directory, a service/launch mechanism for Stackarr itself, an uninstall flow that preserves data unless the user separately chooses “remove my Stackarr data,” and a repair flow.
- Implement safe in-product update checks: manual by default, release notes before update, verified download/signature, backup, migration preview, health verification, and one-click rollback to the previous Stackarr release.

### Do not do

- Silently install Docker, browser extensions, certificates, router rules, kernel drivers, or unrelated software.
- Treat a ZIP or a development checkout as a production runtime.
- publish generic `latest`-only plans as the only supported deployment story.

### Exit criteria

A new supported Windows or Linux host can get from download to the Stackarr welcome page with no terminal knowledge, and a clear recovery path exists for every failure before any application is installed.

## Workstream 2: host and deployment architecture

### Build

- Define a host-provider interface: local Docker/Compose, Docker Desktop, Synology, QNAP, Unraid, TrueNAS, and later a narrowly scoped host agent for difficult NAS networks.
- Add capability detection instead of platform assumptions: architecture, Compose version, rootless mode, supported bind mounts, UID/GID model, available storage, hardware acceleration availability, and reverse-proxy availability.
- Generate a Stackarr-owned Compose project from the portable schema, using a per-install project ID, dedicated network, named volumes, explicit image digests, health checks, resource guidance, and no raw Docker socket.
- Add a generated deployment lock file recording image digests, adapter versions, settings revision, deployment location, and ownership marker. Use it to show drift and make rollback exact.
- Separate application containers from Stackarr control-plane updates. An update to the dashboard must never restart a media server without explicit consent.
- Create a future scoped Docker proxy only after the core is mature. Its API must be allowlisted to inspect, health, logs, and lifecycle actions for the owned project; no exec, arbitrary mounts, image deletion, or unrelated containers.

### Exit criteria

The same intent produces understandable, reviewable deployment artifacts across two real platforms, and a failed operation leaves no ambiguous ownership or orphaned sensitive state.

## Workstream 3: setup wizard and configuration model

### Build

- Turn the existing settings object into a versioned declarative schema with migrations, field descriptions, platform capability constraints, secret references, defaults, and validation errors that name the next corrective action.
- Add templates: minimal server, requests-only companion, full private stack, and custom. Templates must never force every application.
- Build a wizard with checkpoints: welcome, host readiness, storage, application selection, network/access, review, install, guided application completion, and verification.
- Save progress locally, permit a user to leave and resume, and distinguish “not configured yet” from “broken.”
- Show a persistent review screen with a human summary and advanced JSON/Compose diff. Include “why does Stackarr need this permission?” beside every privileged step.
- Offer a configuration export/import that excludes secrets and a review screen for Buildarr/Recyclarr translation. Imports are drafts until explicitly accepted.
- Add a settings information architecture: **General**, **Storage**, **Apps**, **Network & access**, **Notifications**, **Backups**, **Updates**, **Advanced**, and **Audit log**. Keep expert fields collapsed.

### Exit criteria

A first-time user can select one or several applications, understand the storage and network choices, stop halfway safely, and resume without re-entering secrets or losing the plan.

## Workstream 4: adapter system and application setup

Each integration needs a published capability contract: detection evidence, authentication method, read data, writable settings, install image/package, health tests, first-run tasks, links, backup inclusion, and supported versions. Adapters must declare whether an operation is read-only, reversible write, or irreversible write.

### First-release adapters

| Application | Stackarr should own | Stackarr should guide or integrate | Leave to the application |
| --- | --- | --- | --- |
| Plex | Install/connect, health, session visibility, storage mapping checks | Server claim and library path validation | Account, library policy, transcoding preferences, content decisions |
| Sonarr/Radarr | Install/connect, health, queues, import backlog, connection diff | qBittorrent/Prowlarr connection, root folder/profile setup wizard | Release selection, library curation, destructive queue actions |
| Prowlarr | Install/connect, indexer health, Arr connection diff | Add-only connection setup | Indexer choice, tracker credentials, indexer-specific policy |
| qBittorrent | Install/connect, authenticated health, active downloads, category checks | Selected Arr category mapping and HTTPS compatibility test | Manual torrents, seeding policy, arbitrary deletion |
| Seerr | Install/connect, health, request-link card | Connect media server and Arr targets through supported setup | Discovery catalog, user permissions, requests/history |
| Tautulli | Install/connect, stream/activity summaries | Plex connection validation | Its analytics configuration and notification policy |
| Uptime Kuma | Install/connect, monitor state | Suggest monitors, allow reviewed monitor creation | Full monitoring topology and public status pages |
| Cleanuparr | Install/connect, clearly limited status | Link to its own reviewed policy | Any cleanup automation or deletion rule |

### Build

- Implement evidence-based discovery. An open port is only a clue; accepted evidence is a Stackarr ownership marker, a successful authenticated API response, a trusted Compose label, or a user-selected executable/service.
- Build adapter test fixtures from recorded, sanitized API shapes. Test old and current supported upstream versions, authentication failure, timeout, malformed response, missing optional application, and API capability drift.
- Build a universal “connection review” component that shows existing values, proposed values, conflict reason, API validation result, and exact rollback. Do not return secret-bearing plans to the browser.
- Add a guided first-run checklist per app, with deep links, completion detection, concise explanations, and an “I’ll do this later” state.
- Add Seerr to the app catalog, schema, install plan, collector, onboarding, capability matrix, and tests before calling the first release complete.
- Maintain Buildarr/Recyclarr translators as isolated import/export adapters. Never execute arbitrary YAML or make a foreign tool a runtime dependency.

### Exit criteria

Every advertised app can be installed or connected from the UI, reports a precise state, has an honest support level, and never causes a settings overwrite without a review screen.

## Workstream 5: best-in-class day-to-day UX

### Navigation

- **Home:** a calm readiness summary, current playback, active downloads, the next one or two actions, and optional applications only.
- **Activity:** active downloads, Arr imports, queue issues, recent request handoffs, and pagination/filtering that retains freshness labels.
- **Requests:** Seerr entry point and request-health summary when Seerr exists; hidden otherwise.
- **Apps:** app cards with state, version, link, setup checklist, connection test, safe restart only for Stackarr-owned containers, and adapter-supported settings.
- **Health:** grouped problems by urgency and cause—gateway, application unavailable, authentication, stale data, storage protection, import backlog, indexer health, backup, and update. Each issue has one primary resolution action.
- **Storage & backups:** capacity, mount mapping, backup status, restore-test date, and guard policy. Never infer a media path from an arbitrary drive letter.
- **Settings:** the organized areas described above, plus audit history.

### Interaction rules

- Use progressive disclosure. Normal users see outcomes and safe choices; advanced users can inspect paths, Compose, API capability details, and logs.
- Prefer verbs that describe effects: “Test connection,” “Review changes,” “Create backup,” “Resume Stackarr install.” Avoid vague controls such as “Execute” or “Sync.”
- Actions with risk require an impact statement, a typed or held confirmation only when the impact is significant, a task ID, progress, result, and audit event.
- Never hide an error in a toast alone. Preserve a useful issue card until it is resolved or dismissed with a reason.
- Support keyboard navigation, visible focus, 200% zoom, reduced motion, high contrast, touch targets, plain-language empty states, and no color-only status indicators.
- Provide a compact phone view designed for checking health and pausing Stackarr-owned work, not for cramming every advanced table into a screen.

### Exit criteria

Usability testing with people who have never used Docker shows that they can identify what needs attention, find the next action, and understand why an optional application is absent.

## Workstream 6: reliability, monitoring, backups, and recovery

### Build

- Run collection and long-running work in a durable job system with bounded retries, concurrency limits, cancellation, resumable state, and a clear result record. Do not perform host work in a browser request.
- Add a data-freshness model to every card and table: collected time, stale threshold, last successful value, and reason for failure. Cache headers and atomic writes are tested.
- Add checks for application availability, gateway availability, authentication failure, API capability mismatch, stale dashboard data, import backlog, download-client connectivity, indexer health, storage capacity, storage-guard state, backup status, and notification failures.
- Implement a storage guard only through an explicitly enabled host adapter. It must pause only selected managed categories, write a guard-specific marker, resume only marked items after the separate resume threshold, preserve partial/manual torrents, and never delete media.
- Build backup destinations for local storage, mounted SMB/NFS shares, and S3-compatible storage. Use encrypted secret storage, checksums, bounded retention, upload confirmation, restore test, and a report of exactly what each backup includes.
- Start recovery with diagnostics, retry, resume, and rollback of Stackarr-owned work. Any restart, queue removal, blocklist, search, or deletion action is later work with per-action controls, cooldowns, audit trail, and a tested compensating action where possible.
- Create provider-neutral notifications: in-app, HTTPS webhook, email, ntfy, and compatible services. Notifications are event-filtered, rate-limited, retry-bounded, and testable from Settings.

### Exit criteria

A network failure, slow app, full disk, bad credential, interrupted update, or failed backup produces an accurate explanation and does not silently discard last-known information or make destructive changes.

## Workstream 7: security, privacy, and trust

### Build

- Use operating-system secret stores where available, with a documented encrypted-file fallback and recovery-key handling. Never render or export secrets after entry.
- Provide local admin creation, recovery-code flow, session management, optional passkey/TOTP later, CSRF protection, rate limits, secure cookies, host/origin validation, CSP, and audit events.
- Make LAN exposure a wizard with a threat explanation, reverse-proxy configuration, local-CA trust instructions, certificate renewal status, per-platform trust guides, and firewall scope validation. Public exposure stays out of scope for the first release.
- Generate SBOMs, verify dependencies, scan containers, pin digests, run secret scanning, publish a vulnerability disclosure process, and have a security update policy.
- Clearly separate product licensing from upstream images, logos, trademarks, API terms, and GPL code. Reuse ideas and documented APIs, not unreviewed code or assets.
- Add privacy controls: no telemetry by default, optional anonymous diagnostics only with a preview, local-only audit logs, redacted support bundle, and a data-retention screen.

### Exit criteria

An external reviewer can explain what privileges Stackarr has, what it stores, what it sends off-device, and how a user can revoke access or recover from a lost password.

## Workstream 8: quality, documentation, and community readiness

### Build

- Maintain a compatibility matrix by OS, architecture, container runtime, NAS platform, upstream app version, browser, and feature. “Tested” must mean a real automated or documented manual run.
- Add unit, contract, integration, browser, accessibility, visual-regression, installer, upgrade/rollback, and fault-injection tests. Use disposable Docker environments, not a personal media server.
- Add real end-to-end test lanes for Linux x86-64, Windows Docker Desktop, ARM64, and at least one NAS-like environment. Hardware transcoding needs dedicated physical/virtual test coverage and may remain experimental.
- Write task-focused documentation: install, storage planning, each app’s guided setup, moving data, backup/restore, certificate trust, troubleshooting, uninstall, upgrades, and privacy/security. Each screen links to the relevant guide.
- Publish contribution guidelines, adapter-development documentation, a code of conduct, issue templates, support boundaries, changelog, roadmap, release policy, compatibility/deprecation policy, and a responsible disclosure channel.
- Establish a small maintainer process: dependency updates, upstream API monitoring, triage labels, reproducible bug reports, release candidates, and monthly compatibility review.

### Exit criteria

A contributor can add a tested adapter without guessing the security model, and a user can solve common installation problems from the documentation without reading source code.

## Delivery sequence

### Milestone 0 — turn the prototype into a trustworthy foundation

- Remove legacy source from future public history or create a new clean public repository after legal/security review.
- Complete the canonical schema, migrations, secret abstraction, job framework, adapter capability model, audit vocabulary, and error taxonomy.
- Add release packaging, SBOM/signing pipeline, pinned images, CI, source-release verification, and supported-version policy.
- Validate the fresh bootstrap on clean Windows and Linux virtual machines.

### Milestone 1 — first public release: install, connect, understand

- Fresh Stackarr installer for Windows and Linux Docker hosts.
- Full guided wizard, templates, storage test, reviewed plan, owned Compose deployment, resume/rollback, and uninstall preservation.
- Production-quality adapters for Plex, Sonarr, Radarr, Prowlarr, qBittorrent, Seerr, Tautulli, and Uptime Kuma; explicitly limited Cleanuparr support.
- Home, Activity, Apps, Health, Settings, mobile/accessibility support, logs/audit, precise freshness, and no blank dashboard failures.
- Basic local backup, restore test, in-app notifications, documentation, and a real compatibility matrix.

### Milestone 2 — safer day-two operations

- NAS host providers and optional paired host agent.
- SMB/NFS/S3 backup targets, encrypted backup manifests, notifications, manual update workflow, image pin updates, controlled lifecycle actions for owned containers.
- Storage Guard, import-backlog guidance, richer Prowlarr/Seerr/Tautulli/Kuma views, Buildarr/Recyclarr translation review, and optional reverse-proxy assistant.

### Milestone 3 — advanced, opt-in operations

- Scoped Docker proxy, advanced NAS support, hardware-transcoding advisor, policy-as-code export/import, multi-host inventory, and advanced recovery actions.
- Passkeys/TOTP, multilingual UI, theme customization, plugin/adapter marketplace only if maintenance and security governance are mature.

## Work to avoid or postpone

- A general remote shell, arbitrary Docker socket access, unrestricted Compose editor, or arbitrary script execution.
- Automatic public internet exposure, port forwarding, dynamic DNS, or weak proxy authentication.
- A universal “fix everything” button, automatic torrent deletion, automatic blocklisting, automatic replacement searches, or cleanup rules Stackarr cannot explain and reverse.
- A separate media-request/discovery system competing with Seerr.
- Full reimplementation of each upstream app’s settings interface. Use guided high-value flows, deep links, and explicit handoff instead.
- Promising every NAS, GPU, ARM board, or upstream app version before it has a tested support lane.

## Risks people commonly miss

- **Storage semantics:** a path that looks correct on the host can be wrong inside containers, producing imports that fail or duplicate files. The wizard must test and explain the whole path chain.
- **Updates and API drift:** upstream containers can change APIs, images, defaults, and migrations. Pin, test, and support a bounded version range.
- **Password recovery:** a local-only product needs a secure recovery mechanism that does not create a cloud back door.
- **Support burden:** “easy to install” shifts complexity to the project. Diagnostics, redacted bundles, compatibility data, and clear support limits are product features.
- **Data ownership:** the installer must know precisely which files, volumes, network, tasks, and settings it owns so uninstall and rollback never remove media or foreign application state.
- **Long-running jobs:** upgrades, image pulls, backup uploads, and health checks must survive a browser closing and a Stackarr restart.
- **Network reality:** DNS, local CAs, browser trust stores, IPv6, guest Wi-Fi isolation, NAS ACLs, and VPNs cause more real failures than the application code.
- **Licensing and trademark boundaries:** upstream images and names remain their owners’ property; adapter code must rely on compatible licenses and public APIs.
- **Accessibility and language:** non-technical users need clear text, not simply a prettier terminal in a browser.

## Decisions still needed from the owner

1. Should the first public release be Windows + Linux only, or should a specific NAS platform be a release blocker?
2. Do you want the first package to require Docker Desktop/Engine, or should a native Windows Stackarr service be a first-release goal?
3. Which four application templates should appear first, and should Plex be optional in every one?
4. What is the support promise: community best-effort, paid support later, or a tightly bounded self-service product?
5. Should remote access remain explicitly out of scope, or should VPN-only guidance be part of the first release?
6. Which backup destination should be implemented first after local backups: SMB/NAS share or S3-compatible storage?
7. Should anonymous, opt-in diagnostics be allowed to improve compatibility, or must every diagnostic remain entirely local?

## Measures of success

- A new-user test participant reaches a working one-app stack in under 30 minutes without a terminal after Docker is installed.
- At least 90% of installation failures have a specific, actionable remediation in the UI.
- Optional/missing apps never create false alarms.
- Every external write has a review, audit event, result, and documented rollback or stated irreversibility.
- A release is reproducible, signed, scanned, documented, and tested on every platform marked supported.
- Support requests can be diagnosed from a redacted bundle without asking for credentials, media names, or a full host export.

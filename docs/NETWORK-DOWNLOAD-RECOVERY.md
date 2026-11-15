# Docker network capacity and download recovery

Choose **Check Docker** during setup. After a failed or interrupted installation,
choose **Check Docker again** beside its saved progress.

The check reads Docker's local address pools and existing subnet allocations.
It reports an estimated number of ranges available for new private networks;
each new app batch needs one. Low capacity is shown clearly. When the known pools
are exhausted, new installation review stops before downloads or app creation.
An interrupted batch with its verified existing network can still resume.

Host routes, reservations and concurrent Docker operations can reduce the estimate.
Unknown or malformed inventory is reported as unverified. A real network-creation
failure is also recognized and explains the same recovery path. The check never
creates a probe network, removes networks or changes Docker settings.

For exhaustion, have your Docker administrator review networks that are no longer
needed or plan a suitable address-pool configuration. Empty-looking networks can
still belong to stopped apps. Stackarr does not prune them. Address-pool changes
require a separately planned Docker restart. Then check again and resume the saved
installation. See Docker's [subnet allocation guidance](https://docs.docker.com/engine/network/#subnet-allocation)
and [daemon configuration reference](https://docs.docker.com/reference/cli/dockerd/).

## Retry an interrupted image download

1. Restore Docker and internet/registry access. If Docker image storage is full,
   restore space without deleting app configuration volumes or media.
2. Reopen Stackarr. The saved installation identifies a failed/interrupted download.
3. Choose **Resume setup**, then **Retry download**. The same installation, pinned images, ports and folders
   are reused. Completed images remain cached; Docker decides whether incomplete
   layer bytes can be reused.

Only known transient image-download errors and download timeouts retry automatically,
with three bounded attempts. Missing images, registry access failures and storage
exhaustion need attention instead of repeated retries. Docker's raw stderr stays
private; the UI receives fixed recovery messages.

The controller records the download stage durably. A restarted controller marks
an unfinished operation interrupted and waits for explicit resume. It does not
automatically replay app setup. New progress metadata is created only when an
approved operation begins, so starting an update candidate does not change an
older idle installation's protected database.

After pulling, Stackarr verifies every image's requested repository digest, complete
image identifier and Linux x64 platform before creating media folders or starting
apps. Startup disables additional pulls. Image verification failure retains the
saved operation for retry. A network failure during Docker startup can leave a
new empty settings volume; resume retains that volume and the same owned project.
Docker documents [pull-only behavior and the missing-image policy](https://docs.docker.com/reference/cli/docker/compose/pull/).

## Isolated acceptance boundary

`tools/docker_network_download_check.py` uses a separate Docker daemon inside a
disposable container, with its own two-range address pool, storage and original
OCI image fixtures. It has no host Docker socket or existing media/configuration
mounts. Only the nested daemon's pool is exhausted. Its unrelated sentinel retains
the same container and original configuration bytes throughout.

Six cases cover actual exhaustion/read-only diagnostics; capacity taken after
review; a real network failure in the final Docker-start window and offline cache
resume; an actual blob connection cut after 262,144 bytes; registry access failure
followed by explicit retry; and a killed worker/download CLI during a partial body,
followed by fresh-process recovery of the same installation and single activation.

`tools/docker_network_download_package_check.py` also promotes a fresh older
Runtime-Repair r2 preview through the packaged browser, preserving its account,
current session, preferences and controller fingerprint. A separate original-image
registry then causes a real failed download in the actual frozen controller. The
browser checks Docker without changing networks and retries the saved download.
The original fixture uses a maintainer-only pinned recipe in the Seerr catalog slot;
it is not an upstream Seerr account/setup test. Production packages keep the normal
image allowlist and have no fault flags or arbitrary-registry browser input.

The packaged fixture receives a separate explicit test subnet so it does not use
the host's last default range. The main installation is fingerprinted throughout,
and its nine integrations are freshly authenticated at final acceptance. The lab
retains configuration volumes, state, keys, encrypted checkpoints and copied media;
only its temporary containers/networks are removed.

This covers same-computer Docker image downloads and address-capacity diagnostics.
It does not configure Docker pools automatically, resume a download at a promised
byte offset, change credentials, certify every registry or close clean-Windows,
LAN, signed-out startup, native-dialog and major-migration release gates.

## Completed result — 18 October 2026

All **eight live cases pass** with the final
**Stackarr-Docker-Network-Download-Preview-20261018-r2** package. All nine real
cached catalog images also pass the new digest/platform verification read-only.
Full regression: **550 passed, 3 existing Windows filesystem-link skips**;
**19 frozen smoke checks outside the checkout**; Ruff passed; portable-source
audit **252 files, 0 findings**. The audit permits only the exact quoted public
Docker default subnet in its defining source file, with the exception regression-tested.

Final acceptance freshly authenticates all **nine main integrations** and verifies
unchanged app/dashboard IDs, settings, credentials, nightly policy and **16 tracked
media/data files**. The separate three-file sample copy also matches. The main
dashboard/controller remain on Self-Removal r4. All lab containers and networks
are removed; configuration volumes, state, keys, encrypted checkpoints and media
are retained. No host pool, Docker settings, firewall or Windows service is changed.

Nine package entries/eight payload hashes verify.
Image: `sha256:9c759d0a9a0b7175cc1fd0efeced39a8963173aba643f38b9551fcc79a4df30f`.
ZIP SHA-256: `d9f62b9f4d16fc41ac7f4a9d2f6e3f89c8aa908425deaf3a7da6830d02eaf52e`.

Private evidence under `test-results/docker-network-download-20261018-r2/`:
`acceptance.json`, `cases.json`, `package-verification.json`, `frozen-smoke.json`,
`catalog-image-verification.json`, `main-authenticated-monitoring.json`,
`source-audit.json` and the three `packaged-*.png` browser screenshots.
Full regression: `test-results/network-download-regression-r2.xml`.

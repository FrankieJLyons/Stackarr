# Recover a port conflict during final app startup

When another service takes a port after the last installation check, Docker can
leave some apps running and another container created but unable to start.
Stackarr preserves that partial installation and shows its saved progress.

1. Choose **Review available ports** beside the failed installation.
2. Check the proposed old → new addresses. Running apps keep their addresses.
3. Choose **Apply new ports & resume**, then **Finish connecting** once ready.

If the original port has become free, choose **Resume installation** to keep the
original addresses. Stackarr recreates only unstarted containers using their
existing settings volumes. This also handles Docker's failed-bind edge case where
starting the old container can report running without restoring its network/port.
The published address is checked before credential handoff.

Existing services using conflicting ports keep running. Stackarr never stops
them, deletes app volumes, resets logins, changes image versions or moves media.
qBittorrent's host port, matching container web port and `WEBUI_PORT` change
together when selected. Its settings volume and saved credentials remain.

## Preservation and interrupted recovery

Recovery keeps the same installation ID, Compose project, private network,
configuration volumes, pinned images and media folders. A healthy running app's
container is not restarted. Unstarted apps receive a new generation label and
are recreated with their existing volumes. Configuration and generated-login
checkpoints are reused by the normal connection setup.

The owner-protected review expires after five minutes and can be approved once.
The browser sends no ports or Docker commands. Before approval the controller
rechecks identities, settings-volume consumers, image/environment/security
options, media mounts and proposed port availability. Changed, missing or shared
retained resources block recovery for inspection.

Approval atomically records the exact source/target recipes and verified resource
identities in the existing deployment receipt before changing the Compose file.
The worker accepts only that recorded source or target file, then replaces it
atomically. A fresh controller marks unfinished work interrupted and waits for
explicit resume. A replacement container must match the complete target recipe
and recorded generation. Unknown or partly renamed containers block recovery.
Another real port conflict can be reviewed again after the saved recipe was
applied; settings remain on the same volumes. An app stopped externally after
approval is preserved for inspection rather than restarted. A port taken before
missing containers are recreated also keeps this recovery receipt; it cannot
fall back to a fresh installation that abandons retained configuration volumes.

Trusted controller status refreshes only a previously reviewed, unactivated
dashboard connection handoff. This repairs an approval response lost before the
dashboard learned its new addresses. Existing activated connections and unrelated
app settings are preserved. **Finish connecting** verifies the new ports privately.

## Isolated acceptance

The maintainer checks use real pinned Prowlarr and qBittorrent images, fresh named
settings volumes and copies of three original sample files. Prowlarr starts first
and receives an identifiable setting and generated login; qBittorrent's new
settings volume receives an original marker. A separate disposable responder
takes its port immediately before the actual Compose startup. Docker supplies
the real binding error; no startup error is simulated.

The six native cases cover a new address while the old port owner stays running;
original-address resume after that owner stops; a proposed address taken before
approval; actual worker exit after receipt/file commit and fresh-process resume;
a second real final-start conflict; and refusal while a read-only foreign
container shares the new settings volume. Each successful recovery checks the
healthy app's unchanged ID/setting/login, exclusive volume fingerprints, marker,
new authenticated qBittorrent access, one installation and one activation.

The packaged runs use the extracted ZIP, frozen Windows controller and real
browser buttons through **Finish connecting**. A separately built maintainer CLI
relay introduces the same real port-owner container only for the new lab's exact
Compose path/project. Only that controller inherits its PATH; the relay is never
included in the package. The case verifies desktop/phone layouts, retained
Prowlarr settings/ID, app-volume identities, generated downloader login and
recovery from a deliberately stale unactivated connection handoff. Repeated
packaged runs verify the later safeguards and the final release artifact.

Evidence remains private under
`test-results/docker-startup-ports-20261018-r1/`. Maintainer entry points are
`tools.docker_startup_ports_check` (`initialize`, `available`, `freed`, `stolen`,
`interrupted`, `repeated`, `shared`) and
`tools.docker_startup_ports_package_check` (`packaged`, `recover`, `cleanup`, `finalize`).
The `recover` phase supports resuming a browser acceptance session after the
initial genuine failure. Private state, keys and credentials must not be shared.

Finalization freshly authenticates all nine existing main integrations and
compares the original running IDs, settings/credential fingerprints, nightly
backup policy and 16 tracked media/data files. It removes only the new lab
containers/networks, without `--volumes`, retaining all lab state, settings,
keys and sample media. The existing main package is not upgraded.

This covers the final app-install binding window on the existing Docker host.
Clean/replacement Windows, native dialogs, signed-out startup, LAN/second-device
access, shared/revoked accounts and major migrations remain separate release gates.

Final acceptance passes six native scenarios and three packaged runs, including
`Stackarr-Docker-Startup-Ports-Preview-20261018-r4.zip`. Its nine entries/eight
payload hashes and 20 frozen smoke checks verify. Regression passes 572 tests
with 3 existing skips; Ruff and the 258-file portable-source audit pass. All nine
main integrations authenticate freshly and the 16 original media/data hashes,
settings, credentials, backup policy and running IDs match the baseline.

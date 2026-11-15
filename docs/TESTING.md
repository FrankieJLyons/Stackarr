# What the automated checks cover

Permission/revocation coverage uses `tools.docker_seerr_permissions_check` and
`tools.docker_seerr_permissions_package_check`. The native phase runs official
Seerr 3.5.0 against synthetic TLS Plex identities on an internal Docker network.
An internal HTTP relay preserves real cookies/headers; it does not mock Seerr
authentication or permission enforcement. It tests shared/imported admission,
request/profile privacy, permission changes on live sessions, revoked external
membership/token behavior and Seerr account deletion. Synthetic pending records
never invoke downloaders. The packaged local-user form repeats restrictions,
role changes, container replacement and deletion with browser sign-in fallback.
Thirty relevant maintenance contracts pass, including four new guest/identity/
revived-user checkpoint cases. Main apps/settings/media are fingerprinted, all
nine connections freshly authenticated and only lab containers/networks removed.

That upstream audit found Manage Users could change another administrator through
alternate routes. The subsequent [security backport](SEERR-PERMISSIONS-FIX.md)
passes 40 real HTTP checks in both its final native image and extracted package,
plus browser login/container replacement and the normal 3.5.0 security update.
It protects higher-privilege profiles, limits delegation and rejects mixed batches
before writes. The suite passes 589 Python tests (3 skipped), 9 Node policy tests
and 22 frozen checks. The real second-account Plex cloud test remains deferred by
the owner's choice to use test identities. The original findings remain separately
recorded in [SEERR-PERMISSIONS.md](SEERR-PERMISSIONS.md).

Seerr setup acceptance uses `tools.docker_seerr_guidance_check` (`native`,
`storage_persistence`) and `tools.docker_seerr_guidance_package_check`
(`verify_package`, `seerr`, `resume_seerr`, `combined`, `finalize`). Six real pinned
Seerr cases reproduce the image warning, verify owned durable storage, retain
unexpected marker files/links, refuse denied/shared storage and check persistence
across container replacement. Packaged Seerr-only and Plex-plus-Seerr journeys
check scoped guidance, clipboard success/denial fixtures, phone layout and warning
absence. The real upstream button opens official Plex authorization; an early
browser fixture also blocks popup creation. Neither completes account authorization.
Finish connecting must keep these incomplete accounts pending. The combined Plex
server stays distinct and unclaimed with read-only copied sample media.

Normal execution needs no saved Plex authorization. The optional `persistence`
phase is excluded and requires explicit human approval before its test-reuse flag
may be enabled. Finalization checks unchanged main state/media and freshly
authenticates its nine integrations, then removes only lab containers/networks,
retaining all configuration volumes and recovery data. See [SEERR-SETUP.md](SEERR-SETUP.md).

The 19 October human follow-up uses fresh sign-in to the retained r3 Seerr-only
lab, never the optional saved-authorization route. The owner completed the usual-
browser fallback and confirmed the same session after container replacement.
Read-only database checks prove a Plex owner with owner permissions; only digests
of its new authorization/identity fields leave that container. Seerr 3.5's separate
POST library-sync and PUT library-enable endpoints select the already claimed
maintenance Plex server's existing original-sample library. No Plex library is
created or changed. Private packaged handoff, repeat handoff, authenticated APIs,
fresh dashboard monitoring and removal of completed account guidance pass.
New account/settings fingerprints and the config volume survive replacement.
The lab is stopped with all data retained; the older test Plex returns to its
previous stopped state. Morning main-state/media baselines and fresh nine-app
authentication are separate from the preceding night's completed automated run.

Network/download acceptance uses `tools/docker_network_download_check.py` and
`tools/docker_network_download_package_check.py`. Six actual nested-engine cases
exercise a private two-range pool, read-only estimation, real subnet exhaustion,
after-review/final-start capacity races, offline cached-image resume, original OCI
blob disconnection, registry access failure and actual worker/CLI exit during a
partial transfer. The packaged browser also checks older-release promotion and
real registry-failure/retry through the frozen controller. All faults target new
lab storage and original fixtures; main account/settings/media are fingerprinted.
The fixture in the Seerr catalog slot is not upstream Seerr account certification.
See [NETWORK-DOWNLOAD-RECOVERY.md](NETWORK-DOWNLOAD-RECOVERY.md).

Runtime repair/storage acceptance uses `tools/docker_runtime_repair_check.py` in
a new two-app Docker lab. `prepare` saves main/account/app/media fingerprints;
the first `browser` review must succeed without a separate runtime status check.
`offline` and `missing` use one-use frozen local approval with stopped components
or an absent dashboard/damaged Compose file. `denied` and `full` force real
read-only-volume and 64 KiB filesystem failures; a read-only holder proves partial
candidate bytes were written before ENOSPC.

`lock` blocks a real Windows controller-file replacement after candidate database
writes, requiring pending recovery until the lock is released. `interrupted`
exits the worker after those real writes and resumes through a fresh packaged
process. `staging` verifies atomic release-admission retry after an actual host
write denial; `unavailable` simulates only the isolated Docker adapter boundary.
`late-port` binds an exclusive listener after preflight, then requires fresh
recovery after the port is freed. `finalize` verifies all nine main integrations,
settings, keys and media, removes only this task's temporary containers/networks,
and retains all configuration volumes, encrypted snapshots and keys.
Unit contracts also cover changed/shared/missing resources, occupied saved ports,
first-use authority, single-use action-bound approval, preflight storage failure,
partial release-copy retry and atomic journal preservation. See
[RUNTIME-REPAIR.md](RUNTIME-REPAIR.md).

Seerr Plex-owner acceptance uses `tools/docker_seerr_plex_maintenance_check.py`
and `tools/docker_seerr_plex_browser_check.py` in a separate fixed Docker lab.
Normal Plex authorization creates the real owner; each verification starts with
an empty Seerr cookie jar and checks fresh Plex sign-in, owner permissions,
selected libraries, Arr connections and a synthetic pending request. Local login
and admission of new Plex users are disabled. No real download is requested.

The six native cases cover repair, confirmed-write failed-repair recovery,
3.4.1 → 3.5.0 update/rollback, rejection of an API-healthy candidate with disabled
Plex sign-in and changed request status, actual worker exit/fresh-process recovery,
and encrypted restore. Independent snapshot inspection proves the candidate writes.
Five packaged browser app actions include an update under the earlier package,
rollback of its checkpoint after Stackarr promotion, then new-package repair,
update and rollback. Docker events verify promotion does not restart Seerr.
Contract tests detect authentication/identity changes, retain older checkpoint
shapes and exclude only the advancing library scan cursor.

Finalization checks all nine main integrations with fresh authentication from
the actual dashboard, main container/settings/credential fingerprints and media
hashes, then stops the new lab and its previously stopped dependencies. Volumes,
keys, encrypted snapshots and original samples remain. See
[SEERR-PLEX-MAINTENANCE.md](SEERR-PLEX-MAINTENANCE.md) for the passed matrix,
account boundary and remaining shared-user/major/whole-host/browser gates.

Optional-app maintenance acceptance uses a fresh, fixed lab rather than the main
installation. `tools/docker_optional_maintenance_check.py` exercises repair,
confirmed failed-candidate writes, distinct-image update/rollback, actual worker
exit and fresh-process recovery, and encrypted configuration restore. The separate
`tools/docker_optional_browser_check.py --package <extracted-folder>` repeats owner
review/apply controls through the packaged frozen controller. It refuses to start
over an active or unresolved maintenance operation. See
[OPTIONAL-APP-MAINTENANCE.md](OPTIONAL-APP-MAINTENANCE.md) for exact versions,
fixtures, credentials/account boundaries and the private evidence directory.

Whole-host recovery acceptance:

```powershell
.\.venv\Scripts\python.exe -m tools.docker_host_recovery_check --package <extracted-preview-folder>
```

The claimed-account extension is the fixed maintainer-only
`tools/docker_claimed_host_recovery_check.py`, with sequential phases `prepare`,
`configure`, `backup`, `loss`, `recover`, `verify` and `finish`. It restores only
stopped disposable Plex/Seerr/Tautulli and Arr configuration snapshots into five
fresh source volumes. Original containers stay stopped and their volumes/media
are retained. A packaged browser creates the complete recovery file; only the
new source volumes/dashboard are removed and source state is renamed.

The real partial-write fault leaves all five new recovery containers stopped.
The claimed Plex machine identifier proves extraction occurred, then a fresh
packaged process retries the saved review. Wrong-key, occupied-port and existing
stopped-resource gates reject before adoption. Recovered checks use normal Plex
authorization, an empty Seerr cookie jar, Tautulli's saved web login/API key,
protected owner/library/request/Arr settings and three database integrity checks.
Old Stackarr sessions must fail, a new controller enrollment must exist and all
five dashboard integrations must authenticate. Finalization authenticates all
nine main apps, compares media/settings/credential/container fingerprints and
stops the recovered lab with volumes/keys/encrypted recovery files retained.
See [HOST-RECOVERY.md](HOST-RECOVERY.md) for exact evidence and remaining gates.

The original `tools.docker_host_recovery_check` creates a new nine-app lab under
`test-results`, copies original sample media,
backs up through the packaged browser, then deletes only that lab's generated
volumes to simulate loss. It makes original host state unavailable, injects a
partial-extraction failure and resumes in the extracted executable. It verifies
credentials/logins/settings, app-volume fixtures, media hashes and preservation
of the existing main stack. Keep its `source.json`, recovery review/results and
report for scoped inspection; `--root` and `--phase` allow bounded continuation.
See [HOST-RECOVERY.md](HOST-RECOVERY.md) for the acceptance boundary and exclusions.

GitHub CI runs unit/contract tests, source auditing, dependency auditing, package
builds and a Chromium workflow. The Windows preview cannot upload an artifact
unless the shared browser workflow succeeds first.

Browser checks use temporary data, loopback access and synthetic app responses.
They cover local pairing, account setup, saved wizard progress, plan download,
partial integration failures, request counts, operation history, filtering,
settings, themes and signing back in. Screenshots cover desktop, tablet and phone;
checks reject horizontal page overflow and unlabeled form controls. Uploaded
screenshots contain synthetic data only; browser sessions and credentials are not
included in artifacts.

This is not a full accessibility audit, a real-app compatibility certification or
a clean-machine installation test. Keyboard/screen-reader testing, contrast audits,
broader upstream-version contracts, Windows reboot-without-login, rollback and NAS validation
remain separate release gates. Unsupported environments must not be marked tested
based on these synthetic checks.

## Packaged Stackarr update acceptance

`tools.docker_self_update_check` is restricted to the designated disposable
four-app Docker lab. Its separate `update`, `rollback`, `failed` and `interrupted`
phases use real packaged Windows controllers and dashboard images. The update,
rollback and failed-candidate checks exercise the authenticated browser review
and approval controls; host staging substitutes for the native file chooser.
Rollback deliberately changes a lab-only Stackarr preference first, then checks
the earlier preference and current session after restore.

`tools.self_update_fixture` builds an explicitly broken, checking-mode-only image.
It changes the copied dashboard database while reporting healthy. Protected-data
verification must reject it and recover the original database/release. The
interruption phase waits for those actual copied-database writes, pauses only
that candidate, kills only its recorded native maintenance worker, then reopens
an older recovery-capable package in a fresh process. All phases compare the four
lab app container IDs and protected settings, six lab media/data hashes, original
main settings/credential hashes, 16 main media/data hashes and unrelated running
container IDs. No app update, restore or media operation is approved by this test.

Keep the private test state, keys and credentials under ignored `test-results`.
Only sanitized reports and screenshots with hidden credentials may be shared.
The broken fixture ZIP is test input and must never be distributed as a release.
Native ZIP-dialog interaction and novice walkthroughs remain human checks.

The Windows packaging job also runs the actual executable with a self-test report
option. It checks bundled Tcl, SQLite/encryption, temporary loopback startup,
unauthenticated access rejection, packaged web assets and shutdown. No media apps
are installed and no live data is used. This catches missing frozen dependencies;
it does not replace a fresh-machine GUI/reboot/install acceptance test.

## Stackarr removal and reinstall acceptance

`tools.docker_self_removal_check --phase run --package <new-package-folder>
--baseline <previous-package-folder> --archive <new-package-zip>` is restricted
to the retained original-sample four-app lab. It records fresh main and lab
fingerprints, upgrades only the lab dashboard/controller, approves removal through
the actual browser and reinstalls using the frozen executable's two-step native
review/approval entry points. Reused approvals, occupied dashboard/controller ports
and an older launcher's attempt to start removed Stackarr must be rejected.

The failure fixture changes the copied candidate database and lets normal protected
data checks reject it. The interruption fixture exits only the maintainer test
supervisor after a confirmed candidate write, then reopens the package in a fresh
process and requires recovery to the original removed state before reviewed retry.
A separate interruption follows confirmed deletion of the exact lab dashboard;
startup must record completed removal without repeating deletion. Faults exist
only in this test process, with no production bypass/environment flag.

Every phase checks the four lab app IDs/settings/logins, six original lab files,
all nine main app IDs, complete logical controller/dashboard fingerprints and 16
main media/data files. Backup/configuration-file hashes are checked across reinstall.
Cleanup removes only isolated containers/networks and retains settings volumes,
original samples, staged releases and encrypted checkpoints. `--phase main` updates
only Stackarr after isolated acceptance, reviews removal without approving it and
verifies all nine apps, fresh monitoring and the unchanged nightly backup plan.
The native dialog and novice recipient walkthrough remain separate human gates.

## Owned-app maintenance acceptance

`tools.docker_app_maintenance_check` is restricted to the retained disposable
four-app lab and original local samples. `prepare` records a fresh main-controller
and dashboard data fingerprint, running container IDs and media hashes. `upgrade`
uses the actual packaged Stackarr update flow. `browser` exercises authenticated
review/approval for repair, retained-data removal, backup while absent, an occupied
saved port and bringing the app back; a stopped app must remain stopped after
repair. Three peer containers, protected settings, generated logins and media are
compared with the baseline.

`fault` stops only the test controller and uses the same maintenance module with a
maintainer-process readiness failure after an actual candidate configuration write.
It requires automatic configuration recovery. `crash` exits that test worker after
the write, leaving its durable operation running. The deterministic fault writes
only a marked file under the receipt-verified candidate configuration volume;
restoration must remove it and recover the original settings/login. `recover` reopens the extracted
packaged controller in a fresh process, checks that startup did not replay the job,
then approves recovery through the browser. No production fault flag is included.
`finalize` stops/removes only the isolated containers/networks without deleting
volumes, sample files or snapshots. Private state/credentials stay under ignored
`test-results`; share only sanitized reports and screenshots with credentials hidden.

`accept --package <extracted-preview-folder>` runs the browser, failed-write and
interruption/recovery phases in order, requiring a confirmed candidate write and
unfinished durable job before reopening the package, then performs scoped cleanup.
`main --archive <preview-zip>` requires the isolated acceptance report and updates
only Stackarr. It reviews all nine main apps without approving an app operation,
checks fresh monitoring and compares the original app IDs, media and data fingerprints.

Contract tests cover shared/missing volumes, missing media roots, changed identity,
environment and mounts, Docker network defaults versus custom options, settings
rollback, interrupted recovery, removal interruptions before/after deletion,
stopped-state preservation and absent-app backup. The final stopped-app Docker
event check also verifies no start occurs before repair completes; only the later
explicit Start action starts its replacement.
These cases do not certify every upstream version or optional-app account recovery.

## Real installer acceptance

`python -m tools.install_wizard_check --full --plex` runs the browser wizard against a
fresh six-app Docker installation. Run it only on a test host with local Linux
Docker containers, existing development dependencies and Playwright Chromium.
It uses separate loopback ports, a unique Compose project, fresh configuration
volumes and an empty synthetic media folder. It leaves your existing deployments
alone and stops only a successfully completed test project, preserving volumes.
Failed projects remain available for diagnosis.

The check verifies reviewed installation, durable progress, Arr API credential
handoff, the generated qBittorrent password, owner-password-gated login display,
Sonarr/Radarr library roots, four tested app connections, duplicate preservation, unclaimed Plex API readiness,
read-only Plex media mounts and recovery from a dropped progress response.
It does not sign in to Plex or Seerr, add sources, download media, claim playback,
install Docker, change firewall rules or exercise a Windows reboot.

The hosted `install-wizard` lane repeats this on a fresh Linux runner. Only redacted
reports and screenshots taken with credentials hidden are uploaded; SQLite state,
encryption keys and generated credentials are excluded.

Monitoring fault tests also verify that oversized streams stop at the response
limit and stalled streams hit a total deadline, closing their connections.

The maintainer-only `tools.docker_folder_ports_check --package <extracted-folder>`
uses disposable Windows Docker installations. It deliberately occupies dashboard,
controller and app ports, verifies automatic alternatives, rejects approval when
a port is taken after review, and stops a download-time conflict before app
containers, volumes or media subfolders are created. A fresh reviewed retry installs
Sonarr/Radarr/qBittorrent, connects them privately and tests app wiring. It reuses
an approved folder containing spaces/non-Latin characters and reopens the package
with saved addresses and app IDs intact. A separate standalone Kuma installation
needs no media folder. Original media hashes, main settings/credential hashes and
running container IDs are compared. Test configurations are retained.

Folder cancellation is a browser-response fixture; persistent grants, cancellation,
single-flight selection and rejection of browser-supplied paths are separately
contract-tested. Native Windows folder-dialog interaction still needs a human
walkthrough. The frozen executable also tests occupied wildcard-port rejection
without contacting the listener. Windows bind checks use exclusive wildcard binds
to avoid shadowing an existing listener; see [Microsoft's socket guidance](https://learn.microsoft.com/en-us/windows/win32/winsock/using-so-reuseaddr-and-so-exclusiveaddruse).

## Final app-start binding recovery

See [STARTUP-PORT-RECOVERY.md](STARTUP-PORT-RECOVERY.md). Run the maintainer-only
`tools.docker_startup_ports_check` phases sequentially: `initialize`, `available`,
`freed`, `stolen`, `interrupted`, `repeated`, `shared`. They use fresh pinned
Prowlarr/qBittorrent installations and copied original media, not existing app
volumes. A disposable responder actually owns the downloader port immediately
before Compose startup. Each case retains Prowlarr's container ID, setting and
generated login, qBittorrent's original config marker and volume fingerprints,
and media bytes. Interruption uses an actual child-process exit after the durable
receipt/file transition. Repeated conflicts use another real Docker bind failure.

`tools.docker_startup_ports_package_check packaged` verifies the exact extracted
ZIP, all payload hashes and 20 frozen smoke checks from outside the checkout,
then exercises browser review/approval and private connection completion through
the real frozen controller. Its separate maintainer CLI relay must be built as
`docker.exe` into the scoped lab directory first; only that lab's controller
inherits the relay PATH. The relay injects a real port owner for one exact new
recipe, never synthetic Docker stderr, and is absent from the release ZIP.
`recover` resumes that browser acceptance after a test-session interruption.

Use `cleanup` to stop/remove only the packaged lab's containers/networks and
free its address ranges before more native cases on a capacity-limited host.
`finalize` requires six native cases and three packaged runs (nine results),
freshly authenticates the nine existing main apps, compares original
settings/credential/media fingerprints and IDs,
and verifies every original and newly retained named volume still exists.
It keeps all state, keys, settings volumes and sample media. Private evidence
stays under ignored `test-results/docker-startup-ports-20261018-r1/`.

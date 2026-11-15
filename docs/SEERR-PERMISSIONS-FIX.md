# Seerr Manage Users security backport

The private Docker package is
**`Stackarr-Docker-Seerr-Permissions-Preview-20261019-r4.zip`**.
It includes **Seerr 3.5.0-stackarr.1**, a separately identified Stackarr-patched
build of the pinned official Seerr 3.5.0 image. This fixes the alternate-route
administrator permission flaw reproduced in the [earlier audit](SEERR-PERMISSIONS.md).
It is not an official upstream release. Existing installations are not changed
by building or testing this package.

## Enforced account policy

The single-user PUT, batch PUT and user-settings permission POST now use the
same transaction and authorization policy. The actor is reloaded inside that
transaction so a removed permission cannot be supplied from an old session.

| Action | Result |
| --- | --- |
| Delegated manager changes an administrator or owner | Denied on all three routes |
| Manager edits a more privileged non-admin account | Denied, including profile/email changes |
| Manager grants capabilities they do not hold | Denied |
| Any user changes their own permissions, including owner demotion | Denied |
| Owner grants/revokes another user's administrator role | Allowed |
| Manager edits an ordinary account within their own capabilities | Allowed |
| Non-owner administrator grants administrator | Denied; the owner grants that role |
| Batch contains any protected, self or missing target | Entire batch rejected before writes |
| Valid batch repeats an ID | Deduplicated; permitted users updated together |
| User edits their own ordinary profile settings | Allowed |

The shared profile middleware also protects mutation routes for email, password,
notifications and push subscriptions. Otherwise, a protected account could be
taken over through its editable profile instead of changing its role directly.
Ordinary request-only defaults and the existing explicit deletion/session
revocation behavior remain in place. Deleting a real Seerr user also deletes
associated request history; the tests delete disposable users only.

The relevant upstream [user handler](https://github.com/seerr-team/seerr/blob/v3.5.0/server/routes/user/index.ts),
[settings handler](https://github.com/seerr-team/seerr/blob/v3.5.0/server/routes/user/usersettings.ts)
and [profile middleware](https://github.com/seerr-team/seerr/blob/v3.5.0/server/utils/profileMiddleware.ts)
are the base for this narrowly scoped backport.

## Build and distribution

`platform/seerr/Dockerfile` derives from the exact upstream digest.
`patch.cjs` verifies every affected compiled file against `upstream.lock.json`
before writing anything. A changed upstream input is rejected; there is no fuzzy
patching, downloaded startup script, authentication proxy or UI-only restriction.
`permissions.cjs` contains the shared policy and transactional operation.
The modified JavaScript, helper, version and security label are baked into the
image. Normal upstream startup, user, volume and network contracts are retained.

The resulting immutable reference is:

```text
stackarr-seerr@sha256:8237a8d28ad28057fbcc4f5c572f158274787b567768519cd2df5901dd5ad818
```

The ZIP includes this image in its hashed Docker archive alongside Stackarr.
The launcher loads it when absent and checks its exact image identity. Install,
update and host recovery verify the digest, Linux/amd64 platform, version and
security label. A missing or changed security image blocks app changes with a
reopen-the-complete-package instruction. It does not fall back to unpatched Seerr
or try to download this private image from an upstream registry.

Docker export must retain the reviewed repository tag as well as the immutable
identity; exporting by digest alone loses the repository association on load.
The packager binds that tag to the reviewed image before exporting it. The final
empty-cache recipient test verifies this behavior rather than relying on the
developer's image cache. No registry push is required.

The image contains its MIT Seerr license, patch source, exact base/file lock,
build recipe and applied-file hash receipt under `/usr/share/stackarr-seerr/`.
See [licensing notes](LICENSE-NOTES.md). No account, database, token, fixture
certificate or media is included in the images or ZIP.

## Validation and scope

The final security image passes **40 real HTTP checks** covering each mutation
route, capability escalation, owner/self protection, higher-privilege account
profiles, mixed/unknown/duplicate batches, permitted edits and live revocation.
The internal-network lab also repeats shared/imported Plex admission, privacy,
request-only access, live permission changes and explicit session revocation:
**nine recorded native cases** in total. External Plex identity/membership is the
owner-approved synthetic TLS fixture; Seerr authentication and authorization
handlers, cookies, database and transactions are real.

The extracted final ZIP passes all **eight payload hashes** and **22 frozen
controller checks** outside the source checkout. Its browser installer loads
the absent security image from the archive and creates a fresh Seerr volume
without media folders or local builds. The app reports the patched version and
does not show the false storage warning.

For account checks, only the disposable native fixture's synthetic settings and
consistent SQLite account snapshot are seeded into this fresh lab volume.
SQLite's backup API includes committed WAL data; log symlinks, real credentials
and other application state are excluded. This is test fixture preparation,
not a claim that a recipient's account setup was completed automatically.

The package repeats all **40 permission checks**. A manager signs in through
the real Seerr form and is denied on all three protected alternate routes.
Replacing only that container retains its cookie, protection, config volume,
owner-authorization digest and settings hash.

The normal packaged review, approval and background worker also update a
disposable previous-release fixture from **3.5.0 to 3.5.0-stackarr.1**. Its users,
pending requests, owner authorization and settings match the authenticated
pre-update checkpoint, and all 40 permission checks pass again afterward.

The Python suite passes **589 tests, 3 skipped**; **nine Node policy tests** pass.
The skipped cases remain Windows filesystem-link contracts. A changed-upstream
input test rejects the patch before any partial output is written.

Maintainer phases:

```text
python -m tools.docker_seerr_permissions_fix_check run
python -m tools.docker_seerr_permissions_fix_package_check verify
python -m tools.docker_seerr_permissions_fix_package_check install
python -m tools.docker_seerr_permissions_fix_package_check seed
python -m tools.docker_seerr_permissions_fix_package_check matrix
python -m tools.docker_seerr_permissions_fix_package_check update
python -m tools.docker_seerr_permissions_fix_package_check finalize
```

Private proof stays under `test-results/docker-seerr-permissions-fix-20261019-r1/`.
The final native proof is in `native-final/`; preliminary attempts remain separate.
Test volumes, state, encryption keys and synthetic credentials are retained.
Final cleanup removes only the lab containers and networks. Fresh authenticated
checks pass for all nine existing integrations, and original app/dashboard IDs,
settings, credentials, nightly backup policy and all 16 media/data files match
the initial baseline. The existing main installation is not upgraded.

ZIP SHA-256:

```text
d058d79aacf5f90dfd5add6f6e3f5868c7a76aa45910d5247798d238adc05719
```

Real Plex cloud sharing/revocation with a second account and broader recipient
walkthroughs remain separate gates. Plex sharing/token revocation still requires
explicit Seerr account revocation to block an existing Seerr session. Restoring
an older unpatched image or package restores its older authorization behavior;
the security build must be applied again afterward. Main app rollout requires a
separate reviewed update and was outside this isolated acceptance task.

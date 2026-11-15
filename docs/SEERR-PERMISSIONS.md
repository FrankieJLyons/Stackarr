# Seerr invited/shared-user permissions and revoked access

This records the **unpatched upstream 3.5.0 audit**. The subsequent
[security backport and packaged acceptance](SEERR-PERMISSIONS-FIX.md) closes the
observed delegated-role gate in Seerr 3.5.0-stackarr.1. Existing unpatched
installations retain the behavior described below until reviewed updating.

The 19 October 2026 Docker matrix exercises the real pinned **Seerr 3.5.0**
application. Ordinary-user restrictions, live permission changes and explicit
Seerr account revocation work. It also reproduces an upstream delegated-role
problem: **Manage Users can change a non-owner administrator's permissions**
through the single-user and batch update routes. The owner remains protected.
That delegated-administrator release gate is open.

The owner chose test identities. Plex identities, sharing membership and token
revocation are simulated; this is not certification of Plex cloud behavior with
a second real account. No invitation is sent and no real sharing is changed.

## Verified behavior

| Check | Observed result |
| --- | --- |
| Shared Plex test identity | Admitted with request-only defaults; an unshared identity is denied |
| New Plex sign-ins disabled | An unknown shared identity is denied; an explicitly imported identity can still sign in |
| Ordinary local/shared user | Cannot read admin settings, create users, grant admin, approve another user's request or change another user's notification settings |
| Request privacy | Without Request View/Manage Requests, users see their own pending requests; another user's direct request and filtered list are denied |
| Profile privacy | Ordinary user lists exclude email, Plex IDs, tokens, passwords and notification settings |
| Live permission change | Removing Manage Users or Request View affects the existing session on its next request |
| Permissions set to none | Capabilities disappear, but the account can still sign in |
| Plex sharing/token revoked in fixture | A fresh sign-in is denied; an existing Seerr session still works |
| Seerr test user deleted | Its open session and password login are denied; the browser returns to sign-in |
| User deleted while sharing/new sign-ins remain enabled | The Plex identity can be admitted again with the default permissions |
| Packaged container replacement | Cookie session, least-privilege role, original owner/authorization, settings and config volume survive |
| Manage Users against another administrator | Delete is denied, but single-user and batch permission updates succeed: unresolved upstream protection gap |

The sharing/login behavior is exercised through the real Seerr authentication
handler; only the external Plex service is a fixture. The relevant upstream
implementation is the [v3.5 authentication handler](https://github.com/seerr-team/seerr/blob/v3.5.0/server/routes/auth.ts)
and [session/permission middleware](https://github.com/seerr-team/seerr/blob/v3.5.0/server/middleware/auth.ts).
The delegated-role result differs from the protection described in
[Seerr's user-editing guide](https://docs.seerr.dev/using-seerr/users/editing-users/);
the affected routes are in its [versioned user handler](https://github.com/seerr-team/seerr/blob/v3.5.0/server/routes/user/index.ts).

## Access guidance for this pinned version

Use request-only defaults for ordinary household users. Grant Manage Users only
to trusted administrators while the observed alternate-route issue remains.
Stackarr does not grant that role or patch Seerr's authentication implementation.

For an import-only policy, disable **Enable New Plex Sign-In** and explicitly
import the intended users. This prevents automatic admission of new identities;
it does not revoke existing imported users or sessions. The
[official adding-users guide](https://docs.seerr.dev/using-seerr/users/adding-users/)
describes default permissions and automatic Plex admission.

Complete revocation needs both sides checked: revoke the user's Plex sharing
where appropriate, remove the Seerr account to invalidate its sessions/password
path, and verify both a new login and an already open browser. Removing Seerr
permissions alone is not a sign-in block. Deleting only the Seerr account permits
readmission if Plex sharing and automatic new sign-ins still allow it.

Review the data consequence before deleting a real account: Seerr also clears
that user's associated data and request history. See its
[deleting-users guide](https://docs.seerr.dev/using-seerr/users/deleting-users/).
Only disposable accounts were deleted in this matrix. No real user or request
was changed, and no media/download files were mounted in the native fixture.

## Test boundary and evidence

Ten native cases run with the official pinned image and normal Seerr routes.
The Plex identity fixture uses a private TLS certificate trusted only inside the
new Seerr container. Its Docker network is internal, and requests originate
inside that network through an HTTP relay preserving actual cookies/headers.
No authentication handler, database account record or permission response is
mocked. Synthetic pending request records are inserted only to test ownership;
no request is submitted to a downloader or approved. Fixture counters prove the
real handler consulted identity and membership endpoints.

The subsequent browser journey reopens only the retained **Seerr Setup r3**
package's isolated Seerr-only installation. A disposable local user signs in
through the real form, is denied admin actions, gains and loses a delegated
permission in the same session, survives replacement of its own container, then
loses both its live session and password access after deletion. The UI returns
to **Login with Seerr**. The original lab owner's freshly authorized Plex
identity/authorization digest and settings-file hash remain unchanged. No owner
token is copied to the synthetic lab. The existing separate Plex test server is
not started for these permission tests.

Thirty focused maintenance tests pass, including four new checkpoint contracts
detecting an elevated guest, removed guest, revived user and changed identity.
These protect update comparisons; they do not claim a new restore-time revocation
policy or real Plex cloud session invalidation.

The native ledger records completed checks and observed boundaries. Its delegated
case explicitly has `delegated_admin_protection_passed: false`; final acceptance
uses `execution_complete`, with `delegated_admin_release_gate_passed: false`.
An executed audit is not reported as a passed security control.

Finalization freshly authenticates all nine existing integrations from the actual
main dashboard and compares original app/dashboard IDs, settings, credentials,
backup policy and 16 media/data file hashes. Only this task's lab containers and
networks are removed. Named volumes, fixture state, private test keys, retained
account data and original samples remain. The main Stackarr installation is not
upgraded, and the Seerr Setup r3 ZIP is unchanged.

Private proof is under `test-results/docker-seerr-permissions-20261019-r1/`:
`native-report.json`, `findings.json`, `isolation.json`, `fixture-events.json`,
`checkpoint-tests.xml`, `acceptance.json`, `main-authenticated-monitoring.json`,
`source-audit.json` and `packaged/browser-report.json` with its revoked-access
screenshot. Credentials, TLS keys, cookies and application state stay private.

Maintainer entry points are `tools.docker_seerr_permissions_check`
(`prepare`, `native`, `boundaries`, `stop_native`) and
`tools.docker_seerr_permissions_package_check` (`prepare`, `browser`, `finalize`).
The `local`, `audit_admin_routes`, `verify_native` and `renew_invited` phases resume
only the fixed disposable test workflow; they are not recipient operations.

Remaining work: fix and retest the delegated-admin route protection before
certifying that role, then exercise a second real disposable Plex account and
broader recipient/browser workflows when available. The owner-approved synthetic
scope is complete.

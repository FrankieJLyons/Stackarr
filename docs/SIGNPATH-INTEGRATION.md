# SignPath integration and activation

Status: prepared, disabled and not connected to a SignPath account. No API token,
production certificate, app installation or signing policy has been provisioned.
Public 0.1.0 remains unsigned. This integration does not publish releases.

## What is wired

The Windows launcher preview workflow has a manual `sign` input, default false.
After its build/tests succeed, an explicitly selected run on `main` can call
`.github/workflows/signpath.yml` with `kind: launcher`. That reusable workflow
also supports `kind: package` for a complete package produced earlier in the same
run. It does not accept an external URL, a different run ID or local binary uploads.

The complete-package caller is `.github/workflows/complete-package.yml`. It builds
the dashboard on hosted Linux and the launcher on hosted Windows, assembles the
real portable ZIP and unsigned installer, then loads and smoke-tests the ZIP's
images on a fresh Linux runner. Only after that check succeeds can an explicit
main-branch `sign: true` dispatch call package signing. Pull-request builds cannot
request signing. See [hosted build details](HOSTED-PACKAGE.md), including the
unchanged Seerr dependency recovered from the checksummed 0.1.0 release.

Package mode performs three requests in order:

1. Sign the launcher and verify its publisher, timestamp and unchanged executable
   content. Update its manifest hash, signing notice and signed metadata before packaging.
2. Run Inno Setup's external-signing first pass. Submit the generated uninstaller
   under the fixed request name `StackarrUninstaller.exe`, verify the result, and
   restore it to the compiler's exact cache filename.
3. Compile with that signed uninstaller, then sign and verify the outer installer.
   Produce a signed-launcher ZIP, installer, SHA-256 files and signing receipt.

Only candidate artifacts are uploaded. The workflow has read-only repository
permissions. Changes to executable code, an invalid/missing timestamp, a different
publisher, revision mismatch, compiler failure or any missing signing step fail
the run. There is no fallback to an unsigned artifact labelled signed.

## Account setup after Foundation approval

1. Have the owner create/configure the SignPath account with MFA and confirm the
   approved certificate's public thumbprint. Configure project access and explicit
   manual signing approval. Give the CI token submission access, not approval rights.
2. Connect SignPath's GitHub trusted build system and its GitHub App to **only**
   `FrankieJLyons/Stackarr`. Constrain the SignPath policy to this repository,
   `main`, the reviewed caller workflow and GitHub-hosted runners. The launcher
   caller is `.github/workflows/windows-preview.yml`; the complete-package caller
   is `.github/workflows/complete-package.yml`. Review both before allowing them.
3. Create artifact configurations named `launcher`, `uninstaller` and `installer`
   from `platform/windows/signpath/*.xml`. They describe GitHub's ZIP artifacts,
   allow one named PE target and constrain product/version. Verify the templates
   against the account's live XML schema and approved samples. These files are
   preparation templates, not evidence of live service validation.
   Inno's installer/uninstaller resources use a 60-character product name and
   50-character version, padded with spaces. Those two XML files preserve the
   exact product-name padding; their workflow requests pass the exact padded
   version as a JSON string. The launcher uses unpadded metadata. Do not replace
   these checks with wildcard suffixes. Verify the service's handling of padding
   with the actual samples during onboarding.
   The fixed field widths are defined in Inno's
   [setup resource](https://github.com/jrsoftware/issrc/blob/is-6_7_1/Projects/Res/Setup.version.rc)
   and [loader resource](https://github.com/jrsoftware/issrc/blob/is-6_7_1/Projects/Res/SetupLdr.version.rc).
4. Create GitHub environment `signpath-production`, restricted to `main`. Configure
   owner review and disable administrator bypass where available. A sole owner
   may need to approve their own environment deployment; SignPath's separate
   manual approval remains mandatory. Do not place the token at repository scope.
5. Add the following configuration to that environment. Enter the token directly
   in GitHub's secret UI, never a chat, committed file or shell command history.

| Type | Name | Value |
| --- | --- | --- |
| Secret | `SIGNPATH_API_TOKEN` | Dedicated submission-only token from SignPath |
| Variable | `SIGNPATH_ORGANIZATION_ID` | Assigned SignPath organization UUID |
| Variable | `SIGNPATH_PROJECT_SLUG` | Approved Stackarr project slug |
| Variable | `SIGNPATH_SIGNING_POLICY_SLUG` | Policy requiring manual approval |
| Variable | `SIGNPATH_CERTIFICATE_SHA1` | Exact approved certificate's 40-character public thumbprint |
| Variable | `SIGNPATH_ENABLED` | Set to `true` only after the preceding controls are verified |

Certificate rotation requires reviewing and updating the public thumbprint. A test
certificate from SignPath that is not Windows-trusted will fail production
verification; do not weaken the verifier or add a private root to production jobs.

## Validation and release acceptance

Unit tests cover modified binaries, malformed PE data, wrong source revision,
signature verification invocation, exact requested files and checksum receipts.
The hosted Windows installer lane rehearses all three handoffs with a one-day
self-signed test identity trusted only on that disposable runner. It verifies the
installed launcher/uninstaller signatures and removes its test certificate. It
uses a synthetic image payload, never starts Docker and never calls SignPath.
Only test reports are retained; those binaries must not be distributed.

After approval, make a manual main-branch launcher run with `sign: true`, review
the request in SignPath, and verify the downloaded artifact on a clean Windows
machine. Then dispatch the complete-package caller and repeat the three-stage
flow with the real payload. Real SignPath API behavior, Foundation policy approval,
public certificate trust, clean Windows setup and sign-in/reboot acceptance remain
unverified until those runs occur.

The complete-package caller's signing job is gated on assembly and verification:

```yaml
sign:
  needs: [assemble, verify]
  uses: ./.github/workflows/signpath.yml
  with:
    artifact-name: unsigned-complete-signing-input
    kind: package
```

The artifact root must contain exactly the manifest payload layout understood by
`stackarr.self_update.package`, including clean source provenance matching the
workflow SHA and a launcher with this release's PE metadata. The caller must grant
`contents: read` and `actions: read`, use GitHub-hosted jobs, and be manually
dispatched on `main`. Do not use `pull_request_target`, accept caller-controlled
checkout refs, or add automatic signing approvals.

References: [SignPath GitHub](https://docs.signpath.io/trusted-build-systems/github),
[artifact metadata constraints](https://docs.signpath.io/artifact-configuration/reference),
[Inno external uninstaller signing](https://jrsoftware.org/inno-setup/documentation/topic_setup_signeduninstaller.htm).

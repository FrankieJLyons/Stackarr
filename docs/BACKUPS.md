# Configuration backups

Use Backups to create a copy of Stackarr settings, inspect saved copies and preview
restored settings. These backups exclude passwords, API keys, webhook addresses,
sessions, third-party application databases and media files. They do contain your
configured server addresses and folder paths; keep them private.

Each new backup has a SHA-256 sidecar. Preview checks the checksum and validates the
configuration schema before staging a draft in Settings. Review that draft and
select Save settings to apply it. Existing credentials remain unchanged and
notifications are disabled in the draft. No container is restarted or reconfigured
by previewing a backup. An older backup without a sidecar needs manual inspection
and can be imported through the normal configuration review flow.

Checksums detect accidental changes; someone able to replace both files can replace
the checksum too. Format verification is explicitly not a successful restore test.
Backups live in the Stackarr data folder, so they do not protect against losing
that disk. Off-host/NAS/S3 copies, encrypted credential recovery and full app backup
and restore are later work. Save and protect your app-native backups separately.

Daily backup attempts are recorded on disk. Restarting Stackarr does not reset the
schedule, and a failed scheduled attempt is not repeated on every status refresh.
After correcting a failure, use Back up now for an immediate retry. The schedule
runs when Stackarr is running; missed checks do not run while it is closed.

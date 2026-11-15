# Configuration upgrades and credentials

Stackarr stores portable settings separately from encrypted credentials. Schema 3
accepts schema 1 and 2 files and upgrades them during validation. Schema 2 separates
webhook secrets; schema 3 adds Seerr as a disabled optional app. Unknown future schemas
are rejected without replacing saved settings. Startup upgrades are transactional
and advance the settings revision, so a stale browser cannot overwrite them.

Notification addresses may contain private tokens. They are encrypted alongside
application credentials. Leaving the address empty when saving settings preserves
the saved address; disabling notifications stops delivery. Existing plaintext
notification settings are moved into encrypted storage on startup. SQLite secure
deletion clears the replaced cells in the current database; older disk snapshots
and existing backups are outside this migration's control.

Imports are validated and staged for review. They do not change active settings or
credentials until Save settings is selected. Imported notifications are disabled
and webhook addresses omitted. Re-enable them in Settings after reviewing the import.
Exports and configuration backups omit credentials and disable notifications.

The encryption key remains in the local data directory. Encryption does not protect
against someone who can read both that key and the database. Windows account ACL
hardening and an OS-backed key store remain release work.

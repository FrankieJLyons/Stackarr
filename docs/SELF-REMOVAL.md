# Remove and reinstall Stackarr

To fix a stopped, missing or unhealthy dashboard while keeping the installation,
use [runtime repair](RUNTIME-REPAIR.md). An intentionally removed installation
continues to require the reinstall review below.

Open **Settings → Stackarr updates & rollback → Review Stackarr removal**. Read
the review, then choose **Remove Stackarr, keep settings**. Stackarr verifies its
owned dashboard and private controller, pauses only those components, saves and
checks an encrypted safety checkpoint, then removes only the dashboard container.
Your media apps keep running. Their containers, settings, media and downloads are
not removed, recreated or restored.

Keep the complete Stackarr state folder, retained Docker volumes and staged
packages. They hold your owner account, encryption/enrollment keys, app credentials,
generated logins, installation receipts and backups. Removal also retains
Stackarr's image and private network. This preview offers no permanent-data deletion
option and does not uninstall Docker Desktop. Scheduled Stackarr backups pause
while its controller is removed; the media apps run independently.

To reinstall, open **Start Stackarr.cmd** from this removal-capable package using
the same state folder. The local **Reinstall Stackarr** window offers **Review
reinstall**. It checks Docker, the original ports, retained data and the saved
checkpoint before asking for approval. Cancel leaves Stackarr removed. Approval
reinstalls the same saved release using isolated copies of the retained settings;
account, credentials and settings checks gate promotion. Sign in with your existing
Stackarr password. Your app connections, generated logins and backups remain.

Reopening the package never silently reinstalls a completed removal. An older
package rejects the deliberate removed-state recipe rather than recreating it.
Use a removal-capable package to review reinstall. A busy saved port, changed
enrollment/image/network, shared or missing settings volume, changed retained data
or corrupt checkpoint blocks reinstall without overwriting the data or stopping
the conflicting service. Ports are retained, so existing app connections stay valid.

If removal fails before container deletion, recovery resumes the verified original
Stackarr container. If deletion completed before interruption, recovery records
the removed state; it never repeats deletion. Reopen **Start Stackarr.cmd** after
checking Docker/storage availability to recover pending maintenance.

If reinstall fails or is interrupted, recovery stops/removes only its verified
candidate container and returns to the removed state with the original settings.
Candidate settings volumes, staged packages and encrypted checkpoints are retained.
Reopen the package and review reinstall again. Recovery refuses foreign or changed
containers instead of guessing their process or replacing their data.

Removal/reinstall retains intact local state. It does not repair corrupt databases
or reconstruct deleted settings volumes, lost keys, media or a lost host disk.
Use [whole-host recovery](HOST-RECOVERY.md) and your separate media backup for that
case. Checkpoints and earlier releases have no automatic retention yet. Native
dialog/novice walkthroughs, signing and clean-Windows/LAN certification remain
separate release gates. See [PROGRESS.md](PROGRESS.md) for packaged acceptance.

# Operation history

Manual connection refreshes now receive a persistent operation ID. Closing a
browser does not cancel them. `/api/jobs` lists their waiting, running, finished,
failed or cancelled state and timestamps for signed-in users. A waiting operation
can be cancelled using the authenticated, CSRF-protected cancellation endpoint.
Concurrent refresh requests share a single waiting or running operation.

Interrupted connection checks resume after a service restart, with at most three
attempts. Ordinary failures require an explicit retry. Each transition has a
correlated audit entry; raw exception text and credentials are never recorded.
Individual unhealthy apps do not mean the check itself failed: consult Health.

This initial runner only accepts connection checks. It suppresses notification and
backup side effects during those checks. Installations, connection writes and
restores must not be added until they support durable reconciliation and reviewed
plans. They cannot safely be blindly replayed after an interrupted request.

The runner assumes one Stackarr process per data directory. The desktop launcher
enforces that. Multi-process server deployments are unsupported. Health includes a Recent operations panel. Step progress and safe cancellation
of running installs remain work
for issue #3; this is the durable foundation, not the complete installer runner.


## Check a wizard installation

In the local launcher, open Apps and select **Check installation**. The read-only
check compares each container with its saved installation receipt: ownership
labels, pinned image reference, configuration volume, media mount paths/access,
published ports, private network, privileged mode and no-new-privileges setting.
It reports running, starting, stopped, paused, restarting, unhealthy, changed or
unavailable. Existing applications connected separately are excluded.

A changed or missing Compose file stops the check. Results show the kind of drift,
not raw Docker output or credentials. The check does not restart containers,
recreate them, change settings or delete data. It also does not certify all
upstream settings, Plex claim, Seerr setup, imports or playback. Use Health for
application API results; review Docker/app logs before deciding on repairs.


## Start or stop an installed app

After Check installation, a matching running or stopped container offers a
**Review stop** or **Review start** button. Review the affected app and confirm in
the separate panel. Stopping interrupts that app's active work. Docker is given
30 seconds to stop it, then may terminate it forcibly; this is not a consistent
backup operation. See Docker's [stop behavior](https://docs.docker.com/reference/cli/docker/container/stop/).

Actions address the exact saved container ID and recheck its receipt, ownership,
image, mounts, ports and network before execution. Start reuses the same container;
it does not pull a new image or recreate anything. Volumes, media and other apps
are preserved. Application readiness follows separately in Health.

Action progress and results are saved and audited. After an interrupted or
unconfirmed action, check the app's actual state and review again. Queued/running
actions are not replayed after a Stackarr restart. Changed, missing, paused or
restarting containers and independently connected apps are excluded from these
controls. Upgrade, rollback, repair and removal remain separate future workflows.

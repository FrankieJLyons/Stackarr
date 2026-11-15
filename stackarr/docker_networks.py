"""Bounded, read-only estimate of Docker's IPv4 network address capacity."""

import ipaddress
import json

GUIDE = "https://docs.docker.com/engine/network/#subnet-allocation"
# Docker's documented built-in pools when info.DefaultAddressPools is null.
DEFAULTS = [("172.17.0.0/16", 16), ("172.18.0.0/16", 16), ("172.19.0.0/16", 16),
            ("172.20.0.0/14", 16), ("172.24.0.0/14", 16), ("172.28.0.0/14", 16),
            ("192.168.0.0/16", 20)]
EXHAUSTED = ("Docker has no unallocated IPv4 network ranges in its address pools. "
             "Your existing apps can keep running. Review unused networks with your Docker administrator, "
             "or expand Docker's address pools following its network guide. Then check Docker again and "
             "resume this installation. Stackarr does not remove networks or change Docker settings.")


def estimate(pools, occupied):
    """Count unavailable subnet slots without expanding potentially huge pools."""
    free = 0
    for base, prefix in pools:
        if base.version != 4:
            continue
        if not base.prefixlen <= prefix <= 32:
            raise ValueError("Invalid pool size")
        stride = 2 ** (32 - prefix)
        start, end = int(base.network_address), int(base.broadcast_address)
        intervals = []
        for subnet in occupied:
            if subnet.version == 4 and subnet.overlaps(base):
                intervals.append(((max(start, int(subnet.network_address)) - start) // stride,
                                  (min(end, int(subnet.broadcast_address)) - start) // stride))
        used, last = 0, -1
        for lower, upper in sorted(intervals):
            used += max(0, upper - max(lower, last + 1) + 1)
            last = max(last, upper)
        free += 2 ** (prefix - base.prefixlen) - used
    return free


def inspect(command, existing=None):
    """command is already bound to a verified local context. Never allocate a probe."""
    result = {"state": "unknown", "estimated_free": None, "guide": GUIDE,
              "detail": "Docker network capacity could not be estimated. Network creation is checked during installation.",
              "notice": "This read-only estimate excludes host routes and concurrent changes; it does not reserve a network."}
    try:
        def read(args):
            value = command(args)
            if len(value) > 262144:
                raise ValueError("Oversized Docker response")
            return value

        raw = json.loads(read(["info", "--format", "{{json .DefaultAddressPools}}"]))
        configured = raw is not None and raw != []
        if configured:
            if not isinstance(raw, list) or len(raw) > 64:
                raise ValueError("Invalid address pools")
            pools = [(ipaddress.ip_network(row["Base"]), row["Size"]) for row in raw]
        else:
            pools = [(ipaddress.ip_network(base), size) for base, size in DEFAULTS]
        ipv4 = [(base, size) for base, size in pools if base.version == 4]
        if not ipv4 or any(not isinstance(size, int) or isinstance(size, bool) for _, size in ipv4):
            raise ValueError("No verified IPv4 pools")
        if any(a.overlaps(b) for i, (a, _) in enumerate(ipv4) for b, _ in ipv4[i + 1:]):
            raise ValueError("Overlapping pools")
        identities = read(["network", "ls", "--filter", "scope=local", "--quiet", "--no-trunc"]).split()
        if not identities or len(identities) > 256 or any(len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in identities):
            raise ValueError("Unverified network inventory")
        data = read(["network", "inspect", "--format",
                     '{"name":{{json .Name}},"labels":{{json .Labels}},"subnets":{{json .IPAM.Config}}}', *identities])
        networks = [json.loads(line) for line in data.splitlines()]
        if len(networks) != len(identities):
            raise ValueError("Incomplete network inventory")
        occupied = [ipaddress.ip_network(row["Subnet"]) for network in networks
                    for row in network["subnets"] or [] if row.get("Subnet")]
        free = estimate(ipv4, occupied)
        result.update(state="exhausted" if not free else "low" if free <= 2 else "available",
                      estimated_free=free, networks=len(networks), pool_source="configured" if configured else "built-in",
                      detail=EXHAUSTED if not free else f"Docker has about {free} unallocated IPv4 network ranges. "
                      + ("Capacity is low; another app batch needs one range." if free <= 2 else "A new app batch needs one range."))
        if existing:
            result["existing_network"] = any(network["name"] == existing and
                (network["labels"] or {}).get("com.docker.compose.project") == existing.removesuffix("_control") and
                (network["labels"] or {}).get("com.docker.compose.network") == "control" for network in networks)
    except Exception:
        # Unavailable/old engines and malformed output cannot disclose raw paths,
        # labels, addresses or engine errors through the browser.
        return {**result, "state": "unknown", "estimated_free": None}
    return result

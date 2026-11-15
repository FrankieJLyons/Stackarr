"""Suggest local bind ports without contacting or changing existing services."""

import socket

from .config import CATALOG


class PortsUnavailable(ValueError):
    pass


def available(port):
    try:
        with socket.socket() as probe:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            # Wildcard first: Windows may allow a specific-address bind beside a
            # nonexclusive wildcard listener. Never temporarily shadow that service.
            probe.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False


def check(draft, reserved=()):
    """Check selected host ports without connecting to any running service."""
    rows, used = [], set()
    for key in draft.install_apps():
        port = draft.choice(key).port or CATALOG[key]["port"]
        status = "available"
        if port in reserved:
            status = "reserved"
        elif port in used:
            status = "duplicate"
        elif not available(port):
            status = "unavailable"
        used.add(port)
        rows.append({"app": key, "name": CATALOG[key]["name"], "port": port, "status": status})
    return rows


def ensure(draft, reserved=()):
    if any(row["status"] != "available" for row in check(draft, reserved)):
        raise PortsUnavailable("Some app ports are now in use. Choose Use available ports and review installation again. Existing services were left running.")


def suggestions(draft, reserved=()):
    result, reserved = [], set(reserved)
    for key in draft.install_apps():
        original = draft.choice(key).port or CATALOG[key]["port"]
        candidates = [original]
        start = original + 10000 if original + 10000 <= 65535 else 49152
        candidates.extend(range(start, min(start + 64, 65536)))
        candidates.extend(range(49152, 49408))
        for port in candidates:
            if port in reserved:
                continue
            if not available(port):
                continue
            reserved.add(port)
            result.append({"app": key, "name": CATALOG[key]["name"], "previous": original, "port": port})
            break
        else:
            raise ValueError(f"No available local port was found for {CATALOG[key]['name']}. Choose a port manually.")
    return result

"""Public, fixed Docker error classifications; raw stderr stays private."""

from .docker_networks import EXHAUSTED


def classify(stderr, downloading=False):
    text = (stderr or "").lower()
    if not downloading and any(value in text for value in ("port is already allocated", "ports are not available",
            "bind: address already in use", "only one usage of each socket address")):
        return "startup-port-conflict", "An app port became busy while Docker started the installation. Review available ports for this saved installation, or free its original port and resume. Existing services, app settings and media are retained.", False
    if any(value in text for value in ("all predefined address pools have been fully subnetted",
            "could not find an available, non-overlapping ipv4 address pool", "no available ipv4 address pool")):
        return "network-capacity", EXHAUSTED, False
    if downloading and any(value in text for value in ("no space left on device", "disk quota exceeded")):
        return "download-storage", "Docker's image storage is full. Free storage without deleting app data, then resume this installation. Completed image downloads remain cached.", False
    if downloading and any(value in text for value in ("unauthorized", "authentication required", "pull access denied", "manifest unknown", "manifest not found", "not found")):
        return "download-unavailable", "The reviewed app image is unavailable or its registry requires access. Check registry access or use an updated Stackarr package, then resume. Existing apps and settings are retained.", False
    transient = downloading and any(value in text for value in (
        "toomanyrequests", "429 too many requests", "tls handshake timeout", "i/o timeout", "unexpected eof",
        "connection reset", "connection refused", "context canceled", "context cancelled", "request canceled",
        "no such host", "temporary failure in name resolution", "network is unreachable", "connection timed out"))
    return ("download-interrupted" if transient else "docker-step",
            "The app image download was interrupted. Check Docker and your internet connection, then resume. Completed image downloads remain cached."
            if transient else "Docker could not complete this step. Check Docker Desktop and resume the saved installation.", transient)

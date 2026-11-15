"""Explicit LAN origins and browser routes; never change API or peer addresses."""

import json
import re
from contextvars import ContextVar
from urllib.parse import urlsplit

from .config import APP_IDS, validate_url

# Request-local state: collectors and background jobs retain their local routes.
browser_routes = ContextVar("stackarr_browser_routes", default=None)


def https_origin(value):
    value = validate_url(value, origin_only=True)
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", parsed.hostname)
            or parsed.hostname in {"localhost", "host.docker.internal"}
            or parsed.hostname.endswith(".localhost") or value != value.rstrip("/")):
        raise ValueError("Choose an exact HTTPS LAN origin without a path or credentials.")
    return value


class LanAccess:
    def __init__(self, local, environment):
        self.local = local
        self.origin = environment.get("STACKARR_LAN_ORIGIN", "")
        self.links = json.loads(environment.get("STACKARR_LAN_LINKS", "{}"))
        if not isinstance(self.links, dict) or set(self.links) - set(APP_IDS):
            raise ValueError("LAN links must name supported apps.")
        if self.origin:
            self.origin = https_origin(self.origin)
            if urlsplit(self.origin).netloc.lower() == urlsplit(local).netloc.lower():
                raise ValueError("The LAN and local browser authorities must differ.")
        elif self.links:
            raise ValueError("Configure the LAN origin before adding LAN app links.")
        hosts = {urlsplit(self.origin).hostname}
        for value in self.links.values():
            address = https_origin(value)
            hostname = urlsplit(address).hostname
            # Cookies are scoped to hosts, not ports. Each app gets its own host.
            if hostname in hosts:
                raise ValueError("Use a different hostname for each app to isolate login cookies.")
            hosts.add(hostname)

    def request_origin(self, headers):
        hosts = headers.getlist("host")
        if len(hosts) != 1:
            return None
        return next((value for value in (self.local, self.origin) if value
                     and urlsplit(value).netloc.lower() == hosts[0].lower()), None)

    def status(self, current):
        return {"origin": current, "local_origin": self.local, "lan_origin": self.origin,
                "mode": "home-network" if current == self.origin else "this-computer",
                "authentication": "required", "restart_required": True,
                "app_links": self.links, "startup": "signed-out-boot-not-certified"}


def browser_url(app, local):
    routes = browser_routes.get()
    return local if routes is None else routes.get(app, "")


def operation_links(operations):
    """Rewrite only display links, preserving durable controller receipts."""
    for operation in operations:
        operation["links"] = [dict(link, url=address) for link in operation.get("links", [])
                              if (address := browser_url(link["app"], link["url"]))]
    return operations

"""Bounded Socket.IO polling for the pinned Kuma setup protocol; no browser events."""

import json
import re
import time

import httpx

from .deployment import DeploymentError

EVENTS = {"needSetup", "setup", "login", "getMonitorList", "getAPIKeyList", "addAPIKey", "add"}


class Kuma:
    def __init__(self, url, transport=None):
        self.client = httpx.Client(base_url=url, timeout=20, trust_env=False, follow_redirects=False, transport=transport)
        self.params = {"EIO": "4", "transport": "polling"}
        self.events, self.counter = {}, 0

    def __enter__(self):
        response = self.client.get("/socket.io/", params=self.params)
        response.raise_for_status()
        if not response.text.startswith("0") or len(response.content) > 65536:
            raise DeploymentError("Kuma's setup connection is unavailable.")
        handshake = json.loads(response.text.split("\x1e")[0][1:])
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", handshake.get("sid", "")):
            raise DeploymentError("Kuma returned an invalid setup session.")
        self.params["sid"] = handshake["sid"]
        self.send("40")
        self.receive()
        return self

    def __exit__(self, *args):
        try:
            self.send("41")
        except Exception:
            pass
        self.client.close()

    def send(self, text):
        response = self.client.post("/socket.io/", params=self.params, content=text,
                                    headers={"Content-Type": "text/plain;charset=UTF-8"})
        response.raise_for_status()

    def receive(self):
        response = self.client.get("/socket.io/", params=self.params)
        response.raise_for_status()
        if len(response.content) > 1024 * 1024:
            raise DeploymentError("Kuma returned too much setup data.")
        packets = response.text.split("\x1e")
        for packet in packets:
            if packet == "2":
                self.send("3")
            elif packet.startswith("42["):
                event = json.loads(packet[2:])
                self.events[event[0]] = event[1:]
        return packets

    def call(self, event, *arguments):
        if event not in EVENTS:
            raise DeploymentError("Unsupported Kuma setup operation.")
        self.counter += 1
        identity = str(self.counter)
        self.send("42" + identity + json.dumps([event, *arguments], separators=(",", ":")))
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            for packet in self.receive():
                match = re.match(r"^43([0-9]+)(\[.*)$", packet, re.S)
                if match and match[1] == identity:
                    values = json.loads(match[2])
                    value = values[0] if values else None
                    if isinstance(value, dict) and value.get("ok") is False:
                        raise DeploymentError("Kuma rejected setup. Existing accounts and monitors were preserved.")
                    return value
        raise DeploymentError("Kuma setup timed out. Review the saved installation before retrying.")

    def login(self, login):
        self.call("login", {"username": login["username"], "password": login["password"], "token": ""})

    def monitors(self):
        self.call("getMonitorList")
        value = self.events.get("monitorList", [{}])[0]
        if not isinstance(value, dict):
            raise DeploymentError("Kuma returned an invalid monitor list.")
        return list(value.values())

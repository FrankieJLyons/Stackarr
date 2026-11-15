"""Readable Docker project names, with compatibility for saved alpha receipts."""

import re

APP_PROJECT = re.compile(r"stackarr-apps(?:-[2-9]|-[1-9][0-9]+)?")
CONTROLLER_PROJECT = re.compile(r"stackarr-controller(?:-[2-9]|-[1-9][0-9]+)?")


def app_project(identity, payload):
    project = payload.get("project")
    if project is None:
        return "stackarr-owned-" + identity
    if not isinstance(project, str) or not APP_PROJECT.fullmatch(project):
        raise ValueError("The saved Docker app group name is invalid.")
    return project


def controller_project(project):
    return isinstance(project, str) and bool(
        CONTROLLER_PROJECT.fullmatch(project)
        or re.fullmatch(r"stackarr-(?:preview|plex-lab)-[a-f0-9]{12}", project)
    )


def available_project(call, kind, reserved=()):
    """Never reuse another installation's containers, network or retained volumes."""
    if kind not in {"apps", "controller"}:
        raise ValueError("Unknown Stackarr Docker group.")
    used = set(reserved)
    for arguments in (
        ["ps", "-a", "--format", '{{.Label "com.docker.compose.project"}}'],
        ["volume", "ls", "--format", '{{.Label "com.docker.compose.project"}}'],
        ["network", "ls", "--format", '{{.Label "com.docker.compose.project"}}'],
    ):
        used.update(call(arguments).splitlines())
    base = "stackarr-" + kind
    number = 1
    while (candidate := base if number == 1 else f"{base}-{number}") in used:
        number += 1
    return candidate

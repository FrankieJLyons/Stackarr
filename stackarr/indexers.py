"""Reviewed source setup through Prowlarr's advertised schema and test endpoint.

Schema defaults, provider credentials and saved resources stay server-side. Search
checks are explicit, bounded diagnostics; they never grab or download a release.
"""

import asyncio
import copy
import hashlib
import json
import math
import re
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import Field, field_validator

from .adapters import require_write
from .config import CATALOG, Model, validate_url
from .native_import import require_writable
from .store import Conflict

SOURCE_CHECK_LIMIT = 3


def _configured(rows):
    if (not isinstance(rows, list) or len(rows) > 1000 or any(not isinstance(row, dict) for row in rows)
            or any(not isinstance(row.get("fields", []), list)
                   or any(not isinstance(field, dict) for field in row.get("fields", [])) for row in rows)):
        raise ValueError("The configured sources could not be read. Check the app connection and retry.")
    return rows


class Source(Model):
    name: str = Field(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$")
    feed_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(default="", max_length=512, pattern=r"^[\x21-\x7e]*$")


class ProviderSource(Model):
    provider_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    name: str = Field(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$")
    fields: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=32)


class SourceCheck(Model):
    query: str = Field(min_length=2, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")
    media_type: Literal["movie", "tv"]

    @field_validator("query")
    @classmethod
    def trim_query(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Enter at least two characters to check a source search.")
        return value


def connection(store):
    revision, config = store.config()
    app = config.integrations["prowlarr"]
    key = store.secret("prowlarr").get("api_key")
    if not app.enabled or not key:
        raise ValueError("Finish connecting Prowlarr first.")
    return revision, app.url, key


def endpoint(value):
    url = validate_url(value.strip())
    parsed = urlsplit(url)
    if parsed.query or parsed.hostname in {"169.254.169.254", "metadata.google.internal"}:
        raise ValueError("Enter the feed address without query parameters. Put its key in the private key field.")
    path = parsed.path.rstrip("/") or "/api"
    return f"{parsed.scheme}://{parsed.netloc}", path


def public(plan):
    if "provider" in plan:
        return {"name": plan["name"], "provider": plan["provider"], "already_exists": plan["exists"],
                "notice": "Only this source will be tested and added. Existing sources are preserved. "
                          "Prowlarr checks its account requirements before saving; no media is downloaded."}
    return {"name": plan["name"], "feed_url": plan["feed_url"], "already_exists": plan["exists"],
            "notice": "Test this source in Prowlarr, then save it if compatible. Existing sources are preserved. Prowlarr shares compatible categories with the Arr apps already connected to it. No media is requested or downloaded."}


async def review(store, source, transport=None):
    require_writable(store, "prowlarr")
    revision, base, key = connection(store)
    source = Source.model_validate(source)
    source_base, path = endpoint(source.feed_url)
    async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False, transport=transport,
                                 headers={"X-Api-Key": key}) as client:
        schema = await client.get(base + "/api/v1/indexer/schema")
        schema.raise_for_status()
        template = next((row for row in schema.json() if row.get("implementation") == "Torznab" and row.get("name") == "Generic Torznab"), None)
        if not template:
            raise ValueError("Prowlarr does not advertise a generic Torznab form.")
        profiles = await client.get(base + "/api/v1/appprofile")
        profiles.raise_for_status()
        available = profiles.json()
        if not available or type(available[0].get("id")) is not int:
            raise ValueError("Prowlarr needs an application sync profile before adding a source.")
        payload = {name: template[name] for name in ("implementation", "configContract", "definitionName", "protocol", "fields")}
        payload.update(name=source.name.strip(), enable=True, priority=25, appProfileId=available[0]["id"], tags=[])
        names = {field["name"] for field in payload["fields"]}
        if not {"baseUrl", "apiPath", "apiKey"} <= names:
            raise ValueError("This Prowlarr version does not advertise a compatible Torznab form.")
        for field in payload["fields"]:
            if field["name"] in {"baseUrl", "apiPath", "apiKey"}:
                field["value"] = {"baseUrl": source_base, "apiPath": path, "apiKey": source.api_key}[field["name"]]
        existing = await client.get(base + "/api/v1/indexer")
        existing.raise_for_status()
        exists = duplicate(_configured(existing.json()), source.name.strip(), source_base, path)
    return {"revision": revision, "base": base, "key": key, "name": source.name.strip(),
            "feed_url": source_base + path, "exists": exists, "payload": payload}


def duplicate(rows, name, base, path):
    for row in rows:
        fields = {field["name"]: field.get("value", "") for field in row.get("fields", [])}
        if row.get("name", "").casefold() == name.casefold() or (
            row.get("implementation") == "Torznab" and fields.get("baseUrl", "").rstrip("/") == base
            and fields.get("apiPath", "/api").rstrip("/") == path.rstrip("/")
        ):
            return True
    return False


async def apply(store, plan, transport=None):
    require_writable(store, "prowlarr")
    require_write("prowlarr", "indexer.create")
    if connection(store) != (plan["revision"], plan["base"], plan["key"]):
        raise Conflict("Settings changed. Review this source again.")
    fields = {field["name"]: field.get("value") for field in plan["payload"]["fields"]}
    async with httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False, transport=transport,
                                 headers={"X-Api-Key": plan["key"]}) as client:
        url = plan["base"] + "/api/v1/indexer"
        response = await client.get(url)
        response.raise_for_status()
        rows = _configured(response.json())
        exists = (provider_duplicate(rows, plan["name"], plan["payload"])
                  if "provider" in plan else duplicate(rows, plan["name"], fields["baseUrl"], fields["apiPath"]))
        if exists:
            return {"state": "existing", "detail": "An existing source is preserved. Open Prowlarr to review it."}
        response = await client.post(url + "/test", json=plan["payload"])
        response.raise_for_status()
        if connection(store) != (plan["revision"], plan["base"], plan["key"]):
            raise Conflict("Settings changed during the test. The source was not saved; review again.")
        response = await client.post(url, json=plan["payload"])
        response.raise_for_status()
    store.audit("indexer.created", "prowlarr")
    return {"state": "connected", "detail": "Source tested and saved in Prowlarr. Check source sharing below; no media was downloaded."}


async def status(store, transport=None):
    _, base, key = connection(store)
    config = store.config()[1]
    async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False, transport=transport) as client:
        headers = {"X-Api-Key": key}
        if config.integrations["prowlarr"].request_host:
            headers["Host"] = config.integrations["prowlarr"].request_host
        response = await client.get(base + "/api/v1/indexer", headers=headers)
        response.raise_for_status()
        sources = [{"name": _plain(row.get("name"), "Source"), "enabled": bool(row.get("enable")),
                    **({"id": row["id"]} if type(row.get("id")) is int and row["id"] > 0 else {})}
                   for row in _configured(response.json())]
        apps = []
        prowlarr = config.integrations["prowlarr"]
        native_peer = prowlarr.read_only and urlsplit(prowlarr.browser_url).hostname == "127.0.0.1"
        peer = urlsplit(prowlarr.browser_url if native_peer else prowlarr.peer_url or base)
        for target in ("sonarr", "radarr"):
            app, secret = config.integrations[target], store.secret(target)
            if not app.enabled or not secret.get("api_key"):
                continue
            try:
                arr_headers = {"X-Api-Key": secret["api_key"]}
                if app.request_host:
                    arr_headers["Host"] = app.request_host
                response = await client.get(app.url + "/api/v3/indexer", headers=arr_headers)
                response.raise_for_status()
                shared = 0
                for row in _configured(response.json()):
                    fields = {field["name"]: field.get("value") for field in row.get("fields", [])}
                    address_value = fields.get("baseUrl")
                    if address_value is not None and not isinstance(address_value, str):
                        raise ValueError("The source sharing address could not be read.")
                    address = urlsplit(address_value or "")
                    same = (address.scheme, address.netloc) == (peer.scheme, peer.netloc)
                    if native_peer:
                        same = (address.scheme == peer.scheme and address.hostname in {"localhost", "127.0.0.1", "::1"}
                                and (address.port or 80) == (peer.port or 80))
                    if row.get("implementation") == "Torznab" and same:
                        shared += 1
                apps.append({"app": target, "name": CATALOG[target]["name"], "shared_sources": shared})
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                apps.append({"app": target, "name": CATALOG[target]["name"], "shared_sources": None, "state": "unavailable"})
    return {"sources": sources, "apps": apps}


def _plain(value, fallback, limit=100):
    """Project labels, never upstream HTML, links, addresses or arbitrary help."""
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        return fallback
    if any(char in value for char in "<>/@\\\r\n") or ":" in value:
        return fallback
    return value.strip()


def _provider_id(template):
    identity = [template.get(key) for key in ("implementation", "configContract", "definitionName", "name")]
    fields = template.get("fields")
    hidden = [(field.get("name"), field.get("value")) for field in fields
              if isinstance(field, dict) and field.get("name") == "definitionFile"] if isinstance(fields, list) else []
    return hashlib.sha256(json.dumps([identity, hidden], sort_keys=True).encode()).hexdigest()[:24]


def _private(field):
    name = field.get("name", "").lower()
    return (field.get("type") == "password" or str(field.get("privacy", "")).lower() in {"password", "apikey", "username"}
            or any(part in name for part in ("password", "apikey", "cookie", "passkey", "token", "username")))


def _advertised_address(template, field):
    if field.get("value"):
        return field["value"]
    # Native Prowlarr forms load baseUrl choices with getUrls. The same official
    # choices are advertised on IndexerResource; keep the first on the server.
    if field.get("name") == "baseUrl" and field.get("selectOptionsProviderAction") == "getUrls":
        for address in template.get("indexerUrls") or []:
            try:
                origin, path = endpoint(address)
                return origin + ("" if path == "/api" and urlsplit(address).path in ("", "/") else path)
            except (ValueError, TypeError, AttributeError):
                continue
    return None


def _form(template):
    """A deliberately small advertised-form subset; unusual forms use Prowlarr."""
    output = []
    supported = (template.get("protocol") == "torrent"
                 and template.get("name") != "Generic Torznab"
                 and all(isinstance(template.get(key), str) and template[key]
                         for key in ("implementation", "configContract", "definitionName")))
    fields = template.get("fields")
    if not isinstance(fields, list):
        return [], False
    for field in fields:
        if not isinstance(field, dict):
            supported = False
            continue
        name, kind = field.get("name", ""), field.get("type", "text")
        kind = "text" if kind == "textbox" else kind
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]{0,79}", name):
            supported = False
            continue
        # Keep the advertised default address/definition on the server. Advanced
        # transport/torrent preferences are left as advertised by Prowlarr.
        if field.get("hidden") not in (None, "", "visible", "none") or field.get("advanced"):
            continue
        if name.startswith("torrentBaseSettings.") or name == "vipExpiration":
            continue
        if name in {"baseUrl", "apiPath", "definitionFile"}:
            if not _advertised_address(template, field):
                supported = False
            continue
        if kind in {"info", "alert", "help"}:
            continue
        if kind not in {"text", "password", "checkbox", "number", "select"} or field.get("selectOptionsProviderAction"):
            supported = False
            continue
        private = _private(field)
        projected = {"name": name, "label": _plain(field.get("label"), name),
                     "type": "password" if private else kind,
                     "required": field.get("required") is True, "private": private,
                     "help": ("Use this source's account details. These are sent only to Prowlarr for its source test and save."
                              if private else "Use the value required by your source. Prowlarr checks it before saving.")}
        if kind == "select":
            options = []
            for option in field.get("selectOptions") or []:
                if not isinstance(option, dict):
                    supported = False
                    continue
                value = option.get("value")
                if type(value) not in (str, int) or (isinstance(value, str) and not re.fullmatch(r"[\w .-]{1,80}", value)):
                    supported = False
                    continue
                options.append({"value": value, "label": _plain(option.get("name"), str(value))})
            if not options or len(options) > 100 or private:
                supported = False
            projected["options"] = options[:100]
        output.append(projected)
    return output, supported and len(output) <= 32


async def _schemas(client, base):
    response = await client.get(base + "/api/v1/indexer/schema")
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or len(rows) > 3000 or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Prowlarr's source catalog could not be read. Open Prowlarr to add your source.")
    return rows


async def catalog(store, transport=None):
    """Public source templates, with no schema values, URLs, links or secrets."""
    _, base, key = connection(store)
    async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False, transport=transport,
                                 headers={"X-Api-Key": key}) as client:
        templates = await _schemas(client, base)
    providers = []
    for template in templates:
        fields, supported = _form(template)
        privacy = template.get("privacy", "unknown")
        providers.append({"id": _provider_id(template), "name": _plain(template.get("name"), "Source"),
                          "protocol": template.get("protocol") if template.get("protocol") in {"torrent", "usenet"} else "unknown",
                          "privacy": privacy if privacy in {"public", "private", "semiPrivate"} else "unknown",
                          "supported": supported, "fields": fields if supported else [],
                          "guidance": ("Have your source account ready if it requires one. Prowlarr validates required details before saving."
                                       if supported else "This source needs additional setup. Add it in Prowlarr, then check it here.")})
    return {"providers": sorted(providers, key=lambda row: row["name"].casefold()),
            "notice": "Choose a source you already use. A source may need an account or subscription. "
                      "Sources requiring browser login, captcha or special forms can be added in Prowlarr."}


def provider_duplicate(rows, name, payload):
    identity = (payload.get("implementation"), payload.get("definitionName"))
    definition = next((field.get("value") for field in payload.get("fields", []) if field.get("name") == "definitionFile"), None)
    for row in rows:
        if row.get("name", "").casefold() == name.casefold():
            return True
        if (row.get("implementation"), row.get("definitionName")) == identity:
            other = next((field.get("value") for field in row.get("fields", []) if field.get("name") == "definitionFile"), None)
            if identity[1] and definition == other:
                return True
    return False


async def review_provider(store, source, transport=None):
    require_writable(store, "prowlarr")
    revision, base, key = connection(store)
    source = ProviderSource.model_validate(source)
    if not source.name.strip():
        raise ValueError("Give this source a name.")
    async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False, transport=transport,
                                 headers={"X-Api-Key": key}) as client:
        templates = await _schemas(client, base)
        template = next((row for row in templates if _provider_id(row) == source.provider_id), None)
        if template is None:
            raise ValueError("The source catalog changed. Choose the source again.")
        form, supported = _form(template)
        if not supported:
            raise ValueError("This source needs additional setup in Prowlarr. Add it there, then check it here.")
        allowed = {field["name"]: field for field in form}
        if set(source.fields) - allowed.keys():
            raise ValueError("The source form changed. Choose the source again.")
        payload = {name: copy.deepcopy(template[name]) for name in
                   ("implementation", "configContract", "definitionName", "protocol", "fields")}
        for field in payload["fields"]:
            if field["name"] == "baseUrl" and not field.get("value"):
                field["value"] = _advertised_address(template, field)
            if field["name"] not in allowed:
                continue
            spec = allowed[field["name"]]
            value = source.fields.get(field["name"])
            if value is None:
                if spec["required"]:
                    raise ValueError("Complete the source's required fields before reviewing.")
                # Do not accidentally reuse a credential advertised as a default.
                if spec["private"]:
                    field["value"] = ""
                continue
            if isinstance(value, str) and (len(value) > 2048 or any(ord(char) < 32 or ord(char) == 127 for char in value)):
                raise ValueError("Source details are too long or contain unsupported characters.")
            if spec["type"] == "checkbox" and type(value) is not bool:
                raise ValueError("Choose the checkbox value again.")
            if spec["type"] == "number" and (type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1_000_000_000):
                raise ValueError("Enter a supported number for this source.")
            if spec["type"] == "select" and not any(value == option["value"] and type(value) is type(option["value"]) for option in spec["options"]):
                raise ValueError("Choose an advertised option for this source.")
            if spec["type"] in {"text", "password"} and not isinstance(value, str):
                raise ValueError("Enter text for this source field.")
            if spec["required"] and value == "":
                raise ValueError("Complete the source's required fields before reviewing.")
            if field["name"] in {"baseUrl", "apiPath"} and value:
                raise ValueError("Use the advanced feed form to enter a custom source address.")
            field["value"] = value
        profiles = await client.get(base + "/api/v1/appprofile")
        profiles.raise_for_status()
        available = profiles.json()
        if not available or type(available[0].get("id")) is not int:
            raise ValueError("Prowlarr needs an application sync profile before adding a source.")
        payload.update(name=source.name.strip(), enable=True, priority=25, appProfileId=available[0]["id"], tags=[])
        existing = await client.get(base + "/api/v1/indexer")
        existing.raise_for_status()
        exists = provider_duplicate(_configured(existing.json()), source.name.strip(), payload)
    return {"revision": revision, "base": base, "key": key, "name": source.name.strip(),
            "provider": _plain(template.get("name"), "Source"), "exists": exists, "payload": payload}


def _categories(row, category):
    capabilities = row.get("capabilities")
    if not isinstance(capabilities, dict):
        return "unknown"
    categories = capabilities.get("categories")
    if not isinstance(categories, list):
        return "unknown"
    stack = categories[:]
    examined = 0
    while stack and examined < 1000:
        item = stack.pop()
        examined += 1
        if not isinstance(item, dict):
            return "unknown"
        value = item.get("id")
        if type(value) is int and value // 1000 == category // 1000:
            return "supported"
        children = item.get("subCategories") or []
        if not isinstance(children, list):
            return "unknown"
        stack.extend(children)
    return "missing"


def _source_result(row, category):
    return {"name": _plain(row.get("name"), "Source"), "state": "not-tested",
            **({"id": row["id"]} if type(row.get("id")) is int and row["id"] > 0 else {}),
            "detail": "This source was outside the three-source check limit. Check it in Prowlarr.",
            "result_count": None, "authentication": "unknown", "categories": _categories(row, category),
            "search": "unknown"}


def _authentication_error(response):
    # Inspect only to choose fixed guidance. Never return/log upstream validation
    # messages, which can include private addresses, usernames or provider keys.
    text = response.text[:20000].casefold()
    return response.status_code in {401, 403} or any(
        phrase in text for phrase in ("invalid api key", "invalid credentials", "authentication failed",
                                     "incorrect password", "invalid username", "login failed", "unauthorized"))


async def _history(client, base, source_id):
    response = await client.get(base + "/api/v1/history", params={"indexerIds": source_id, "page": 1,
                                "pageSize": 20, "sortKey": "date", "sortDirection": "descending"})
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows[:20]):
        raise ValueError("Source search history is not available.")
    return rows[:20]


async def _validate_one(client, base, row, check, category, result):
    if result["categories"] == "missing":
        result.update(state="category-missing", detail="This source does not advertise this media category. Choose another source or review its categories in Prowlarr.")
        return
    if type(row.get("id")) is not int or row["id"] < 1:
        result.update(state="unverified", detail="Prowlarr did not return a usable source identity. Review this source in Prowlarr.")
        return
    try:
        response = await client.post(base + "/api/v1/indexer/test", json=row)
        if not response.is_success:
            failed_auth = _authentication_error(response)
            result.update(state="authentication-failed" if failed_auth else "test-failed",
                          authentication="failed" if failed_auth else "unknown",
                          detail=("Source authentication failed. Check your account, private key and subscription in Prowlarr."
                                  if failed_auth else "The source test failed. Review its account requirements and connection in Prowlarr, then retry."))
            return
        # The advertised test can check public/no-auth sources too. 'passed' means
        # its connection/account test succeeded; it is not a playback guarantee.
        result["authentication"] = "passed"
        before = None
        try:
            before = {item.get("id") for item in await _history(client, base, row["id"])
                      if type(item.get("id")) is int}
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            pass
        response = await client.get(base + "/api/v1/search", params={"query": check.query,
                                    "type": "search", "indexerIds": row["id"], "categories": category,
                                    "limit": 20, "offset": 0}, timeout=12)
        response.raise_for_status()
        releases = response.json()
        if not isinstance(releases, list):
            raise ValueError("Source search returned an unsupported response.")
        count = sum(isinstance(item, dict) and item.get("indexerId") == row["id"] for item in releases[:1000])
        if count:
            verified = result["categories"] == "supported"
            result.update(state="results" if verified else "unverified", search="results", result_count=min(count, 20),
                          detail=("The source test passed and this search returned matching releases. Availability and quality still depend on the requested title."
                                  if verified else "The source returned releases, but its media categories could not be verified. Review its category support in Prowlarr before relying on this source."))
            return
        try:
            after = await _history(client, base, row["id"])
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            result.update(state="unverified", detail="The source test passed, but search history could not confirm the empty response. Review the source in Prowlarr and retry.")
            return
        matching = []
        for item in after:
            data = item.get("data") or {}
            if not isinstance(data, dict):
                continue
            if (before is not None and type(item.get("id")) is int and item["id"] not in before
                    and item.get("indexerId") == row["id"] and item.get("eventType") in {"indexerQuery", 2}
                    and data.get("Query") == check.query and data.get("QueryType") == "search"
                    and str(category) in str(data.get("Categories", "")).split(",")):
                matching.append(item)
        if any(item.get("successful") is False for item in matching):
            result.update(state="search-failed", search="failed", detail="The source test passed, but this search failed. Check the source's search limits and connection in Prowlarr.")
        elif matching and all(item.get("successful") is True for item in matching) and result["categories"] == "supported":
            result.update(state="no-matches", search="no-matches", result_count=0,
                          detail="The source test and recorded search passed, but this query returned no matching releases. Try another title or source; no download was started.")
        else:
            result.update(state="unverified", detail="The source test passed, but an empty response did not prove the search ran successfully. Review its search limits and history in Prowlarr.")
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        state = "search-failed" if result["authentication"] == "passed" else "test-failed"
        result.update(state=state, search="failed" if state == "search-failed" else "unknown",
                      detail="This source check could not finish. Check the source connection and limits in Prowlarr, then retry.")


async def validate(store, check, transport=None):
    require_writable(store, "prowlarr")
    """Test at most three enabled sources, without changing settings or grabbing.

    A zero-result search requires a new successful matching history record:
    Prowlarr may otherwise return HTTP 200/[] for failed or quota-skipped searches.
    Only projected outcomes leave this function, never releases/history/secrets.
    """
    check = SourceCheck.model_validate(check)
    _, base, key = connection(store)
    category = 2000 if check.media_type == "movie" else 5000
    async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False, transport=transport,
                                 headers={"X-Api-Key": key}) as client:
        response = await client.get(base + "/api/v1/indexer")
        response.raise_for_status()
        rows = _configured(response.json())
        enabled = [row for row in rows if row.get("enable") is True]
        results = [_source_result(row, category) for row in rows]
        for row, result in zip(rows, results):
            if row.get("enable") is not True:
                result.update(state="disabled", detail="This source is disabled. Enable it in Prowlarr if you want to use it.")
        selected = [(row, result) for row, result in zip(rows, results) if row.get("enable") is True][:SOURCE_CHECK_LIMIT]
        try:
            async with asyncio.timeout(25):
                await asyncio.gather(*(_validate_one(client, base, row, check, category, result) for row, result in selected))
        except TimeoutError:
            for _, result in selected:
                if result["state"] == "not-tested":
                    result.update(state="unverified", detail="The bounded source check timed out. Review this source in Prowlarr and retry.")
    sharing = None
    try:
        async with asyncio.timeout(5):
            sharing = await status(store, transport)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, TimeoutError):
        pass
    checked = [result for _, result in selected]
    outcomes = {row["state"] for row in checked}
    state = ("not-configured" if not enabled else "needs-attention" if outcomes - {"results", "no-matches"}
             else "results" if "results" in outcomes else "no-matches")
    return {"media_type": check.media_type, "state": state, "sources": results,
            "checked_sources": len(checked), "total_enabled": len(enabled), "limited": len(enabled) > SOURCE_CHECK_LIMIT,
            "sharing": sharing,
            "notice": "This check tests source accounts and one category-filtered search for up to three enabled sources. "
                      "It does not request, download, import or play media. A passing source does not prove a title can be watched."}

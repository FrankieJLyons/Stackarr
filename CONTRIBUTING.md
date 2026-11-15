# Contributing

Run the quality gate before opening a change:

```text
python -m ruff check stackarr tests tools
python -m pytest -q
python tools/browser_check.py
python -m pip_audit -r requirements.lock
```

Use synthetic fixtures for application APIs. Never point tests or screenshots at a personal media host. Changes to configuration fields require a schema test, redaction test, migration note, and a review of whether the setting applies immediately or needs a restart. Changes to collectors must preserve unavailable versus empty data and should include a malformed-response fixture.

Do not add credentials, private paths, hostnames, certificates, media titles, downloaded files, or application databases. Keep upstream image tags and icon licenses documented.

from stackarr.integrations import summarize


def row(key, table, count=0, state="ready", stale=False):
    return {"id": key, "name": key, "capabilities": [table], "tables": {table: [{}] * count},
            "state": state, "stale": stale}


def test_unrelated_failure_cannot_hide_downloads():
    result = summarize([row("qbittorrent", "downloads", 3), row("prowlarr", "sources", state="unavailable")], "downloads")
    assert result["count"] == 3 and result["state"] == "complete"


def test_partial_counts_are_explicit_and_missing_is_not_zero():
    result = summarize([row("sonarr", "queue", 2), row("radarr", "queue", 5, stale=True)], "queue")
    assert result["state"] == "partial" and result["count"] == 2
    assert result["missing"] == ["radarr"]
    assert summarize([], "queue")["count"] is None
    assert summarize([row("radarr", "queue", state="unavailable")], "queue")["count"] is None
    assert summarize([row("radarr", "queue")], "queue")["count"] == 0


def test_plex_and_tautulli_are_not_double_counted():
    assert summarize([row("plex", "streams", 2), row("tautulli", "streams", 2)], "streams")["count"] == 2
    assert summarize([row("tautulli", "streams", 2)], "streams")["count"] == 2

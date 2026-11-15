#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! command -v xdg-open >/dev/null 2>&1 && ! command -v open >/dev/null 2>&1; then
    echo 'Start Stackarr needs a desktop browser. For a headless server, see the Docker setup guide.' >&2
    exit 1
fi
docker compose up -d --build --wait --wait-timeout 120 stackarr
setup_address=$(docker compose exec -T stackarr stackarr setup-link)
case "$setup_address" in http://*|https://*) ;; *) echo 'Stackarr could not open setup.' >&2; exit 1;; esac
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$setup_address" >/dev/null 2>&1
else
    open "$setup_address"
fi
echo 'Stackarr is open in your browser.'

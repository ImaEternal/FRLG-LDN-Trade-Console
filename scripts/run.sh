#!/usr/bin/env bash
# Thin wrapper so you do not have to remember the compose incantation.
#   ./run.sh --live -o out/received.pk3 pk3/A.pk3 pk3/B.pk3
#   ./run.sh --replay capture.jsonl pk3/A.pk3 pk3/B.pk3
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
if [[ " $* " == *" --live "* ]]; then
  [[ -s keys/prod.keys ]] || { echo "!! keys/prod.keys is missing or empty" >&2; exit 1; }
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"; [[ -f "$ROOT/.env" ]] && . "$ROOT/.env"
  if ip route show default | grep -q "${FRLG_WIFI_IF:-wlan0}"; then
    echo "!! the wireless interface still holds the default route — run ./radio.sh take first" >&2
    exit 1
  fi
fi
exec docker compose run --rm frlg "$@"

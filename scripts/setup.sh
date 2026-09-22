#!/usr/bin/env bash
# One-time setup. Fetches the things this repository deliberately does not ship:
#
#   vendor/frlg-ldn-trade   upstream's AGPL-3.0 engine, plus our patches
#   web/static/sprites      Gen-3 sprites (Nintendo's artwork, not ours to redistribute)
#   data/*.json             game data derived from the PokeAPI dataset
#
# Safe to re-run.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

UPSTREAM="${FRLG_UPSTREAM:-https://github.com/tornadus/frlg-ldn-trade}"

echo "==> upstream engine"
mkdir -p vendor
if [[ -d vendor/frlg-ldn-trade/.git ]]; then
  git -C vendor/frlg-ldn-trade fetch --depth 1 origin && \
  git -C vendor/frlg-ldn-trade reset --hard origin/HEAD
else
  git clone --depth 1 "$UPSTREAM" vendor/frlg-ldn-trade
fi

echo "==> applying patches (AGPL-3.0, see patches/README.md)"
for p in patches/*.patch; do
  [[ -e "$p" ]] || continue
  if patch -p0 -d vendor/frlg-ldn-trade --forward --silent --dry-run < "$p" >/dev/null 2>&1; then
    patch -p0 -d vendor/frlg-ldn-trade --forward --silent < "$p"
    echo "    applied $(basename "$p")"
  else
    echo "    skipped $(basename "$p") (already applied, or upstream moved)"
  fi
done

echo "==> game data"
[[ -s data/dex.json ]]   || python3 scripts/build_dex.py
[[ -s data/items.json ]] || python3 scripts/build_items.py

echo "==> sprites"
if [[ ! -d web/static/sprites/normal ]] || \
   [[ $(ls web/static/sprites/normal 2>/dev/null | wc -l) -lt 386 ]]; then
  bash scripts/fetch_sprites.sh
else
  echo "    already present"
fi

echo "==> config"
[[ -f .env ]] || { cp .env.example .env; echo "    wrote .env — EDIT IT before running"; }
mkdir -p keys pk3 out box control

cat <<'DONE'

Setup complete. Next:
  1. edit .env                       (interfaces for your machine)
  2. put prod.keys in keys/          (dumped from your own console)
  3. docker compose up -d dashboard
  4. open http://localhost:8781
DONE

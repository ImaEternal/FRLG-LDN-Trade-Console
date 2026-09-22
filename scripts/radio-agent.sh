#!/usr/bin/env bash
# Host-side helper. The dashboard container writes one word into control/request;
# this runs the already-tested radio.sh and reports back in control/status.json.
#
# Why this exists: freeing the WiFi card changes HOST networking. Letting a
# container do that means handing it the host's namespaces, which is a
# container escape in all but name. A request file plus a host service keeps
# the privileged action on the host, where it belongs, and auditable.
set -uo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
REQ=control/request
OUT=control/status.json
[[ -f $REQ ]] || exit 0
action="$(tr -d '[:space:]' < "$REQ")"
rm -f "$REQ"
if [[ $action != take && $action != give-back ]]; then
  printf '{"action":"%s","ok":false,"error":"unknown action","at":"%s"}\n' \
    "$action" "$(date -Is)" > "$OUT"
  exit 0
fi
log=$(scripts/radio.sh "$action" 2>&1); rc=$?
LOG="$log" ACTION="$action" RC="$rc" OUTF="$OUT" python3 -c '
import json, os, datetime
json.dump({"action": os.environ["ACTION"],
           "ok": os.environ["RC"] == "0",
           "rc": int(os.environ["RC"]),
           "log": os.environ["LOG"].splitlines()[-12:],
           "at": datetime.datetime.now().astimezone().isoformat()},
          open(os.environ["OUTF"], "w"), indent=1)'

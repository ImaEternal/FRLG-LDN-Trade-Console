#!/usr/bin/env bash
# Syntax-check everything before building. A JavaScript syntax error takes the
# WHOLE dashboard down — no dex, no buttons, no console output — and the only
# clue is one line in the browser console, which is easy to miss when the page
# still renders its static HTML. Cheap to check, expensive to miss.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
fail=0

for f in web/*.py scripts/*.py; do
  [[ -e $f ]] || continue
  python3 -c "import ast,sys; ast.parse(open('$f').read())" \
    && echo "  ok   $f" || { echo "  FAIL $f"; fail=1; }
done

for f in scripts/*.sh; do
  [[ -e $f ]] || continue
  bash -n "$f" && echo "  ok   $f" || { echo "  FAIL $f"; fail=1; }
done

if command -v node >/dev/null; then
  for f in web/static/*.js; do
    [[ -e $f ]] || continue
    # `node --check` only accepts CommonJS; wrap so browser globals are fine.
    if node -e "new Function(require('fs').readFileSync('$f','utf8'))" 2>/dev/null; then
      echo "  ok   $f"
    else
      echo "  FAIL $f"
      node -e "new Function(require('fs').readFileSync('$f','utf8'))" 2>&1 | head -4 | sed 's/^/       /'
      fail=1
    fi
  done
else
  echo "  skip web/static/*.js (node not installed)"
fi

python3 - <<'PY' || fail=1
import re, sys, pathlib
html = pathlib.Path("web/templates/index.html").read_text()
js   = pathlib.Path("web/static/app.js").read_text()
# Every element the script reaches for by id should exist in the template.
ids  = set(re.findall(r'id="([\w-]+)"', html))
used = set(re.findall(r'\$\("#([\w-]+)"\)', js))
missing = sorted(u for u in used if u not in ids)
if missing:
    print("  FAIL web/static/app.js references ids not in the template:")
    for m in missing:
        print(f"       #{m}")
    sys.exit(1)
print(f"  ok   all {len(used)} referenced ids exist in the template")
PY

[[ $fail -eq 0 ]] && echo "  ALL CHECKS PASSED" || echo "  CHECKS FAILED"
exit $fail

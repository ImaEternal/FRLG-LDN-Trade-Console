#!/usr/bin/env bash
# Pull Gen-3 front sprites (normal + shiny) once, so the dashboard never
# depends on the network. FRLG is the target game, so prefer its sprites and
# fall back through the other Gen-3 games for the handful it lacks.
set -uo pipefail
cd "$(dirname "$0")"
B=https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-iii
OUT=web/static/sprites
mkdir -p "$OUT/normal" "$OUT/shiny"

grab() {  # grab <natdex> <normal|shiny>
  local id=$1 kind=$2 sub="" ; [[ $kind == shiny ]] && sub="shiny/"
  local dest="$OUT/$kind/$id.png"
  [[ -s $dest ]] && return 0
  for game in firered-leafgreen emerald ruby-sapphire; do
    if curl -sfL --max-time 20 "$B/$game/$sub$id.png" -o "$dest" && [[ -s $dest ]]; then
      return 0
    fi
  done
  rm -f "$dest"; echo "MISS $kind/$id"
}
export -f grab; export B OUT

seq 1 386 | xargs -P 16 -I{} bash -c 'grab {} normal'
seq 1 386 | xargs -P 16 -I{} bash -c 'grab {} shiny'
echo "normal: $(ls $OUT/normal | wc -l)/386   shiny: $(ls $OUT/shiny | wc -l)/386"
du -sh "$OUT"

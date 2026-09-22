#!/usr/bin/env python3
"""Build a compact Gen-3 species dataset from the PokeAPI CSV dumps.

Produces data/dex.json: everything the pk3 builder and the dashboard need,
baked once so neither has to touch the network at runtime.

The important subtlety is the species index. A .pk3 stores the GAME'S INTERNAL
index, which tracks National Dex only up to #251; the 135 Gen-3 species sit at
277..411 because 252..276 are the Unown-form/placeholder block. Writing a
National Dex number straight into a .pk3 for anything above Chikorita's line
yields the wrong Pokemon or a bad egg.
"""
import csv, io, json, urllib.request, collections

BASE = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
def get(name):
    with urllib.request.urlopen(BASE + name, timeout=60) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode())))

print("fetching csvs...")
pokemon   = get("pokemon.csv")
stats     = get("pokemon_stats.csv")
species   = get("pokemon_species.csv")
ptypes    = get("pokemon_types.csv")
types     = get("types.csv")
moves     = get("moves.csv")
pmoves    = get("pokemon_moves.csv")

FRLG_VG = "7"          # FireRed/LeafGreen version group
LEVEL_UP = "1"         # pokemon_move_method_id
STAT = {"1":"hp","2":"atk","3":"def","4":"spa","5":"spd","6":"spe"}
GROWTH = {"1":"slow","2":"medium","3":"fast","4":"medium-slow",
          "5":"erratic","6":"fluctuating"}

type_name = {t["id"]: t["identifier"] for t in types}
move_name = {m["id"]: m["identifier"] for m in moves}
# Gen 3 move ids are 1..354; anything later cannot exist in FRLG.
gen3_move = {m["id"] for m in moves if int(m["generation_id"]) <= 3}

base = collections.defaultdict(dict)
for s in stats:
    if s["stat_id"] in STAT:
        base[s["pokemon_id"]][STAT[s["stat_id"]]] = int(s["base_stat"])

tmap = collections.defaultdict(list)
for t in sorted(ptypes, key=lambda r: int(r["slot"])):
    tmap[t["pokemon_id"]].append(type_name[t["type_id"]])

learn = collections.defaultdict(list)
for m in pmoves:
    if m["version_group_id"] == FRLG_VG and m["pokemon_move_method_id"] == LEVEL_UP:
        if m["move_id"] in gen3_move:
            learn[m["pokemon_id"]].append((int(m["level"]), m["move_id"]))

growth = {s["id"]: GROWTH.get(s["growth_rate_id"], "medium") for s in species}

def internal_index(natdex):
    """National Dex -> the index Gen 3 actually stores in a .pk3."""
    return natdex if natdex <= 251 else natdex + 25

out = {}
for p in pokemon:
    pid = int(p["id"])
    if pid > 386 or p["is_default"] != "1":
        continue
    sid = p["species_id"]
    lv = sorted(learn.get(p["id"], []))
    out[pid] = {
        "natdex": pid,
        "index": internal_index(pid),          # what goes in the .pk3
        "name": p["identifier"].replace("-", " ").title(),
        "base": base[p["id"]],
        "types": tmap.get(p["id"], ["normal"]),
        "growth": growth.get(sid, "medium"),
        # (level, move_id) pairs; the builder picks the last four at or below
        # the requested level, which is what the game itself would have.
        "learnset": [[l, int(m)] for l, m in lv],
    }

with open("data/dex.json", "w") as f:
    json.dump(out, f, separators=(",", ":"))
with open("data/moves.json", "w") as f:
    json.dump({int(i): move_name[i].replace("-", " ").title()
               for i in gen3_move}, f, separators=(",", ":"))
print(f"wrote data/dex.json: {len(out)} species")
miss = [k for k, v in out.items() if not v["learnset"]]
print(f"  species with no FRLG level-up moves: {len(miss)}")
print(f"  index check: Bulbasaur={out[1]['index']} (exp 1), "
      f"Treecko={out[252]['index']} (exp 277), Deoxys={out[386]['index']} (exp 411)")

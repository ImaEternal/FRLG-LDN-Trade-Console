#!/usr/bin/env python3
"""Build data/items.json: Gen-3 internal item indices -> display names.

A .pk3 stores the GAME'S internal item index, not a National-Dex-style id, so
the mapping has to come from the generation-3 game indices specifically.
Source data: the PokeAPI CSV dataset.
"""
import csv, io, json, os, urllib.request

BASE = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "data", "items.json")


def get(name):
    with urllib.request.urlopen(BASE + name, timeout=60) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode())))


def main():
    names = {i["id"]: i["identifier"] for i in get("items.csv")}
    out = {}
    for g in get("item_game_indices.csv"):
        if g["generation_id"] == "3":
            ident = names.get(g["item_id"])
            if ident:
                out[int(g["game_index"])] = ident.replace("-", " ").title()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT}: {len(out)} Gen-3 items")


if __name__ == "__main__":
    main()

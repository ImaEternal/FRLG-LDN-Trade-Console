# Licensing

This repository is **not** a single licence, and the split is deliberate.

## Our code — EUPL-1.2

Everything in `web/`, `scripts/`, `systemd/`, `docs/` and the repository root
is licensed under the **European Union Public Licence v1.2** ([LICENSE](LICENSE)).

The EUPL is a strong copyleft licence. In short, if you distribute this — or a
modified version, or something built on it — you must:

- **attribute** the original work, and
- **publish your modifications** under the EUPL (or a compatible licence
  listed in its Article 5).

It is the European Commission's own licence, is available in all 23 official EU
languages with each version equally legally valid, and is explicitly designed to
be compatible with the GPL/AGPL family.

## Upstream's engine — AGPL-3.0, and not vendored here

The LDN/Pia/trade engine is [`tornadus/frlg-ldn-trade`](https://github.com/tornadus/frlg-ldn-trade),
licensed **AGPL-3.0**. It is **not** copied into this repository.
`scripts/setup.sh` clones it into `vendor/` at install time.

This is the reason for the split. AGPL-3.0 is copyleft: a combined work that
embeds AGPL source must itself be AGPL. By keeping upstream's code out of this
tree and depending on it instead, our own work remains separately licensable —
and upstream keeps its authorship rather than being absorbed into someone
else's repository.

## Our changes to upstream — AGPL-3.0

`patches/` contains modifications to upstream's `frlgsim/transport.py`. Those
are derivative of AGPL-3.0 code and are therefore **themselves AGPL-3.0**, not
EUPL-1.2. They are published here so the changes are public, as the AGPL
requires. See [patches/README.md](patches/README.md).

## Third-party data and assets

| what | where from | note |
|---|---|---|
| Sprites | [PokeAPI/sprites](https://github.com/PokeAPI/sprites) | Nintendo/Game Freak artwork. **Not redistributed here** — fetched at setup. |
| Species, moves, items | [PokeAPI dataset](https://github.com/PokeAPI/pokeapi) | Generated at setup into `data/`, not committed. |
| LDN protocol library | [kinnay/LDN](https://github.com/kinnay/LDN) | GPL-3.0, installed from PyPI as `ldn`. |

Pokémon and the Pokémon character names are trademarks of Nintendo, Creatures
Inc. and GAME FREAK Inc. This project is unaffiliated with and unendorsed by
any of them.

## Not covered by any licence here

`prod.keys` is not distributable under any terms. It is gitignored, and you
must dump it from a console you own.

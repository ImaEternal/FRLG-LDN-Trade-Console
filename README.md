<div align="center">

<img src="docs/pokeball.svg" width="110" alt="">

# FRLG Trade Console

**Build any Gen III Pokémon in a browser and trade it to a real Nintendo Switch
over local wireless.**

No mods. No custom firmware. No save editing — the console performs an ordinary
in-game trade, and this sits on the other end of it.

Built on **[tornadus/frlg-ldn-trade](https://github.com/tornadus/frlg-ldn-trade)**,
which did the hard part: proving a PC can join a Switch's LDN session and speak
FireRed/LeafGreen's link protocol. That engine does the trading. This is the
interface around it.

[![Licence: EUPL-1.2](https://img.shields.io/badge/licence-EUPL--1.2-1f6feb)](LICENSE)
[![Engine: AGPL-3.0](https://img.shields.io/badge/engine-AGPL--3.0-6f42c1)](LICENSING.md)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-2ea043)](#requirements)

</div>

<div align="center">
<img src="docs/screenshots/dashboard.png" width="920" alt="The dashboard">
</div>

---

## What it adds

Upstream is a command-line proof of concept: you hand-craft `.pk3` files, wrestle
the Wi-Fi card away from NetworkManager, and read stack traces when it doesn't
work. This adds:

- **All 386 Gen III species** with in-game sprites, searchable
- **Level, nature, nickname, held item, moves, IVs and EVs** — validated against
  what the games actually allow
- **A party of six and a box** of saved builds
- **Radio control from the browser** that won't cut your own network
- **Diagnostics for when it fails** — the hard part of this project is never the
  Pokémon, it's the radio

<div align="center">

### Builder

<img src="docs/screenshots/builder.png" width="900" alt="Builder">

<sub>Level, nature, nickname, OT, held item, friendship and shininess — with legal level-up moves, IVs and EVs behind the two panels below</sub>

### Party and controls

<img src="docs/screenshots/bay.png" width="900" alt="Healing bay">

<sub>Six sockets with type-coloured rings · radio control and diagnostics · a live trade log</sub>

### Responsive

<img src="docs/screenshots/mobile.png" width="900" alt="Mobile">

<sub>Usable from a phone while you stand at the Switch</sub>

</div>

### Details it gets right

- **Shininess is solved for, not flagged.** It's a property of the PID —
  `(TID ^ SID ^ PIDhi ^ PIDlo) < 8` — so a shiny request means finding a PID
  that satisfies it *and* your chosen nature.
- **Species use the game's internal index**, which diverges from National Dex
  above #251. Treecko is Dex 252 but index 277; writing the Dex number gives
  you a bad egg.
- **EVs are capped** at 255 per stat and 510 total, trimmed from the largest down.
- **Moves are restricted** to what that species legally learns by level-up in FRLG.

## Requirements

### Wi-Fi card — the part that decides whether this works

LDN needs a card that can transmit and receive action frames in monitor mode.
This is the single biggest cause of failure. From upstream's testing:

| Model | Type | Driver | Reliability |
|---|---|---|---|
| ALFA AWUS036ACHM | External (USB) | `mt76x0u` | **High** |
| Realtek RTL8821CE | Internal (PCIe 1x) | `rtw88_8821ce` | **High** |
| AMD RZ616 | Internal (M.2) | `mt7921e` | Low |

**Known problematic:**

| Model | Type | Driver | Issue |
|---|---|---|---|
| Intel AX200 | Internal (M.2) | `iwlwifi` | cannot be assigned an IP |
| Atheros AR9271 | External | `ath9k_htc` | cannot be assigned an IP (usually) |

Before buying anything, **use the built-in card test** — it actually transmits
action frames, which `iw list` cannot tell you. An external ALFA AWUS036ACHM is
the safe choice and has the side benefit of leaving your internal card free to
keep the machine online.

### Everything else

| | |
|---|---|
| **OS** | Linux. LDN needs raw nl80211 access; there is no macOS or Windows path. |
| **Switch** | FireRed or LeafGreen via the GBA Nintendo Switch Online app, played to the **Direct Corner** (roughly 20–40 minutes in). Switch or Switch 2. |
| **`prod.keys`** | Dumped from a console you own with [Lockpick_RCM](https://github.com/shchmue/Lockpick_RCM). Not downloadable — see [keys/README.md](keys/README.md). |
| **Runtime** | Docker, or Python 3.12+ directly. |

No particular router or network is required — LDN is peer-to-peer between the
PC and the console. A console associated to a 5GHz access point may host the
session on a 5GHz channel, which this scans for.

## Install

```bash
git clone https://github.com/ImaEternal/FRLG-Trade-Console
cd FRLG-Trade-Console
bash scripts/setup.sh          # fetches upstream, applies patches, gets sprites + data
cp /path/to/prod.keys keys/    # from your own console
docker compose up -d dashboard
```

Open **http://localhost:8781**.

`setup.sh` fetches rather than ships three things: upstream's AGPL engine,
Nintendo's sprite artwork, and the PokeAPI-derived game data. See
[LICENSING.md](LICENSING.md).

### If the dashboard will manage your radio

Only needed if the card you're giving to LDN is also the one keeping this
machine online — typically a laptop with one internal card. Copy `.env.example`
to `.env` and set your interfaces:

```bash
cp .env.example .env && $EDITOR .env
```

With a dedicated USB adapter you can skip this entirely and let upstream's own
handling take the card.

## Using it

1. On the Switch: **Direct Corner → trade → Leader**, and *stay on the waiting screen*
2. **Scan for console** — confirms your session is visible before you commit
3. **Start trade** → approve the join from `EMU` on the Switch
4. Walk to the **left chair**, pick what you're sending, accept
5. Back at the trade menu, **cancel**, then walk out

You receive whatever is in **slot 2**. What you traded away is saved to `out/`.

## When it doesn't work

The failure modes are indistinguishable without tooling. Three buttons separate them:

| button | answers |
|---|---|
| **Test card** | *Can this card do LDN at all?* Actually transmits action frames. |
| **Listen (raw)** | *Is the console emitting?* Raw per-channel capture, **no keys, no LDN decode**. Frames but no action frames ⇒ the console isn't advertising. Action frames ⇒ the radio is fine and the fault is higher up. |
| **Scan for console** | *Is it MY game?* Prints each network's `local_communication_id` and whether it's FRLG or another title. |

### `no joinable FRLG network (saw 0)`

The most common failure, with four distinct causes — all fixed in [`patches/`](patches/README.md):

- **The scan window is 330ms.** Upstream dwells 0.11s across three channels; a
  console is easily missed in that blink. Widened and made tunable.
- **5GHz is never scanned.** The LDN library supports `36/40/44/48`; upstream
  only scans `1/6/11`.
- **The comm-id varies by region and app version.** Upstream hardcodes
  `0x0100610011000000`. Read yours with **Scan for console** and set
  `FRLG_COMM_ID` in `.env`.
- **It joins the wrong console.** Upstream falls back to "the only joinable
  network", which with another Switch nearby means associating to a stranger's
  game and being rejected. Now opt-in via `FRLG_ANY_NETWORK=1`.

## Architecture

```
browser ──HTTP/SSE──► Flask (container, host network, privileged)
                        │
                        ├── pk3build.py   .pk3 construction: crypto, PID solving, stats
                        ├── scan.py       LDN discovery
                        ├── diag.py       raw capture + injection test
                        └── frlgtrade.py  upstream engine ──► nl80211 ──► Wi-Fi ──► Switch
```

The container is privileged and shares the host network namespace because `ldn`
drives the card over netlink. It is deliberately **not** given host PID or mount
namespaces — changing host networking from inside a container is a container
escape in all but name, so radio switching goes through a request file that a
systemd path unit on the host picks up. Units are in [`systemd/`](systemd/) for
anyone who wants the dashboard to start at boot; neither is required to trade.

## Credits

**[tornadus/frlg-ldn-trade](https://github.com/tornadus/frlg-ldn-trade)** (AGPL-3.0)
— the LDN/Pia/trade engine this is built on, and the project that proved the
whole thing was possible.

**[kinnay/LDN](https://github.com/kinnay/LDN)** (GPL-3.0) — the local-wireless
implementation everything rests on, and the
[NintendoClients wiki](https://github.com/kinnay/NintendoClients/wiki).

**[pret/pokefirered](https://github.com/pret/pokefirered)** — the FireRed
decompilation, used to cross-check the Gen III data structures.

**[PokeAPI](https://github.com/PokeAPI/pokeapi)** — species, move and item data,
and the sprite mirror.

See [NOTICE](NOTICE) for full attribution.

## Licence

Our code is **[EUPL-1.2](LICENSE)** — attribute the original, and publish your
modifications. Upstream's engine remains AGPL-3.0 and is fetched rather than
vendored; our patches to it are AGPL-3.0 too. [LICENSING.md](LICENSING.md)
explains the split.

Pokémon is a trademark of Nintendo, Creatures Inc. and GAME FREAK Inc. This
project is unaffiliated with and unendorsed by any of them. Use it with games
and hardware you own.

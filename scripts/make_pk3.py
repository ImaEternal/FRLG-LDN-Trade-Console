#!/usr/bin/env python3
"""Generate valid Gen-3 .pk3 files for use as trade fodder.

Written instead of downloading .pk3 files from the internet: these are 100-byte
data structures, not content, so building them from the format is both safer
and gives exact control over what goes in. The layout, substruct shuffle and
checksum all come from frlgsim/mon.py, so anything produced here round-trips
through the project's own decoder.

  python3 make_pk3.py                  # write the default pair into pk3/
  python3 make_pk3.py --list           # show selectable species
"""
import argparse, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frlgsim import charmap
from frlgsim.mon import (decode_mon, to_encrypted, SECURE_OFF, SECURE_END,
                         BOX_SIZE, PARTY_MON_SIZE)

# species id -> (name, base stats HP/Atk/Def/Spe/SpA/SpD, a legal level-up move set)
SPECIES = {
    1:   ("BULBASAUR", (45, 49, 49, 45, 65, 65), [33, 45, 73, 22]),
    4:   ("CHARMANDER",(39, 52, 43, 65, 60, 50), [10, 43, 52, 108]),
    7:   ("SQUIRTLE",  (44, 48, 65, 43, 50, 64), [33, 39, 145, 110]),
    25:  ("PIKACHU",   (35, 55, 40, 90, 50, 50), [84, 45, 86, 98]),
    133: ("EEVEE",     (55, 55, 50, 55, 45, 65), [33, 39, 98, 44]),
    129: ("MAGIKARP",  (20, 10, 55, 80, 15, 20), [150, 0, 0, 0]),
}
# Gen-3 experience groups vary; medium-fast (n^3) is correct for all of the above.
def exp_for_level(level): return level ** 3

def make_pk3(species_id, level=20, ot_name="EMU", tid=12345, sid=54321,
             nickname=None, seed=None):
    """Build one decrypted, canonical .pk3 (100-byte party form)."""
    rng = random.Random(seed)
    name, base, moves = SPECIES[species_id]
    nickname = (nickname or name)[:10]

    # PID must not equal OTID: when the XOR key is zero the encrypted and
    # decrypted forms are indistinguishable and from_pk3 cannot tell which it
    # was handed (mon.py says so explicitly).
    otid = (sid << 16) | tid
    while True:
        pid = rng.getrandbits(32)
        if pid != otid and pid != 0:
            break

    mon = bytearray(PARTY_MON_SIZE)
    mon[0:4]   = pid.to_bytes(4, "little")
    mon[4:8]   = otid.to_bytes(4, "little")
    mon[8:18]  = charmap.encode(nickname, width=10)
    mon[18]    = 2                                  # language: English
    mon[19]    = 0x02                               # isBadEgg=0, hasSpecies=1, isEgg=0
    mon[20:27] = charmap.encode(ot_name[:7], width=7)
    mon[27]    = 0                                  # markings

    # --- the four 12-byte substructs, in canonical G A E M order -------------
    exp = exp_for_level(level)
    growth = bytearray(12)
    growth[0:2] = species_id.to_bytes(2, "little")
    growth[2:4] = (0).to_bytes(2, "little")         # held item: none
    growth[4:8] = exp.to_bytes(4, "little")
    growth[8]   = 0                                 # pp bonuses
    growth[9]   = 70                                # friendship
    attacks = bytearray(12)
    for i, mv in enumerate(moves):
        attacks[i*2:i*2+2] = mv.to_bytes(2, "little")
    for i, mv in enumerate(moves):
        attacks[8+i] = 35 if mv else 0              # current PP
    evs = bytearray(12)                             # all zero: a freshly caught mon
    misc = bytearray(12)
    misc[0:2] = (0).to_bytes(2, "little")           # pokerus / met location
    misc[2:4] = ((level & 0x7F) | (1 << 7)).to_bytes(2, "little")  # met level, ball, game
    ivs = 0
    for i in range(6):
        ivs |= (rng.randint(20, 31) & 0x1F) << (i * 5)
    misc[4:8] = ivs.to_bytes(4, "little")

    mon[SECURE_OFF:SECURE_END] = growth + attacks + evs + misc

    # Checksum is over the canonical (decrypted, unshuffled) secure region.
    sec = mon[SECURE_OFF:SECURE_END]
    chk = sum(int.from_bytes(sec[i*2:i*2+2], "little") for i in range(24)) & 0xFFFF
    mon[28:30] = chk.to_bytes(2, "little")

    # --- party tail (level and computed stats) -------------------------------
    hp_iv = ivs & 0x1F
    hp = ((2*base[0] + hp_iv) * level) // 100 + level + 10
    mon[80:84] = (0).to_bytes(4, "little")          # status
    mon[84]    = level
    mon[85]    = 0                                  # mail id
    mon[86:88] = hp.to_bytes(2, "little")           # current HP
    mon[88:90] = hp.to_bytes(2, "little")           # max HP
    for i, bs in enumerate(base[1:6]):              # Atk Def Spe SpA SpD
        iv = (ivs >> (5 * (i + 1))) & 0x1F
        st = ((2*bs + iv) * level) // 100 + 5
        mon[90 + i*2 : 92 + i*2] = st.to_bytes(2, "little")
    return bytes(mon)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="pk3")
    ap.add_argument("--ot", default="EMU")
    ap.add_argument("--tid", type=int, default=12345)
    ap.add_argument("--sid", type=int, default=54321)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--species", type=int, nargs="*",
                    help="species ids to generate (default: 129 and 25)")
    ap.add_argument("--level", type=int, default=20)
    a = ap.parse_args()
    if a.list:
        for k, (n, *_ ) in sorted(SPECIES.items()):
            print(f"  {k:4}  {n}")
        return
    ids = a.species or [129, 25]
    os.makedirs(a.out_dir, exist_ok=True)
    for n, sid_ in enumerate(ids, 1):
        if sid_ not in SPECIES:
            sys.exit(f"unknown species {sid_}; try --list")
        data = make_pk3(sid_, level=a.level, ot_name=a.ot, tid=a.tid, sid=a.sid, seed=sid_)
        path = os.path.join(a.out_dir, f"PARTY{n}.pk3")
        with open(path, "wb") as f:
            f.write(data)
        # Verify through the project's own decoder, in the wire form it will
        # actually be transmitted as.
        d = decode_mon(to_encrypted(data))
        print(f"  wrote {path}  {len(data)}B  {d['species_name']} lv{d['level']} "
              f"OT={d['otName']} checksum_ok={d['checksum_ok']}")

if __name__ == "__main__":
    main()

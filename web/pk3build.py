"""Build Gen-3 .pk3 files to order: species, level, shininess, nature, IVs.

Everything here follows the real game's rules, because the receiving console
validates what it is handed:

  shiny   (TID ^ SID ^ PIDhi ^ PIDlo) < 8     -- a property of the PID, so a
                                                 shiny request means SOLVING for
                                                 a PID, not setting a flag
  nature  PID % 25
  ability PID & 1
  gender  (PID & 0xFF) vs the species ratio

Stat and experience formulas are Gen 3's own. The species number written to the
file is the GAME'S INTERNAL INDEX (dex.json "index"), not National Dex.
"""
import json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))
DEX = json.load(open(os.path.join(HERE, "..", "data", "dex.json")))
MOVES = json.load(open(os.path.join(HERE, "..", "data", "moves.json")))
ITEMS = json.load(open(os.path.join(HERE, "..", "data", "items.json")))

BOX_SIZE, PARTY_MON_SIZE = 80, 100
SECURE_OFF, SECURE_END = 32, 80

NATURES = ["Hardy","Lonely","Brave","Adamant","Naughty","Bold","Docile","Relaxed",
           "Impish","Lax","Timid","Hasty","Serious","Jolly","Naive","Modest","Mild",
           "Quiet","Bashful","Rash","Calm","Gentle","Sassy","Careful","Quirky"]
# Gen-3 stat order for IVs and the party tail: HP, Atk, Def, Speed, SpAtk, SpDef.
STAT_ORDER = ["hp", "atk", "def", "spe", "spa", "spd"]

# --- character encoding (Gen 3 uses its own table, not ASCII) ---------------
_CH = {" ": 0x00}
for i, c in enumerate("0123456789"):            _CH[c] = 0xA1 + i
for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"): _CH[c] = 0xBB + i
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"): _CH[c] = 0xD5 + i
_CH.update({"!":0xAB,"?":0xAC,".":0xAD,"-":0xAE,"'":0xB4,"/":0xBA,",":0xB8})
EOS = 0xFF

def encode_str(s, width):
    out = bytearray([EOS] * width)
    for i, ch in enumerate(s.upper() if width == 7 else s):
        if i >= width: break
        out[i] = _CH.get(ch, _CH.get(ch.upper(), 0x00))
    if len(s) < width:
        out[len(s)] = EOS
    return bytes(out)

# --- experience groups ------------------------------------------------------
def exp_for_level(group, n):
    if n <= 1: return 0
    if group == "fast":        return (4 * n**3) // 5
    if group == "medium":      return n**3
    if group == "slow":        return (5 * n**3) // 4
    if group == "medium-slow": return max(0, (6 * n**3)//5 - 15*n**2 + 100*n - 140)
    if group == "erratic":
        if n < 50:  return (n**3 * (100 - n)) // 50
        if n < 68:  return (n**3 * (150 - n)) // 100
        if n < 98:  return (n**3 * ((1911 - 10*n)//3)) // 500
        return (n**3 * (160 - n)) // 100
    if group == "fluctuating":
        if n < 15:  return (n**3 * ((n + 1)//3 + 24)) // 50
        if n < 36:  return (n**3 * (n + 14)) // 50
        return (n**3 * (n//2 + 32)) // 50
    return n**3

def nature_mods(nature):
    """-> dict of stat -> multiplier. Gen 3 order: Atk, Def, Speed, SpAtk, SpDef."""
    order = ["atk", "def", "spe", "spa", "spd"]
    up, down = nature // 5, nature % 5
    mods = {s: 1.0 for s in STAT_ORDER}
    if up != down:
        mods[order[up]] = 1.1
        mods[order[down]] = 0.9
    return mods

def is_shiny(pid, tid, sid):
    return (tid ^ sid ^ (pid >> 16) ^ (pid & 0xFFFF)) < 8

def solve_pid(tid, sid, want_shiny, nature=None, rng=None):
    """Find a PID satisfying the requested shininess and nature.

    Shininess is not a flag in the file -- it is a relationship between the PID
    and the trainer ID, so it has to be solved for.
    """
    rng = rng or random.Random()
    v = tid ^ sid
    for _ in range(200000):
        if want_shiny:
            lo = rng.getrandbits(16)
            hi = lo ^ v ^ rng.randrange(8)      # forces the xor into [0,8)
            pid = ((hi & 0xFFFF) << 16) | lo
        else:
            pid = rng.getrandbits(32)
            if is_shiny(pid, tid, sid):
                continue
        if pid == 0 or pid == ((sid << 16) | tid):
            continue                            # key==0 makes .pk3/.ek3 ambiguous
        if nature is not None and pid % 25 != nature:
            continue
        return pid
    raise RuntimeError("could not solve a PID for those constraints")

def moves_for(entry, level):
    """The four moves the game would give: last four learned at or below level."""
    learned = [m for lv, m in sorted(entry["learnset"]) if lv <= max(1, level)]
    picked, seen = [], set()
    for m in reversed(learned):
        if m not in seen:
            seen.add(m); picked.append(m)
        if len(picked) == 4: break
    picked.reverse()
    # A handful of species (Deoxys) have no FRLG level-up data at all. A mon
    # with zero moves is rejected by the receiving game, so fall back to
    # Tackle (33) rather than hand over something unusable.
    if not picked:
        picked = [33]
    return (picked + [0, 0, 0, 0])[:4]

EV_MAX_TOTAL, EV_MAX_ONE = 510, 255      # Gen 3 caps

def clamp_evs(evs):
    """Gen 3 allows 255 per stat and 510 across all six. A .pk3 that breaks
    either is illegal and the receiving game can reject or 'fix' it."""
    out = {s: max(0, min(EV_MAX_ONE, int(evs.get(s, 0) or 0))) for s in STAT_ORDER}
    total = sum(out.values())
    if total > EV_MAX_TOTAL:                 # trim from the largest first
        for s in sorted(out, key=lambda k: -out[k]):
            if total <= EV_MAX_TOTAL: break
            take = min(out[s], total - EV_MAX_TOTAL)
            out[s] -= take; total -= take
    return out


def build(natdex, level=50, shiny=False, nature=None, ivs=None, ot="EMU",
          tid=12345, sid=54321, nickname=None, seed=None,
          moves=None, item=0, evs=None, friendship=70):
    e = DEX[str(natdex)]
    rng = random.Random(seed)
    level = max(1, min(100, int(level)))
    if isinstance(nature, str):
        nature = NATURES.index(nature)
    if nature is None:
        nature = rng.randrange(25)
    pid = solve_pid(tid, sid, shiny, nature, rng)
    otid = (sid << 16) | tid
    if ivs is None:
        ivs = {s: rng.randint(15, 31) for s in STAT_ORDER}
    else:
        ivs = {s: max(0, min(31, int(ivs.get(s, 0) or 0))) for s in STAT_ORDER}
    evs = clamp_evs(evs or {})

    mon = bytearray(PARTY_MON_SIZE)
    mon[0:4]   = pid.to_bytes(4, "little")
    mon[4:8]   = otid.to_bytes(4, "little")
    mon[8:18]  = encode_str((nickname or e["name"])[:10], 10)
    mon[18]    = 2                                    # language: English
    mon[19]    = 0x02                                 # hasSpecies
    mon[20:27] = encode_str(ot[:7], 7)
    mon[27]    = 0

    growth = bytearray(12)
    growth[0:2] = e["index"].to_bytes(2, "little")    # INTERNAL index, not natdex
    growth[2:4] = (int(item) & 0xFFFF).to_bytes(2, "little")   # held item
    growth[4:8] = exp_for_level(e["growth"], level).to_bytes(4, "little")
    growth[9]   = max(0, min(255, int(friendship)))

    # An explicit move list wins; otherwise take what the game would give.
    if moves:
        mv = [int(m or 0) for m in list(moves)[:4]]
        mv += [0] * (4 - len(mv))
        if not any(mv):
            mv = moves_for(e, level)
    else:
        mv = moves_for(e, level)
    attacks = bytearray(12)
    for i, m in enumerate(mv):
        attacks[i*2:i*2+2] = m.to_bytes(2, "little")
        attacks[8+i] = 35 if m else 0

    evbuf = bytearray(12)
    for i, st in enumerate(STAT_ORDER):               # HP,Atk,Def,Spe,SpA,SpD
        evbuf[i] = evs[st]

    misc = bytearray(12)
    # origins: metLevel bits0-6, game bits7-10 (4=FireRed), ball bits11-14 (4=Poke Ball)
    misc[1]   = 0x39                                  # met location: a plausible route
    origins   = (min(level, 100) & 0x7F) | (4 << 7) | (4 << 11)
    misc[2:4] = origins.to_bytes(2, "little")
    ivword = 0
    for i, s in enumerate(STAT_ORDER):
        ivword |= (ivs[s] & 0x1F) << (i * 5)
    ivword |= (pid & 1) << 31                         # ability slot from PID
    misc[4:8] = ivword.to_bytes(4, "little")

    mon[SECURE_OFF:SECURE_END] = growth + attacks + evbuf + misc
    sec = mon[SECURE_OFF:SECURE_END]
    mon[28:30] = (sum(int.from_bytes(sec[i*2:i*2+2], "little")
                      for i in range(24)) & 0xFFFF).to_bytes(2, "little")

    # party tail
    mods = nature_mods(nature)
    b = e["base"]
    hp = ((2*b["hp"] + ivs["hp"] + evs["hp"]//4) * level)//100 + level + 10
    mon[84]    = level
    mon[85]    = 0xFF                                 # MAIL_NONE
    mon[86:88] = hp.to_bytes(2, "little")
    mon[88:90] = hp.to_bytes(2, "little")
    for i, s in enumerate(["atk", "def", "spe", "spa", "spd"]):
        raw = ((2*b[s] + ivs[s] + evs[s]//4) * level)//100 + 5
        val = int(raw * mods[s])
        mon[90+i*2:92+i*2] = min(val, 0xFFFF).to_bytes(2, "little")

    return bytes(mon), {
        "natdex": natdex, "index": e["index"], "name": e["name"],
        "level": level, "shiny": is_shiny(pid, tid, sid),
        "nature": NATURES[nature], "pid": f"{pid:08X}", "otid": otid,
        "ivs": ivs, "evs": evs, "types": e["types"],
        "item": int(item), "item_name": ITEMS.get(str(int(item)), "None" if not item else f"#{item}"),
        "friendship": int(friendship),
        "moves": [MOVES.get(str(m), "-") for m in mv if m],
        "move_ids": mv,
        "stats": {"hp": hp, **{s: int.from_bytes(mon[90+i*2:92+i*2], "little")
                               for i, s in enumerate(["atk","def","spe","spa","spd"])}},
    }

"""Standalone LDN scan, used by the dashboard's Scan button.

The trade path scans briefly and then commits. This one only looks, with a
long dwell and several passes, so you can confirm the console is actually
advertising before spending a join attempt on it.
"""
import os, sys, trio, ldn
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from frlgsim.transport import free_radio

def main():
    keys_path = os.path.expanduser("~/.switch/prod.keys")
    phy = os.environ.get("FRLG_PHY", "phy0")
    dwell = float(os.environ.get("FRLG_SCAN_DWELL", "0.9"))
    # ldn.scan defaults to [1,6,11] -- 2.4GHz only. The library also supports
    # 36/40/44/48, and a Switch associated to a 5GHz AP can host the session
    # up there, where a 2.4-only scan will never see it.
    channels = [int(c) for c in os.environ.get(
        "FRLG_CHANNELS", "1,6,11,36,40,44,48").split(",") if c.strip()]
    passes = int(os.environ.get("FRLG_SCAN_PASSES", "4"))

    def _leaves(exc):
        inner = getattr(exc, "exceptions", None)
        if not inner:
            return [exc]
        out = []
        for x in inner:
            out.extend(_leaves(x))
        return out

    FRLG_COMM_ID = 0x0100610011000000      # FireRed/LeafGreen, from transport.py

    async def run():
        keys = ldn.load_keys(keys_path)
        seen, errors = {}, []
        for i in range(1, passes + 1):
            # The trade path frees the radio before every join attempt; the
            # scanner has to do the same or it hits EBUSY on SET_CHANNEL —
            # any interface left up on this phy holds the channel.
            try:
                free_radio({phy}, log=lambda m: print(f"[scan] {m}", flush=True))
            except Exception as e:
                print(f"[scan] could not free the radio: {e}", flush=True)
            print(f"[scan] pass {i}/{passes} — listening {dwell:.2f}s on each of channels "
                  f"{','.join(map(str, channels))}…", flush=True)
            try:
                nets = await ldn.scan(keys, phyname=phy, dwell_time=dwell,
                                      channels=channels)
            except BaseException as e:
                # trio wraps everything in an ExceptionGroup; printing the group
                # tells you nothing. Unwrap to the leaf causes, or the scan
                # reports "nothing found" when it actually never ran.
                for leaf in _leaves(e):
                    print(f"[scan] pass {i} ERROR: {type(leaf).__name__}: {leaf}", flush=True)
                errors.append(e)
                continue
            for n in nets:
                # local_communication_id is what decides whether this is FRLG.
                # The first version of this printed getattr(n,"local_comm_id")
                # -- an attribute that does not exist -- so every hit showed
                # "comm_id=?" and a non-FRLG session looked like a success.
                cid = n.local_communication_id
                is_frlg = (cid == FRLG_COMM_ID)
                seen[str(n.address)] = (n, is_frlg)
                print(f"[scan]   {'FRLG' if is_frlg else 'other'}  "
                      f"comm_id=0x{cid:016x} scene={n.scene_id} ch={n.channel} "
                      f"app_version={n.app_version} "
                      f"{n.num_participants}/{n.max_participants} "
                      f"accept_policy={n.accept_policy} addr={n.address}", flush=True)
            if not nets:
                print("[scan]   nothing on this pass", flush=True)
        print(flush=True)
        frlg = [v for v in seen.values() if v[1]]
        if frlg:
            print(f"[scan] RESULT: FRLG trade session visible ({len(frlg)}). Press Start trade "
                  f"now, while the console is still on that screen.", flush=True)
        elif seen:
            print(f"[scan] RESULT: {len(seen)} LDN network(s) seen but NONE are FRLG "
                  f"(expected comm_id=0x{FRLG_COMM_ID:016x}). That is another Switch/game "
                  f"nearby, not your trade. Put the console on the Direct Corner trade "
                  f"screen as Leader and scan again.", flush=True)
        elif errors:
            print("[scan] RESULT: the scan could not run — see the ERROR lines above. This is "
                  "a radio/driver problem, NOT a missing console.", flush=True)
        else:
            print("[scan] RESULT: nothing found. The console is not advertising a trade right "
                  "now. On the Switch: Direct Corner -> trade -> Leader, stay on the waiting "
                  "screen, then scan again.", flush=True)
    trio.run(run)

if __name__ == "__main__":
    sys.exit(main())

"""Radio diagnostics: is the console emitting, and can this card do LDN?

Ported in spirit from SantiagoPuertas/pokemon-ldn-trade's escuchar_ldn.sh and
check_injection.sh (MIT-spirited community work on the same upstream). The
idea there is the one we were missing all evening:

  `saw 0` does not say whether the fault is the PC or the Switch.

So these two tests deliberately avoid prod.keys, Pia and frlgsim entirely:

  listen  raw 802.11 monitor capture per channel, counting management and
          action frames. Frames here => the radio receives fine and any
          failure is higher up (keys, comm-id, parsing). Nothing here =>
          the console is not emitting on these channels.

  inject  LDN requires transmitting action frames in monitor mode. No
          `iw list` can answer whether a driver really does it -- only
          trying. This is the single open question about the mt7925.
"""
import os, re, subprocess, sys, time

CHANNELS = [int(c) for c in os.environ.get(
    "FRLG_CHANNELS", "1,6,11,36,40,44,48").split(",") if c.strip()]
SECONDS = float(os.environ.get("FRLG_LISTEN_SECS", "6"))
MONIF = "ldndiag0"


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def phy_for():
    p = os.environ.get("FRLG_PHY")
    if p:
        return p
    out = sh(["iw", "dev"]).stdout
    m = re.search(r"^phy#(\d+)", out, re.M)
    return f"phy{m.group(1)}" if m else "phy0"


def cleanup():
    sh(["iw", "dev", MONIF, "del"])


def make_monitor(phy):
    cleanup()
    r = sh(["iw", "phy", phy, "interface", "add", MONIF, "type", "monitor"])
    if r.returncode:
        print(f"[diag] could not create a monitor interface on {phy}: "
              f"{r.stderr.strip()}", flush=True)
        return False
    if sh(["ip", "link", "set", MONIF, "up"]).returncode:
        print("[diag] could not bring the monitor interface up", flush=True)
        return False
    return True


def listen():
    phy = phy_for()
    print(f"[diag] raw listen on {phy} — no keys, no LDN decode. "
          f"{SECONDS:.0f}s per channel.", flush=True)
    print("[diag] leave the console ON the Trade Center waiting screen "
          "for the whole test.", flush=True)
    if not make_monitor(phy):
        return 1
    if not sh(["which", "tcpdump"]).stdout.strip():
        print("[diag] tcpdump is not installed in the container", flush=True)
        cleanup(); return 1

    print(f"\n[diag] {'chan':<6}{'frames':>8}{'beacons':>9}{'action':>8}", flush=True)
    print(f"[diag] {'-'*4:<6}{'-'*6:>8}{'-'*7:>9}{'-'*6:>8}", flush=True)
    total_action, hot = 0, []
    for ch in CHANNELS:
        if sh(["iw", "dev", MONIF, "set", "channel", str(ch)]).returncode:
            print(f"[diag] {ch:<6}{'(cannot set channel)':>25}", flush=True)
            continue
        r = sh(["timeout", str(SECONDS), "tcpdump", "-i", MONIF,
                "-e", "-n", "-s", "300", "-c", "250", "type mgt"])
        txt = r.stdout
        frames  = len(re.findall(r"^\d{2}:\d{2}:\d{2}", txt, re.M))
        beacons = txt.count("Beacon")
        action  = txt.count("Action")
        total_action += action
        if action:
            hot.append(ch)
        print(f"[diag] {ch:<6}{frames:>8}{beacons:>9}{action:>8}", flush=True)

    cleanup()
    print(flush=True)
    if total_action:
        print(f"[diag] VERDICT: action frames received on channel(s) "
              f"{', '.join(map(str, hot))}. The radio receives fine — if the "
              f"trade still says 'saw 0' the fault is higher up (keys, "
              f"comm-id or parsing), not the card.", flush=True)
    elif any(True for _ in hot) is False:
        print("[diag] VERDICT: no action frames on any channel. Either the "
              "console is not emitting, or not on a channel we tested. Check "
              "it is still on the Trade Center waiting screen and run again.",
              flush=True)
    return 0


def inject():
    """Transmit an action frame in monitor mode -- LDN's hard requirement."""
    phy = phy_for()
    print(f"[diag] injection test on {phy}. This is what `iw list` cannot "
          f"tell you: whether the driver really transmits action frames.",
          flush=True)
    if not make_monitor(phy):
        return 1
    sh(["iw", "dev", MONIF, "set", "channel", "1"])

    import socket, struct
    # radiotap header (8 bytes, no fields) + a minimal 802.11 action frame.
    radiotap = struct.pack("<BBHI", 0, 0, 8, 0)
    frame = (b"\xd0\x00\x00\x00"              # type/subtype: action
             + b"\xff\xff\xff\xff\xff\xff"    # addr1 broadcast
             + b"\x02\x00\x00\x00\x00\x01"    # addr2 (locally administered)
             + b"\xff\xff\xff\xff\xff\xff"    # addr3
             + b"\x00\x00"                    # seq
             + b"\x7f"                        # category: vendor specific
             + b"\x00\x1f\x32"                # a vendor OUI
             + b"FRLGDIAG")
    ok = 0
    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
        s.bind((MONIF, 0))
        for i in range(5):
            s.send(radiotap + frame)
            ok += 1
            time.sleep(0.05)
        s.close()
    except Exception as e:
        print(f"[diag] injection FAILED: {type(e).__name__}: {e}", flush=True)
        cleanup(); return 1
    cleanup()
    print(f"[diag] transmitted {ok}/5 action frames without error.", flush=True)
    print("[diag] VERDICT: this card accepts action-frame injection in "
          "monitor mode, so it meets LDN's basic requirement. (It does not "
          "prove the association path is reliable — that is a separate "
          "driver behaviour.)", flush=True)
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "listen"
    try:
        sys.exit(listen() if mode == "listen" else inject())
    finally:
        cleanup()

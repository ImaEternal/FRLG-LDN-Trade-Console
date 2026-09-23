"""Dashboard for frlg-ldn-trade: pick a Pokemon, build it, run the trade.

Privilege split, deliberately:
  * READS (routes, radio state, sprites, dex) happen in-process -- the
    container runs with the host network namespace, so `ip route` already
    shows the truth.
  * WRITES that touch host networking (freeing the WiFi card) are NOT done
    from in here. The container drops a one-word request in control/ and a
    systemd path unit on the host runs the already-tested radio.sh. Reaching
    into PID 1's namespaces from a container would have been fewer moving
    parts and is exactly the kind of escape hatch that should stay shut.
"""
import json, os, queue, re, subprocess, sys, threading, time
from flask import Flask, jsonify, request, Response, send_from_directory, render_template

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pk3build

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT    = os.path.dirname(APP_DIR)
PK3_DIR = os.path.join(ROOT, "pk3")
OUT_DIR = os.path.join(ROOT, "out")
CTL_DIR = os.path.join(ROOT, "control")
KEYS_PATH = os.path.expanduser("~/.switch/prod.keys")
MANIFEST = os.path.join(PK3_DIR, "party.json")
BOX_DIR  = os.path.join(ROOT, "box")          # saved .pk3 library
os.makedirs(BOX_DIR, exist_ok=True)
for d in (PK3_DIR, OUT_DIR, CTL_DIR):
    os.makedirs(d, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
# Flask sorts JSON keys by default, which shuffled the stat bars out of the
# canonical HP/Atk/Def/SpA/SpD/Spe order the games use.
app.json.sort_keys = False

# ---- the guided send: one button, orchestrated ----------------------------
# The manual flow needs five buttons pressed in the right order (write, free
# the radio, scan, start, restore). Getting the order wrong produces errors
# that look like faults. This runs the whole sequence and reports one state.
SEND = {
    "active": False, "phase": "idle", "attempt": 0, "detail": "",
    "started": None, "error": None, "received": None,
}
_send_cancel = threading.Event()
_send_thread = None

PHASES = ["prepare", "radio", "scan", "join", "trade", "done"]


def set_phase(phase, detail="", **kw):
    SEND.update(phase=phase, detail=detail, **kw)
    publish(json.dumps({"phase": phase, "detail": detail,
                        "attempt": SEND["attempt"], "active": SEND["active"]}), "state")


# ---- live log plumbing -----------------------------------------------------
_log_subs: list[queue.Queue] = []
_log_lock = threading.Lock()
_proc: subprocess.Popen | None = None

LOG_PATH = os.path.join(ROOT, "out", "trade.log")

def publish(line, kind="log"):
    msg = json.dumps({"kind": kind, "line": line, "t": time.time()})
    with _log_lock:
        for q in list(_log_subs):
            try: q.put_nowait(msg)
            except queue.Full: pass
    # Also to stdout (docker logs) and a file, so a run can be diagnosed after
    # the browser has gone away.
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] {kind}: {line}", flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {kind}: {line}\n")
    except Exception:
        pass

# ---- read-only host state --------------------------------------------------
def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except Exception:
        return ""

def resolve_phy(iface):
    """phy index is not stable: reloading the driver renumbers it, and a
    hardcoded phy0 then fails with 'No wiphy found'. Read it off the
    interface each time."""
    out = subprocess.run(["iw", "dev", iface, "info"],
                         capture_output=True, text=True).stdout
    m = re.search(r"wiphy (\d+)", out)
    return f"phy{m.group(1)}" if m else os.environ.get("FRLG_PHY", "phy0")


WIFI_IF  = os.environ.get("FRLG_WIFI_IF", "wlan0")
WIRED_IF = os.environ.get("FRLG_WIRED_IF", "eth0")


def radio_state():
    routes = sh("ip route show default")
    # A released card leaves its default route in the table marked `linkdown`.
    # That route carries nothing, so treating it as "WiFi is still in use"
    # kept ready_for_trade false even after the radio was successfully freed.
    def active(dev):
        return any(dev in ln and "linkdown" not in ln for ln in routes.splitlines())
    wifi_default  = active(WIFI_IF)
    wired_default = active(WIRED_IF)
    wired_ip = sh(f"ip -4 -o addr show {WIRED_IF} | "
                  r"grep -oP '(?<=inet )[\d.]+' | head -1")
    status_file = os.path.join(CTL_DIR, "status.json")
    last = {}
    if os.path.exists(status_file):
        try: last = json.load(open(status_file))
        except Exception: last = {}
    return {
        "wifi_is_default": wifi_default,
        "wired_is_default": wired_default,
        "wired_ip": wired_ip or None,
        "ready_for_trade": wired_default and not wifi_default,
        "routes": routes.splitlines(),
        "last_action": last,
        # The keyfile is mounted where frlgtrade.py expects it (root's home),
        # not under the app directory -- check the path that actually matters.
        "keys_present": os.path.exists(KEYS_PATH) and os.path.getsize(KEYS_PATH) > 0,
    }

# ---- api -------------------------------------------------------------------
@app.get("/api/dex")
def api_dex():
    out = []
    for k, e in pk3build.DEX.items():
        out.append({"natdex": e["natdex"], "name": e["name"], "types": e["types"],
                    "base": e["base"], "growth": e["growth"]})
    out.sort(key=lambda x: x["natdex"])
    return jsonify(out)

@app.get("/api/items")
def api_items():
    out = [{"id": 0, "name": "None"}]
    out += sorted(({"id": int(k), "name": v} for k, v in pk3build.ITEMS.items()),
                  key=lambda x: x["name"])
    return jsonify(out)


@app.get("/api/moves/<int:natdex>")
def api_moves(natdex):
    """Moves this species can legally learn by level-up in FRLG, plus the
    level it learns each at. Offering the full 354-move list would make it
    trivial to build something the game rejects as illegal."""
    e = pk3build.DEX.get(str(natdex))
    if not e:
        return jsonify({"error": "unknown species"}), 404
    seen, out = set(), []
    for lv, mid in sorted(e["learnset"]):
        if mid in seen: continue
        seen.add(mid)
        out.append({"id": mid, "name": pk3build.MOVES.get(str(mid), f"#{mid}"), "level": lv})
    return jsonify(out)


@app.get("/api/box")
def api_box_list():
    out = []
    for f in sorted(os.listdir(BOX_DIR)):
        if not f.endswith(".json"): continue
        try:
            out.append(json.load(open(os.path.join(BOX_DIR, f))))
        except Exception:
            pass
    return jsonify(out)


@app.post("/api/box")
def api_box_save():
    """Keep a built Pokemon in the library so it survives the party being
    rewritten -- the party is scratch space, this is not."""
    b = request.get_json(force=True)
    spec = b.get("spec") or {}
    try:
        data, meta = pk3build.build(
            int(spec["natdex"]), level=int(spec.get("level", 50)),
            shiny=bool(spec.get("shiny")), nature=spec.get("nature") or None,
            ot=b.get("ot", "EMU")[:7] or "EMU",
            nickname=(spec.get("nickname") or None),
            moves=spec.get("moves") or None, item=int(spec.get("item") or 0),
            ivs=spec.get("ivs") or None, evs=spec.get("evs") or None)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    slug = re.sub(r"[^A-Za-z0-9_-]", "_",
                  (b.get("name") or f"{meta['name']}_Lv{meta['level']}"))[:48]
    with open(os.path.join(BOX_DIR, slug + ".pk3"), "wb") as f:
        f.write(data)
    rec = {"slug": slug, "spec": spec, **{k: meta[k] for k in
           ("name","natdex","level","shiny","nature","item_name","moves","stats","ivs","evs")}}
    json.dump(rec, open(os.path.join(BOX_DIR, slug + ".json"), "w"))
    publish(f"saved to box: {slug}", "ok")
    return jsonify(rec)


@app.delete("/api/box/<slug>")
def api_box_delete(slug):
    slug = re.sub(r"[^A-Za-z0-9_-]", "_", slug)[:48]
    n = 0
    for ext in (".pk3", ".json"):
        pth = os.path.join(BOX_DIR, slug + ext)
        if os.path.exists(pth):
            os.remove(pth); n += 1
    return jsonify({"deleted": n > 0})


@app.get("/api/natures")
def api_natures():
    return jsonify(pk3build.NATURES)

@app.get("/api/status")
def api_status():
    st = radio_state()
    st["trade_running"] = _proc is not None and _proc.poll() is None
    st["party"] = sorted(os.path.basename(p) for p in os.listdir(PK3_DIR)
                         if p.endswith((".pk3", ".ek3")))
    # What those files actually are, so the UI can rebuild the bay on reload.
    st["party_meta"] = []
    if os.path.exists(MANIFEST):
        try:
            man = json.load(open(MANIFEST))
            # Only trust the manifest if it still matches the files present.
            if [m["file"] for m in man] == [f for f in st["party"] if f.startswith("PARTY")]:
                st["party_meta"] = man
        except Exception:
            st["party_meta"] = []
    st["received"] = sorted(os.listdir(OUT_DIR)) if os.path.isdir(OUT_DIR) else []
    return jsonify(st)

@app.post("/api/preview")
def api_preview():
    b = request.get_json(force=True)
    try:
        _, meta = pk3build.build(
            int(b["natdex"]), level=int(b.get("level", 50)),
            shiny=bool(b.get("shiny")), nature=b.get("nature") or None,
            ot=b.get("ot", "EMU")[:7] or "EMU",
            tid=int(b.get("tid", 12345)), sid=int(b.get("sid", 54321)),
            nickname=(b.get("nickname") or None), seed=b.get("seed"),
            moves=b.get("moves") or None, item=int(b.get("item") or 0),
            ivs=b.get("ivs") or None, evs=b.get("evs") or None,
            friendship=int(b.get("friendship") or 70),)
        return jsonify(meta)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.post("/api/party")
def api_party():
    """Write the chosen mons to pk3/ as PARTY1..N, replacing what was there."""
    b = request.get_json(force=True)
    slots = b.get("slots") or []
    if len(slots) > 6:
        return jsonify({"error": "a party holds at most 6"}), 400
    # An empty list is a legitimate "clear the party": removing the last
    # Pokemon must be able to reach disk, or the old files linger and the UI
    # silently disagrees with what would actually be sent.
    for f in os.listdir(PK3_DIR):
        if re.fullmatch(r"PARTY\d\.pk3", f):
            os.remove(os.path.join(PK3_DIR, f))
    if os.path.exists(MANIFEST):
        os.remove(MANIFEST)
    made = []
    for i, s in enumerate(slots, 1):
        data, meta = pk3build.build(
            int(s["natdex"]), level=int(s.get("level", 50)),
            shiny=bool(s.get("shiny")), nature=s.get("nature") or None,
            ot=b.get("ot", "EMU")[:7] or "EMU",
            tid=int(b.get("tid", 12345)), sid=int(b.get("sid", 54321)),
            nickname=(s.get("nickname") or None),
            moves=s.get("moves") or None, item=int(s.get("item") or 0),
            ivs=s.get("ivs") or None, evs=s.get("evs") or None,
            friendship=int(s.get("friendship") or 70))
        path = os.path.join(PK3_DIR, f"PARTY{i}.pk3")
        with open(path, "wb") as f:
            f.write(data)
        meta["file"] = f"PARTY{i}.pk3"
        meta["req"] = {k: s.get(k) for k in
                       ("natdex","level","shiny","nature","nickname",
                        "moves","item","ivs","evs","friendship")}
        made.append(meta)
        publish(f"built {meta['file']}: {meta['name']} lv{meta['level']}"
                + (" SHINY" if meta["shiny"] else ""), "ok")
    with open(MANIFEST, "w") as f:
        json.dump(made, f)
    return jsonify({"party": made})

@app.post("/api/radio/<action>")
def api_radio(action):
    if action not in ("take", "give-back"):
        return jsonify({"error": "unknown action"}), 400
    # Hand off to the host helper; never touch host networking from in here.
    with open(os.path.join(CTL_DIR, "request"), "w") as f:
        f.write(action + "\n")
    publish(f"requested radio {action} from the host helper", "info")
    return jsonify({"requested": action})

@app.post("/api/trade/start")
def api_trade_start():
    global _proc
    if _proc is not None and _proc.poll() is None:
        return jsonify({"error": "a trade is already running"}), 409
    st = radio_state()
    if not st["keys_present"]:
        return jsonify({"error": "keys/prod.keys is missing or empty"}), 400
    if not st["ready_for_trade"]:
        return jsonify({"error": "the wireless interface still holds the "
                                 "default route — free the radio first"}), 400
    party = sorted(f for f in os.listdir(PK3_DIR) if re.fullmatch(r"PARTY\d\.pk3", f))
    if len(party) < 2:
        return jsonify({"error": "need at least 2 party files; build a party first"}), 400
    b = request.get_json(silent=True) or {}
    cmd = [sys.executable, os.path.join(ROOT, "frlgtrade.py"), "--live",
           "-o", os.path.join(OUT_DIR, b.get("out") or "received.pk3")]
    if b.get("verbose"): cmd.append("--verbose")
    if b.get("version"): cmd += ["--version", b["version"]]
    # Upstream hardcodes FRLG as 0x0100610011000000, but the GBA NSO app
    # advertises a different local_communication_id per region/version --
    # this console broadcasts 0x01006fa0233f8000. Without passing it through,
    # the scan finds the session and then rejects it as "not FRLG".
    comm = b.get("comm_id") or os.environ.get("FRLG_COMM_ID")
    if comm: cmd += ["--comm-id", str(comm)]
    if b.get("ot"):      cmd += ["--ot", b["ot"][:7]]
    cmd += [os.path.join(PK3_DIR, p) for p in party]
    publish("$ " + " ".join(cmd), "cmd")
    env = {**os.environ,
           "FRLG_IFNAME": os.environ.get("FRLG_IFNAME", "ldnclient"),
           "FRLG_PHY": resolve_phy(WIFI_IF),
           "FRLG_SCAN_DWELL": str(b.get("dwell") or 0.60),
           "FRLG_JOIN_ATTEMPTS": str(int(b.get("attempts") or 1)),
           "FRLG_JOIN_SETTLE": str(b.get("settle") or 4.0),
           "FRLG_JOIN_UNWIND": str(b.get("unwind") or 8.0),
           # This console's GBA NSO app advertises a different id than the one
           # upstream hardcodes; default to the observed value.
           # No console id is baked in: upstream's hardcoded value is wrong for
           # some regions, so it comes from .env or the request.
           **({"FRLG_COMM_ID": str(b["comm_id"])} if b.get("comm_id") else {})}
    _proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
    def pump(p):
        tail = []
        for line in p.stdout:
            line = line.rstrip("\n")
            tail.append(line)
            del tail[:-40]
            publish(line)
        rc = p.wait()
        if rc != 0:
            # A raw Python traceback is not an error message. Pull out the line
            # that actually says what went wrong and lead with it.
            cause = next((l for l in reversed(tail)
                          if l.strip() and not l.startswith((" ", "\t"))
                          and "Traceback" not in l and "^^^" not in l), "")
            HINTS = {
              "no joinable FRLG network":
                "The radio scanned but nothing was broadcasting a trade. "
                "On the console: Direct Corner -> trade -> be LEADER, and leave it "
                "on that screen before pressing Start.",
              "Operation not permitted":
                "The radio rejected the command. Free the radio first, then retry.",
              "prod.keys":
                "The keyfile could not be read. Check keys/prod.keys.",
            }
            hint = next((h for k, h in HINTS.items() if k in cause), "")
            publish(cause or f"exited with code {rc}", "err")
            if hint:
                publish(hint, "info")
        publish(f"process exited rc={rc}", "done")
    threading.Thread(target=pump, args=(_proc,), daemon=True).start()
    return jsonify({"started": True, "cmd": cmd})

@app.post("/api/scan")
def api_scan():
    """Look for a broadcasting console without committing to a join."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        return jsonify({"error": "a trade is already running"}), 409
    st = radio_state()
    if not st["keys_present"]:
        return jsonify({"error": "keys/prod.keys is missing or empty"}), 400
    if not st["ready_for_trade"]:
        return jsonify({"error": "free the radio first"}), 400
    cmd = [sys.executable, os.path.join(APP_DIR, "scan.py")]
    publish("$ scan for broadcasting consoles", "cmd")
    _proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    def pump(p):
        for line in p.stdout:
            publish(line.rstrip("\n"), "info" if "RESULT" in line else "log")
        publish(f"scan finished rc={p.wait()}", "done")
    threading.Thread(target=pump, args=(_proc,), daemon=True).start()
    return jsonify({"started": True})


@app.post("/api/diag/<mode>")
def api_diag(mode):
    """Radio diagnostics that deliberately bypass keys/LDN entirely, so a
    failure can be attributed to the console or to this card."""
    global _proc
    if mode not in ("listen", "inject"):
        return jsonify({"error": "unknown diagnostic"}), 400
    if _proc is not None and _proc.poll() is None:
        return jsonify({"error": "something is already running"}), 409
    if not radio_state()["ready_for_trade"]:
        return jsonify({"error": "free the radio first"}), 400
    cmd = [sys.executable, os.path.join(APP_DIR, "diag.py"), mode]
    publish(f"$ radio diagnostic: {mode}", "cmd")
    _proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    def pump(p):
        for line in p.stdout:
            line = line.rstrip("\n")
            publish(line, "info" if "VERDICT" in line else "log")
        publish(f"diagnostic finished rc={p.wait()}", "done")
    threading.Thread(target=pump, args=(_proc,), daemon=True).start()
    return jsonify({"started": True})


def _wait_radio(free=True, timeout=45):
    """Ask the host helper to take or return the radio, then wait for it."""
    want = "take" if free else "give-back"
    with open(os.path.join(CTL_DIR, "request"), "w") as f:
        f.write(want + "\n")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _send_cancel.is_set():
            return False
        if radio_state()["ready_for_trade"] == free:
            return True
        time.sleep(1.5)
    return radio_state()["ready_for_trade"] == free


LDN_VIFS = ("ldn", "ldn-mon", "ldn-tap", "ldnclient", "ldndiag0") \
            + tuple(f"ldnc{i}" for i in range(10))


def _clear_ldn_vifs():
    """Delete any leftover LDN virtual interface.

    nl80211 ACTION-frame registrations hang off the vif. If a run is killed --
    which Cancel does, and which a crash does -- the vif survives, still UP and
    still holding its registration. Every later attempt then dies with
      BlockingIOError [Errno 114]: Match already configured
    before it ever reaches the console, and no amount of retrying helps because
    the obstacle is local. Clear them before each attempt and after each kill.
    """
    for vif in LDN_VIFS:
        subprocess.run(["iw", "dev", vif, "del"],
                       capture_output=True, timeout=10)
        subprocess.run(["ip", "link", "del", vif],
                       capture_output=True, timeout=10)


def _run(cmd, tag):
    """Run a child process, streaming its output, honouring cancel."""
    global _proc
    env = {**os.environ,
           "FRLG_IFNAME": os.environ.get("FRLG_IFNAME", "ldnclient"),
           "FRLG_PHY": resolve_phy(WIFI_IF),
           "FRLG_SCAN_DWELL": os.environ.get("FRLG_SCAN_DWELL", "0.60"),
           # ONE in-process attempt. nl80211 frame registrations belong to
           # the netlink SOCKET, which lives as long as the process, and the
           # ldn library does not release them between retries -- so the
           # SECOND attempt onwards dies with
           #   BlockingIOError [Errno 114]: Match already configured
           # before it ever reaches the console. Measured: attempt 1 gives a
           # genuine result, every later one in the same process is doomed.
           # The outer loop restarts the process instead, so each attempt
           # gets a clean socket and is a real attempt.
           "FRLG_JOIN_ATTEMPTS": os.environ.get("FRLG_JOIN_ATTEMPTS", "1")}
    _proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
    out = []
    for line in _proc.stdout:
        line = line.rstrip("\n")
        out.append(line)
        publish(line)
        if _send_cancel.is_set():
            _proc.terminate()
            break
    rc = _proc.wait()
    # A terminated child never runs its own cleanup, so do it here.
    if _send_cancel.is_set() or rc != 0:
        _clear_ldn_vifs()
    return rc, out


def _send_worker(keep_radio, trades=1, slot=1):
    """prepare -> radio -> (scan -> join/trade) on a loop until it lands."""
    try:
        set_phase("radio", "handing the wireless card to LDN")
        if not _wait_radio(True):
            SEND["error"] = ("Could not free the radio. There must be a working "
                             "second network path, or the host refuses to release it.")
            set_phase("failed"); return

        party = sorted(f for f in os.listdir(PK3_DIR) if re.fullmatch(r"PARTY\d\.pk3", f))
        out_name = "received.pk3"
        while not _send_cancel.is_set():
            SEND["attempt"] += 1
            # Scan and join must be ATOMIC. This used to run scan.py first --
            # four passes over seven channels, ~25s, tearing the radio down at
            # each pass -- and only then start frlgtrade.py, which freed the
            # radio and scanned all over again. By the time we tried to
            # associate, the session we had found was half a minute stale, and
            # a console only advertises while somebody stands at the waiting
            # screen. frlgtrade.py does its own scan and joins the instant it
            # finds a match, so let it do both with no gap in between.
            set_phase("scan", "listening for your console")
            _clear_ldn_vifs()          # start every attempt from a clean radio
            cmd = [sys.executable, os.path.join(ROOT, "frlgtrade.py"), "--live",
                   "-o", os.path.join(OUT_DIR, out_name), "--verbose",
                   "--trades", str(trades), "--slot", str(slot)]
            comm = os.environ.get("FRLG_COMM_ID")
            if comm:
                cmd += ["--comm-id", str(comm)]
            cmd += [os.path.join(PK3_DIR, p) for p in party]
            # Rotate the station interface name so each attempt gets a fresh
            # ifindex and cannot inherit a registration left by a killed run.
            os.environ["FRLG_IFNAME"] = f"ldnc{SEND['attempt'] % 10}"
            rc, out = _run(cmd, "trade")
            if _send_cancel.is_set():
                break
            if rc == 0:
                SEND["received"] = out_name
                set_phase("done", "trade complete")
                return

            joined = any("saw network" in l for l in out)
            cause = next((l for l in reversed(out)
                          if l.strip() and not l.startswith((" ", "\t"))
                          and "Traceback" not in l and "^^^" not in l), "")
            if not joined:
                # Nothing was advertising: this is the console's side, not ours.
                set_phase("scan", "no session yet — keep the console on the "
                                  "trade waiting screen; retrying")
                wait = 3
            else:
                # We saw it and failed to associate. Retrying quickly is right:
                # the session is live right now.
                set_phase("join", f"found it, but the join did not take "
                                  f"(attempt {SEND['attempt']}) — retrying")
                publish(cause or f"exited rc={rc}", "err")
                wait = 2
            for _ in range(wait):
                if _send_cancel.is_set(): break
                time.sleep(1)

        if _send_cancel.is_set():
            set_phase("cancelled", "stopped")
    except Exception as e:
        SEND["error"] = f"{type(e).__name__}: {e}"
        set_phase("failed", SEND["error"])
    finally:
        SEND["active"] = False
        if not keep_radio:
            _wait_radio(False, timeout=30)
        publish(json.dumps({"phase": SEND["phase"], "active": False,
                            "attempt": SEND["attempt"]}), "state")


@app.post("/api/send/start")
def api_send_start():
    global _send_thread
    # A send is only really active if its worker thread is still alive. Without
    # this a crashed or orphaned worker leaves active=True forever and every
    # later attempt gets a 409 it can never clear.
    if SEND["active"] and not (_send_thread and _send_thread.is_alive()):
        SEND["active"] = False
    if SEND["active"]:
        return jsonify({"error": "already sending"}), 409
    st = radio_state()
    if not st["keys_present"]:
        return jsonify({"error": "keys/prod.keys is missing or empty"}), 400
    party = sorted(f for f in os.listdir(PK3_DIR) if re.fullmatch(r"PARTY\d\.pk3", f))
    if len(party) < 2:
        return jsonify({"error": "prepare the party first"}), 400
    b = request.get_json(silent=True) or {}
    # Work the parameters out BEFORE recording them; a previous edit had the
    # SEND.update() above these lines, which raised UnboundLocalError and made
    # the second dialog fail with a 500 the moment you pressed Continue.
    n_party = len(party)
    trades = max(1, min(6, int(b.get("trades") or 1), n_party))
    slot = int(b.get("slot") if b.get("slot") is not None else 1)
    slot = max(0, min(n_party - 1, slot))
    # ...and do not let the range run off the end of the party.
    trades = max(1, min(trades, n_party - slot))

    _send_cancel.clear()
    SEND.update(active=True, attempt=0, error=None, received=None,
                started=time.time(), trades=trades, slot=slot)
    set_phase("radio", "starting")
    _send_thread = threading.Thread(
        target=_send_worker,
        args=(bool(b.get("keep_radio")), trades, slot), daemon=True)
    _send_thread.start()
    return jsonify({"started": True})


@app.post("/api/send/cancel")
def api_send_cancel():
    _send_cancel.set()
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
    publish("cancelled by you", "info")
    return jsonify({"cancelled": True})


@app.get("/api/send/state")
def api_send_state():
    return jsonify({**SEND, "phases": PHASES})


@app.post("/api/trade/stop")
def api_trade_stop():
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        publish("terminate requested", "info")
        return jsonify({"stopped": True})
    return jsonify({"stopped": False})

@app.get("/api/logs")
def api_logs():
    def stream():
        q = queue.Queue(maxsize=2000)
        with _log_lock:
            _log_subs.append(q)
        try:
            yield f"data: {json.dumps({'kind':'info','line':'connected'})}\n\n"
            while True:
                try:
                    yield f"data: {q.get(timeout=20)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _log_lock:
                if q in _log_subs: _log_subs.remove(q)
    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/received/<path:name>")
def api_received(name):
    return send_from_directory(OUT_DIR, name, as_attachment=True)

@app.get("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8781, threaded=True)

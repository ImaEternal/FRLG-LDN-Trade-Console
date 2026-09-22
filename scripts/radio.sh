#!/usr/bin/env bash
# Hand the WiFi card to LDN, or give it back.
#
# THE RISK THIS MANAGES: on most machines the wireless interface IS the default
# route. LDN needs that card unmanaged, and the upstream README's advice ("just
# stop NetworkManager") would cut every remote session to the host with no way
# back in. So we move the machine onto a wired interface FIRST, prove the wire
# actually carries traffic, and only then release the radio. If there is no
# working second path, this refuses to proceed rather than strand you.
#
# Interfaces come from .env (see .env.example); nothing is hardcoded.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
[[ -f "$HERE/.env" ]] && . "$HERE/.env"
WIFI="${FRLG_WIFI_IF:-wlan0}"
WIRED_IF="${FRLG_WIRED_IF:-eth0}"
WIRED_CON="${FRLG_WIRED_CON:-frlg-wired}"
WIFI_CON="${FRLG_WIFI_CON:-}"
# Works both ways: run by hand as the agent user (sudo with the piped
# password) and run by systemd, which is already root and has no tty.
# Run as root (systemd does) or via sudo. No password is embedded anywhere:
# if sudo needs one it will ask on the terminal, and the systemd path is root
# already.
SUDO() { if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi; }

have_route_without_wifi() {
  ip route show default | grep -v "$WIFI" | grep -q default
}

case "${1:-}" in
  take)
    echo "==> bringing the wired link up as primary"
    SUDO nmcli connection modify "$WIRED_CON" ipv4.route-metric 50 connection.autoconnect yes
    SUDO nmcli connection up "$WIRED_CON" >/dev/null
    sleep 5
    # Observed 2026-09-22: NetworkManager can bring the link up, take a DHCP
    # lease WITH a gateway, and still install no routes at all -- leaving an
    # interface that has an IP but cannot route. `nmcli connection up` on an
    # already-active profile is the case that does it. A down/up cycle fixes
    # it, so verify rather than assume, and repair once before giving up.
    if ! ip route show default | grep -q "$WIRED_IF"; then
      echo "    wired link came up without a default route; re-applying"
      SUDO nmcli connection down "$WIRED_CON" >/dev/null 2>&1 || true
      sleep 2
      SUDO nmcli connection up "$WIRED_CON" >/dev/null
      sleep 5
    fi
    if ! have_route_without_wifi; then
      echo "!! no non-WiFi default route — REFUSING to free the radio" >&2
      echo "   (you would lose remote access to this machine)" >&2
      exit 1
    fi
    # Prove the wire actually carries traffic before trusting it.
    if ! curl -s --interface "$WIRED_IF" -o /dev/null --max-time 10 https://1.1.1.1; then
      echo "!! wired link has a route but no connectivity — REFUSING" >&2
      exit 1
    fi
    echo "    wired OK: $(ip -4 addr show "$WIRED_IF" | grep -oP '(?<=inet )[\d.]+' | head -1)"
    echo "==> releasing $WIFI to LDN"
    SUDO nmcli device set "$WIFI" managed no
    SUDO nmcli device disconnect "$WIFI" 2>/dev/null || true
    echo "    $WIFI is now unmanaged. Default route:"
    ip route show default | sed 's/^/    /'
    echo
    echo "Ready. Run a trade with:  ./run.sh --live -o out/received.pk3 pk3/A.pk3 pk3/B.pk3"
    ;;
  give-back)
    echo "==> returning $WIFI to NetworkManager"
    SUDO nmcli device set "$WIFI" managed yes
    sleep 4
    # Reconnect whatever profile was on the wireless interface. If the name
    # is not configured, let NetworkManager pick its own autoconnect.
    if [[ -n "$WIFI_CON" ]]; then
      SUDO nmcli connection up "$WIFI_CON" >/dev/null 2>&1 || true
    fi
    sleep 3
    echo "==> restoring the wire to standby (metric 500)"
    SUDO nmcli connection modify "$WIRED_CON" ipv4.route-metric 500 connection.autoconnect no
    SUDO nmcli connection up "$WIRED_CON" >/dev/null 2>&1 || true
    ip route show default | sed 's/^/    /'
    ;;
  status)
    echo "default routes:"; ip route show default | sed 's/^/    /'
    echo "$WIFI managed: $(nmcli -t -f GENERAL.STATE device show $WIFI 2>/dev/null | cut -d: -f2)"
    echo "wired: $(ip -4 addr show "$WIRED_IF" | grep -oP '(?<=inet )[\d.]+' | head -1 || echo none)"
    echo "tailscale: $(tailscale status --json 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["Online"])' 2>/dev/null || echo unknown)"
    ;;
  *)
    echo "usage: $0 {take|give-back|status}"
    echo "  take       move this box to ethernet, then free the WiFi card for LDN"
    echo "  give-back  return the WiFi card to normal networking"
    echo "  status     show what is currently routing"
    exit 1;;
esac

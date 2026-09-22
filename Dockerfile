# frlg-ldn-trade runtime.
#
# The project talks nl80211 over netlink to put a WiFi card into a raw mode and
# speak Nintendo's LDN local-wireless protocol. That means the container cannot
# be network-isolated: it needs the host's network namespace to see the phy at
# all, plus NET_ADMIN/NET_RAW to drive it. Docker here buys a clean, pinned
# Python environment -- not isolation.
#
# The host runs Python 3.14, which is newer than anything these pinned deps
# were tested against; 3.12 is what the project asks for, so that is what we
# give it. That alone is a good reason to containerise this.
FROM python:3.12-slim

# iw/iproute2 are for diagnosing the radio from inside the container, which is
# most of the work when a card will not cooperate.
# frlgsim/transport.py shells out to these on every join attempt. A missing
# binary is fatal (FileNotFoundError), not a soft failure -- `_run` passes
# check=False so it tolerates a command FAILING but not one being ABSENT.
#   iw, ip            - delete stale LDN vifs, bring interfaces down
#   nmcli             - take the adapter off NetworkManager
#   pkill (procps)    - clear a stray avahi-autoipd on the interface
#   sysctl (procps)   - per-interface kernel knobs
# network-manager here is the CLI only; no daemon runs in the container, and
# nmcli reaches the HOST's NetworkManager over the mounted D-Bus socket.
RUN apt-get update && apt-get install -y --no-install-recommends \
        iw iproute2 wireless-tools network-manager procps tcpdump ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so edits to the source do not bust the layer cache.
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt

# Upstream's engine is not vendored in git (AGPL-3.0, fetched by
# scripts/setup.sh). It is copied in at build time from vendor/.
COPY vendor/frlg-ldn-trade/frlgsim/ ./frlgsim/
COPY vendor/frlg-ldn-trade/frlgtrade.py .
COPY web/ ./web/
COPY data/ ./data/

# The script defaults to ~/.switch/prod.keys. Container runs as root (required
# for netlink), so root's home is where that has to land.
RUN mkdir -p /root/.switch

EXPOSE 8781
# Default to the dashboard; the trade CLI is still reachable via
#   docker compose run --rm --entrypoint python frlg frlgtrade.py ...
ENTRYPOINT ["python"]
CMD ["web/app.py"]

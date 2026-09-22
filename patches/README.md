# Patches against upstream

These change `tornadus/frlg-ldn-trade`, which is **AGPL-3.0**. They are
therefore themselves AGPL-3.0 — not EUPL-1.2 like the rest of this repository.
See [LICENSING.md](../LICENSING.md).

`scripts/setup.sh` clones upstream into `vendor/` and applies them.

## 0001-transport-scan-and-retry-fixes.patch

Four fixes to `frlgsim/transport.py`, all found by failing to join a real
console for an entire evening:

| change | why |
|---|---|
| scan dwell `0.11s` → `0.60s`, env-tunable | upstream listens for 330ms total across 3 channels. A console advertising a trade is trivially missed in that blink, and the failure surfaces as the unhelpful `no joinable FRLG network (saw 0)`. |
| channels `[1,6,11]` → all 7, env-tunable | the LDN library supports `36/40/44/48` too. A console associated to a 5GHz AP can host the session there, where a 2.4GHz-only scan will never see it. |
| join attempts env-tunable, retry teardown | 3 attempts over ~5s is a narrow window. Worse, the 2s unwind cap let an abandoned attempt overlap the next one, producing `BlockingIOError [Errno 114]: Match already configured` and runs that degraded as state piled up. Now: 8s unwind, 4s settle, and a full vif cleanup *before* the settle window so the driver can actually release. |
| "use the only joinable network" fallback is now opt-in (`FRLG_ANY_NETWORK=1`) | with any other Switch in range, this associated to a stranger's game and was rejected with status code 1 — eight confusing failures that look like a local bug. |

The comm-id itself is **not** patched: it is passed with upstream's existing
`--comm-id` flag, because the correct value varies by region and app version.

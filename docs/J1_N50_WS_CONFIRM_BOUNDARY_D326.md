# J1/D326 - Recovery after live WS boundary rejection

## Observed production facts, 13 November 2026 UTC

D322 root installer returned n50_ws_with_36h_rotation_enabled and activated
one private causal N50 epoch. The first WS lease began 02:59:31 and failed
03:00:00 with exit 65. Sanitized journal: ACK=1, zero confirmed rows,
invalid_or_gapped_market_data, 0 HTTP GET, 0 orders. The fallback service
completed at 03:00:02, disabled both WS/rotation timers and restored N2.
Original epoch and journal remain isolated. Never re-run D322 installer.

The failing data bytes were NOT recorded. Thus the first-frame cause is
not verified; in particular temporal rejection is a *hypothesis*, not a fact.

## Narrow correction and live diagnostic

Official Bybit WS kline contract: confirm=true means the bar is closed.
The local parser additionally required >=1 second after the boundary.
For a genuine confirmed event arriving at HH:00:00.xxx, this fails
despite server timestamp being after the closed UTC hour. New WS contract
accepts such receipts at/after end_ms+1 ONLY IF confirm is true, server
timestamp >=end_ms+1 and received_ms >=server_ms. Keep 120s max age,
actual receipt unchanged, immutable SQLite replay, integrity/UTC checks.
REST staging still uses its separate safety buffer. The full-hour
SQLite attestation still cannot occur before HH:00:01 and 24h/36h
proofs remain unchanged.

Supervisor classifies only exact predeclared internal validator messages
into allowlisted stages (envelope, row count, open/closed temporal, gap
or journal); all unknown exceptions become generic. Output never exposes
symbols, prices, provider payload or raw exception strings. Owner cached
report also carries frames_seen/preack_frames_discarded counters. This
makes the NEXT owner run diagnostic without extra repetitive REST calls.

## Gates

tests/test_j1_n50_ws_confirm_boundary_d326.py covers exact and subsecond
closed receipts, time authenticity, negative preclose/future/stale/open
cases, SQLite replay, allowlisted diagnostics and post-ACK rejection.
Regress D313/D315/D317/D323/D324/D325. CI Linux/docs,
Windows/offline and PAPER on exact SHA. Merge without production.
A separately authorized root recovery with N2 rollback is required
before re-enabling existing D322 units; never attempt another full
bootstrap of 372 rank GETs. No real orders, signals, marketwide claim.

## Controlled root recovery, code prepared but NOT executed

After merging D326 with all three CI gates, the operator may use the
version-pinned root script deploy/vps/recover_j1_n50_ws_d326_once.sh
on srv1319424. It refuses any other host, old checkout SHA, dirty
owner code, wrong systemd state, or stale private D321 active pointer.
The script fetches the *exact new reviewed SHA* into the existing
owner-only D322 checkout, verifies offline tests with the VPS Python,
and **only then** re-enables the already-installed WS/rotation timers.
If a cutover step fails or the shell exits unexpectedly, it restores
N2. No new D286 ranking bootstrap, metadata GET, unit overwrite,
SQLite migration, credentials, trade or timer installed from scratch.
It does NOT prove the root hypothesis; the next WS lease output
still must be inspected. Keep REST N2 active until a separate
operator-root execution intentionally transitions.

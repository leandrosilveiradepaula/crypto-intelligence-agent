# J1/OPS6 - Off-by-default owner WS service supervision and private health

**Issue:** #429. **Research only:** Bybit V5 linear perpetuals. **Deployment:** NOT performed. **Orders sent:** zero. **Additional spend:** zero.

## What this changes

The OPS4/OPS5 pilot already supports a finite owner-operated public WebSocket session, locally reviewed catalog snapshots, separate SQLite WS journaling and a single-writer file lease. This work adds the *service boundary*, not a new collector. The private historical REST database from EXIT5 is never read or modified by these components.

- `scripts.run_j1_ws_service` is an explicit-flag, owner-only, single finite WS lease. Its default runtime is 3300 seconds (under the supervisor's hard limit of one hour). The script does not schedule itself, activate a service, query historical REST klines or place orders.
- Stable **exit statuses** tell a service manager what can be restarted. `0`: finite lease completed with a warming/limited research status; this is **not** proof of marketwide Top50 or live readiness. `75`: bounded transport interruption, eligible for a controlled restart. `64`: invalid configuration; `65`: provider denial/rate limit including `10006`; `66`: journal/integrity/unknown status; `77`: missing explicit owner permission or unsupported owner. Codes `64/65/66/77` must never be automatically restarted. `130`: operator interruption, also excluded from automatic restart.
- `deploy/systemd/cia-j1-ws-owner.service.template` is inert source text. It uses a non-root named owner, `ProtectSystem=strict`, an independently provisioned private read/write directory, an unprivileged Python executable, no credentials and no private API access. It has a capped restart policy, a delayed restart for transient faults and `RestartPreventExitStatus=64 65 66 77 130`. The template intentionally includes **no installation command**.
- `scripts.render_j1_ws_service` accepts explicit username, repository root, Python executable and private directory and **prints** the rendered unit. It does not write under `/etc`, call `systemctl` or inspect the VPS. Invalid usernames/paths and private data directories inside the public repository are refused. The owner must decide when deployment gates are satisfied.
- `crypto_intelligence_agent.j1_ws_service_health` and `scripts.read_j1_ws_service_health` read one last-observation file only. They validate POSIX owner, `0700/0600`, regular file, inode, bounded JSON and accepted research statuses. Fresh health always says `worker_running_verified=false`, because a last observation does not prove the process is still running. Files older than two hours are marked stale; missing, future, unsafe, malformed, symlinked or hardlinked files abstain. No SQLite, `/proc`, connection, credential, PID or symbolic price/turnover is exposed.

## Owner-operated activation gate - NOT SATISFIED

Before the prepared unit can be installed or enabled, separately verify the actual VPS identity, exact Git SHA, unit renderer output, owner account permissions, private directory mode, backup of the original REST DB, reachable public WS endpoint, Bybit's multi-subscription ACK correlation, region, expected topic quota and the complete eligible candidate scope. A release/activation subject to a production gate needs the Product Owner's authorization; a CI green state alone cannot authorize activation.

**Never** copy or migrate REST candles into the WS journal without an independently reviewed, provenance-preserving import. A new WS journal normally needs 24 *closed* hourly candles for every reviewed candidate before the local ranking can be marked complete. If a disconnect loses a close, the journal must abstain; no REST retry loop and no synthetic PIT are authorized. The future gap reconciler must implement separate quota and provenance gates.

An owner-enabled service may cycle finite leases using systemd's `Restart=always` with a 30-second delay and a limit of six starts per hour; this does not guarantee zero dropped candles during a restart. The collector's existing strictly sequenced journal will detect gaps, while strategy/ranking outputs remain fail-closed. The service manager is the source for actual process state; the last-observation JSON is only historical telemetry.

## Acceptance matrix

Run the new dedicated offline tests plus the full GitHub Actions matrix. Cases include positive and negative opt-ins, non-root guard, malicious paths, template escaping, no accidental installation, quota code `10006` versus transient transport, failure sanitization, missing/stale/future status, corrupted JSON, insecure permissions, symlink/hardlink and unverified uptime flags. Verify the generated unit grammar with a local `systemd-analyze verify` when the tool is present, without loading it into a running service manager. Record the exact CI SHA, review and post-merge checks.

## Limits and next authorized engineering task

This increment is a **deployable but not deployed** service blueprint, with a bounded CLI and last-report monitor. It is not evidence of 24/7 operation, a marketwide Top50, WS provider acceptance, a safe REST backfill, profitable strategies or real trading. Next: a separately gated owner-only real WS pilot with authenticated transport evidence and live multi-topic ACK; instrument coverage #319; then controlled service activation and one-day soak with hourly continuity and gap monitoring. No VPS operation or new market request is part of OPS6.

## Atualização OPS9 — capacidade do lease (01/11/2026)

O template systemd permanece off-by-default. O adaptador de serviço deixa de aceitar implicitamente o orçamento de 4.096 frames do piloto e configura `52 * seconds + 4096` (175.696 para 3.300s) em um teto global 200.000. Estouro **antes** do fim normal produz abstenção categórica e exit 66, protegido por `RestartPreventExitStatus`. Evidências adicionais em `docs/J1_OPS9_HOURLY_FRAME_BUDGET.md` (D217). Isso não é demonstração de operação 24/7 na VPS.

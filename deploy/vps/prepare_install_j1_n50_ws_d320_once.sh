#!/usr/bin/env bash
# J1/D320. One root invocation: pinned owner checkout, fresh D287 snapshot,
# D314 metadata receipt/cache, then reversible N2 -> N50 WS timer cutover.
# Do not run through the restricted MCP broker: it lacks owner DAC/capabilities.
set -euo pipefail
umask 077

OWNER=cia-probe
HOST=srv1319424
ORIGIN=https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git
PY=/home/cia-probe/agent/ws-venv/bin/python
BASE=/home/cia-probe/agent
SHA="${1:-}"

if [[ "$(id -u)" != 0 || "$(hostname)" != "$HOST" ]]; then
  echo "preflight_blocked: expected operator root on $HOST" >&2
  exit 77
fi
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "preflight_blocked: exact reviewed main SHA required" >&2
  exit 77
fi
if [[ "$(/usr/bin/timedatectl show --property=NTPSynchronized --value)" != yes ]]; then
  echo "preflight_blocked: NTP unsynchronized" >&2
  exit 77
fi
test -x "$PY"
test -d "$BASE"
test ! -L "$BASE"
OWNER_GROUP="$(/usr/bin/id -gn "$OWNER")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SHORT="${SHA:0:12}"
CODE="$BASE/j1-n50-ws-${SHORT}-code-${STAMP}"
MANIFEST="$BASE/j1-n50-ws-manifest-${STAMP}"
WS_DIR="$BASE/j1-n50-ws-private-${STAMP}"
for d in "$CODE" "$MANIFEST" "$WS_DIR"; do
  if [[ -e "$d" || -L "$d" ]]; then
    echo "preflight_blocked: owner staging collision" >&2
    exit 77
  fi
done

# Before touching any private data: old REST N50 must be disabled and N2
# must remain enabled. All systemd changes occur only at the final release.
test "$(/usr/bin/systemctl is-enabled cia-j1-n50-managed.timer)" = disabled
test "$(/usr/bin/systemctl is-active cia-j1-n50-managed.timer)" = inactive
test "$(/usr/bin/systemctl is-enabled cia-j1-rest-hourly.timer)" = enabled
test "$(/usr/bin/systemctl is-active cia-j1-rest-hourly.timer)" = active

echo "STAGE_1_CHECKOUT_PINNED_OWNER"
# Clone as private owner, never overwrite historical old REST worktree.
# Fetch the exact SHA explicitly even if main has since advanced.
 /usr/sbin/runuser -u "$OWNER" -- /usr/bin/git clone \
  --quiet --no-checkout --depth 1 "$ORIGIN" "$CODE"
/usr/sbin/runuser -u "$OWNER" -- /usr/bin/git -C "$CODE" \
  fetch --quiet --no-tags --depth 1 origin "$SHA"
/usr/sbin/runuser -u "$OWNER" -- /usr/bin/git -C "$CODE" \
  checkout --quiet --detach "$SHA"
test "$(/usr/sbin/runuser -u "$OWNER" -- /usr/bin/git -C "$CODE" rev-parse HEAD)" = "$SHA"
test -z "$(/usr/sbin/runuser -u "$OWNER" -- /usr/bin/git -C "$CODE" status --porcelain)"
test "$(/usr/sbin/runuser -u "$OWNER" -- /usr/bin/git -C "$CODE" remote get-url origin)" = "$ORIGIN"
test "$(stat -c '%a' "$CODE")" = 700

/usr/bin/install -d -o "$OWNER" -g "$OWNER_GROUP" -m 0700 "$MANIFEST" "$WS_DIR"
test "$(stat -c '%a' "$MANIFEST")" = 700
test "$(stat -c '%a' "$WS_DIR")" = 700
cd "$CODE"

# D287 current 24h ranking is only causal during the first 15m after an
# hourly close. Begin only at HH:02:15..HH:02:30, after the usual N2
# HH:02 run is finished, leaving ~12m30s for the D287 catalogue.
# Waiting happens inside the operator's one-shot process.
NOW="$(date -u +%s)"
PHASE="$((NOW % 3600))"
if (( PHASE < 135 )); then
  WAIT="$((135 - PHASE))"
elif (( PHASE <= 150 )); then
  WAIT=0
else
  WAIT="$((3735 - PHASE))"
fi
if (( WAIT > 0 )); then
  echo "STAGE_2_WAITING_FOR_CAUSAL_UTC_CENSUS_WINDOW"
  /usr/bin/sleep "$WAIT"
fi

# Refuse to compete with an unusually long-running N2 hourly cycle.
# Failing here preserves the healthy N2 timer without new network requests.
test "$(/usr/bin/systemctl is-active cia-j1-rest-hourly.service)" = inactive
echo "STAGE_3_CAPTURE_FRESH_D287_50"
# The bounded rank may issue public GETs; any 10006/error halts here with N2
# unchanged and no new WS unit installed. Do not retry the failed epoch.
/usr/bin/timeout --signal=TERM --kill-after=10s 1350s \
  /usr/sbin/runuser -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m scripts.run_j1_current_ranked_epoch_once capture-seal \
  --manifest-directory "$MANIFEST" \
  --allow-public-network \
  --confirm-region-and-personal-research \
  --allow-private-manifest-write

echo "STAGE_4_CACHE_D314_OWNER_METADATA"
# D314 metadata requires the SAME fresh D287 cohort. No hourly metadata
# recapture: D316 persists source pages once in the private WS epoch.
/usr/bin/timeout --signal=TERM --kill-after=10s 180s \
  /usr/sbin/runuser -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m scripts.cache_j1_n50_ws_metadata_owner_once \
  --manifest-directory "$MANIFEST" --ws-directory "$WS_DIR" \
  --allow-public-network \
  --confirm-region-and-personal-research \
  --enable-n50-ws-metadata-capture \
  --allow-private-manifest-read \
  --allow-private-ws-cache-write

echo "STAGE_5_ROOT_CUTOVER_WITH_FAILBACK"
# Read-only preflight and actual install/cutover happen in the same
# SHA-pinned root module; errors restore N2 if isolation already began.
PYTHONDONTWRITEBYTECODE=1 "$PY" -m scripts.release_j1_n50_ws_owner_once \
  --source "$CODE" --expected-sha "$SHA" \
  --manifest "$MANIFEST" --ws-dir "$WS_DIR" \
  --confirm-n50-ws-cutover --allow-systemd-modifications

echo "N50_WS_INSTALLER_DONE: units on disk and new timer enabled; no trades"

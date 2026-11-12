#!/usr/bin/env bash
# J1/D322: install N50 WS + automatic >=36h epoch rotation in ONE root run.
# No execution via restricted MCP, no orders, no REST HALT mutation.
set -euo pipefail
umask 077

OWNER=cia-probe
HOST=srv1319424
ORIGIN=https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git
BASE=/home/cia-probe/agent
PY="$BASE/ws-venv/bin/python"
EPOCH="$BASE/j1-n50-ws-epochs"
STATE="$EPOCH/active"
SHA="${1:-}"

if [[ "$(id -u)" != 0 || "$(hostname)" != "$HOST" ]]; then
  echo "blocked: expected operator root on srv1319424" >&2
  exit 77
fi
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "blocked: reviewed full SHA40 required" >&2
  exit 77
fi
test "$(/usr/bin/timedatectl show --property=NTPSynchronized --value)" = yes
test -x "$PY"
test -d "$BASE"
test ! -L "$BASE"
test ! -e "$EPOCH"
test ! -L "$EPOCH"
test "$(/usr/bin/systemctl is-enabled cia-j1-rest-hourly.timer)" = enabled
test "$(/usr/bin/systemctl is-active cia-j1-rest-hourly.timer)" = active
test "$(/usr/bin/systemctl is-enabled cia-j1-n50-managed.timer)" = disabled
test "$(/usr/bin/systemctl is-active cia-j1-n50-managed.timer)" = inactive
test "$(/usr/bin/systemctl show cia-j1-n50-ws.timer --property=LoadState --value)" = not-found
test "$(/usr/bin/systemctl show cia-j1-n50-ws-rotate.timer --property=LoadState --value)" = not-found

OWNER_GROUP="$(id -gn "$OWNER")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
CODE="$BASE/j1-n50-ws-${SHA:0:12}-code-$STAMP"
test ! -e "$CODE"
test ! -L "$CODE"
echo "D322_STAGE_1_CHECKOUT_OWNER_PINNED"

# Never alter D306 source or the old N50 REST data.
# Keep the new repo, manifest, metadata, pointer and WS journal owner-only.
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

/usr/bin/install -d -o "$OWNER" -g "$OWNER_GROUP" -m 0700 "$EPOCH" "$STATE"
test "$(stat -c '%a' "$EPOCH")" = 700
test "$(stat -c '%a' "$STATE")" = 700
cd "$CODE"

# D286 MUST start between HH:01:00 and HH:02:00 UTC; never use D320 HH:02:15.
# A narrow 01:15..01:30 owner attempt ensures enough remaining 15m budget.
NOW="$(date -u +%s)"
PHASE="$((NOW % 3600))"
if (( PHASE < 75 )); then
  WAIT="$((75 - PHASE))"
elif (( PHASE <= 90 )); then
  WAIT=0
else
  WAIT="$((3675 - PHASE))"
fi
if (( WAIT > 0 )); then
  echo "D322_STAGE_2_WAIT_FOR_D286_CAUSAL_RANK_WINDOW"
  /usr/bin/sleep "$WAIT"
fi

# A long-running N2 REST cycle at the boundary must not be disturbed.
test "$(/usr/bin/systemctl is-active cia-j1-rest-hourly.service)" = inactive
test "$(/usr/bin/systemctl is-active cia-j1-rest-hourly.timer)" = active
echo "D322_STAGE_3_CAPTURE_RANK_METADATA_AND_ATOMIC_INITIAL_POINTER"

# Bootstrap with D321 owner rotator, which has its own time/GET/owner gates:
# claim is written BEFORE the first request and 10006 is never retried.
# Any failure leaves N2 enabled and the old N50 REST journal untouched.
/usr/bin/timeout --signal=TERM --kill-after=10s 1350s \
  /usr/sbin/runuser -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m scripts.rotate_j1_n50_ws_epoch_once \
  --state-directory "$STATE" --epoch-root "$EPOCH" \
  --allow-private-rotation --allow-public-network \
  --confirm-region-and-personal-research \
  --allow-private-manifest-write --allow-private-ws-cache-write

echo "D322_STAGE_4_RELEASE_ROTATING_WS_WITH_FAILBACK"
# Separate explicit root gate: five new units only, no overwrite or orders.
# No systemd mutation before this point. Partial cutover restores N2.
PYTHONDONTWRITEBYTECODE=1 "$PY" -m scripts.release_j1_n50_ws_rotating_once \
  --source "$CODE" --expected-sha "$SHA" \
  --state-directory "$STATE" --epoch-root "$EPOCH" \
  --confirm-rotating-ws-cutover --allow-systemd-modifications

echo "D322_RELEASE_STARTED: WS preclose and >=36h rotation timers active; no orders"

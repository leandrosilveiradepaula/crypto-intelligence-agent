#!/usr/bin/env bash
# D439: host-only preflight and finite public research. NO J1 writes or orders.
set -euo pipefail
umask 077
test "$#" -eq 2 || { echo 'D439_BLOCKED=ARGUMENTS'; exit 77; }
MODE="$1"
SHA="$2"
OWNER=cia-probe
HOST=srv1319424
BASE=/home/cia-probe/agent
STATE="$BASE/j1-n50-ws-epochs/active"
REPO="$BASE/repo"
PY="$BASE/ws-venv/bin/python"
RUNUSER=/usr/sbin/runuser
GIT=/usr/bin/git
TIMEOUT=/usr/bin/timeout
ORIGIN=https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git

fail() { printf 'D439_BLOCKED=%s\n' "$1"; exit 77; }
case "$MODE" in --preflight|--capture) ;; *) fail MODE ;; esac
[[ "$SHA" =~ ^[a-f0-9]{40}$ ]] || fail SHA
test "$(/usr/bin/id -u)" = 0 || fail ROOT_HOST_REQUIRED
test "$(/usr/bin/hostname)" = "$HOST" || fail WRONG_HOST
test -x "$RUNUSER" && test -x "$GIT" && test -x "$TIMEOUT" || fail HOST_DEPENDENCIES
test -x "$PY" || fail VENV_MISSING
test -d "$BASE" && test ! -L "$BASE" || fail OWNER_BASE
test -d "$STATE" && test ! -L "$STATE" || fail J1_OWNER_STATE
test -d "$REPO" && test ! -L "$REPO" || fail OWNER_REPO
test "$(/usr/bin/id -u "$OWNER")" -gt 0 || fail OWNER_ID
"$RUNUSER" -u "$OWNER" -- /usr/bin/test -d "$STATE" >/dev/null 2>&1 || fail OWNER_DAC
"$RUNUSER" -u "$OWNER" -- /usr/bin/id -u >/dev/null 2>&1 || fail OWNER_SWITCH
test "$(/usr/bin/timedatectl show -p NTPSynchronized --value 2>/dev/null)" = yes || fail CLOCK_NTP
"$RUNUSER" -u "$OWNER" -- "$PY" -c 'import websockets.sync.client' >/dev/null 2>&1 || fail WEBSSOCKETS_LIBRARY
# This checks the existing private J1 pointer without modifying it or using network.
"$RUNUSER" -u "$OWNER" -- /usr/bin/env PYTHONPATH="$REPO" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 "$PY" -c '
import time
from pathlib import Path
from crypto_intelligence_agent.j1_n50_ws_epoch_rotation import load_active_n50_ws_epoch
s = load_active_n50_ws_epoch(
    state_directory=Path("/home/cia-probe/agent/j1-n50-ws-epochs/active"),
    current_at_ms=time.time_ns() // 1000000,
    allow_private_pointer_read=True)
assert s.status == "active_n50_ws_epoch_revalidated"
' >/dev/null 2>&1 || fail OWNER_J1_EPOCH_REVALIDATION

printf 'D439_HOST_PREFLIGHT=PASS_NO_NETWORK_NO_WRITES\n'
printf 'D439_EXPECTED_SHA=%s\n' "$SHA"
if test "$MODE" = --preflight; then
    printf 'D439_PUBLIC_WS=NOT_STARTED\n'
    exit 0
fi

# Operator, not the program, must check applicable terms and region.
test "${CIA_D439_CONFIRM_PERSONAL_RESEARCH:-}" = YES || fail PERSONAL_RESEARCH_NOT_CONFIRMED
test "${CIA_D439_CONFIRM_REGION_ELIGIBLE:-}" = YES || fail REGION_NOT_CONFIRMED
test "${CIA_D439_CONFIRM_DATA_RIGHTS:-}" = YES || fail RIGHTS_NOT_CONFIRMED
test "${CIA_D439_CONFIRM_PUBLIC_WS:-}" = YES || fail PUBLIC_WS_NOT_CONFIRMED

# Never write into the active J1 repo/epoch; owner-only new evidence directory.
WORK="$("$RUNUSER" -u "$OWNER" -- /usr/bin/mktemp -d "$BASE/j2-d439-public-XXXXXXXX")" || fail OWNER_WORK
test -d "$WORK" && test ! -L "$WORK" || fail WORK_DIR
test "$(/usr/bin/stat -c '%U:%a' "$WORK")" = "$OWNER:700" || fail WORK_DAC
CODE="$WORK/code"
OUT="$WORK/observations"
"$RUNUSER" -u "$OWNER" -- /usr/bin/install -d -m 0700 "$OUT" || fail OUT_DAC
# Immutable SHA fetch; do not git pull in the operating J1 checkout.
"$TIMEOUT" 120 "$RUNUSER" -u "$OWNER" -- "$GIT" clone \
    --quiet --no-checkout --depth 1 "$ORIGIN" "$CODE" >/dev/null 2>&1 || fail CLONE
"$TIMEOUT" 120 "$RUNUSER" -u "$OWNER" -- "$GIT" -C "$CODE" fetch \
    --quiet --no-tags --depth 1 origin "$SHA" >/dev/null 2>&1 || fail FETCH
test "$("$RUNUSER" -u "$OWNER" -- "$GIT" -C "$CODE" rev-parse FETCH_HEAD)" = "$SHA" || fail FETCH_SHA
"$RUNUSER" -u "$OWNER" -- "$GIT" -C "$CODE" checkout --quiet --detach "$SHA" \
    >/dev/null 2>&1 || fail CHECKOUT
test "$("$RUNUSER" -u "$OWNER" -- "$GIT" -C "$CODE" rev-parse HEAD)" = "$SHA" || fail CHECKOUT_SHA
test -z "$("$RUNUSER" -u "$OWNER" -- "$GIT" -C "$CODE" status --porcelain)" || fail DIRTY
test -f "$CODE/scripts/run_j2_public_kline_session_d437_once.py" || fail D437_MISSING
test -f "$CODE/crypto_intelligence_agent/j2_current_owner_kline_scope_d438.py" || fail D438_MISSING
# Fail before opening WSS unless the current J1 N50 is valid at this instant.
"$RUNUSER" -u "$OWNER" -- /usr/bin/env PYTHONPATH="$CODE" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 "$PY" -c '
import time
from pathlib import Path
from crypto_intelligence_agent.j2_current_owner_kline_scope_d438 import read_current_owner_n50_kline_scope
scope = read_current_owner_n50_kline_scope(
    state_directory=Path("/home/cia-probe/agent/j1-n50-ws-epochs/active"),
    now_ms=time.time_ns() // 1000000,
    allow_private_pointer_read=True)
assert len(scope.contracts) == 50
' >/dev/null 2>&1 || fail CURRENT_N50_UNAVAILABLE

printf 'D439_OWNER_N50_SCOPE=REVALIDATED_PROVISIONAL\n'
printf 'D439_PUBLIC_WS=STARTED_FINITE_READONLY\n'
set +e
RAW="$("$TIMEOUT" 300 "$RUNUSER" -u "$OWNER" -- /usr/bin/env \
    PYTHONPATH="$CODE" PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    "$PY" -m scripts.run_j2_public_kline_session_d437_once \
    --state-directory "$STATE" --output-dir "$OUT" \
    --max-seconds 240 --max-frames 24000 \
    --allow-private-pointer-read --allow-public-network --allow-public-websocket \
    --confirm-personal-readonly-research --confirm-region-eligible 2>/dev/null)"
RC="$?"
set -e
if test "$RC" != 0 && test "$RC" != 2; then
    printf 'D439_PUBLIC_RESULT=ABSTAINED_EXIT_%s\n' "$RC"
    exit 65
fi
test -n "$RAW" && test "${#RAW}" -le 16000 || fail REPORT_MISSING
D439_PRIVATE_JSON="$RAW" /usr/bin/python3 - <<'PY' || fail REPORT_INVALID
import json, os, re
def unique(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("duplicate")
        d[k] = v
    return d
v = json.loads(os.environ["D439_PRIVATE_JSON"], object_pairs_hook=unique)
status = v.get("status")
if (type(v) is not dict or type(status) is not str
        or not re.fullmatch(r"[a-z0-9_]{1,90}", status)
        or v.get("orders_sent") is not False
        or v.get("approved_for_signals") not in (None, False)):
    raise ValueError("unsafe output")
s = v.get("session")
if type(s) is not dict:
    s = {}
for key in ("subscriptions_acknowledged", "closed_events_appended", "open_updates"):
    n = s.get(key, 0)
    if type(n) is not int or not 0 <= n <= 1000000:
        raise ValueError("invalid count")
    print("D439_" + key.upper() + "=" + str(n))
print("D439_PUBLIC_RESULT=" + status)
print("D439_ORDERS_SENT=NO")
print("D439_CONTINUOUS_24X7_VERIFIED=NO")
PY
printf 'D439_PRIVATE_EVIDENCE_RETAINED=YES\n'
printf 'D439_J1_SERVICES_MODIFIED=NO\n'

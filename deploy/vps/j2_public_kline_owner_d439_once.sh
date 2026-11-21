#!/usr/bin/env bash
# D441: host-only, J1-independent finite public BTCUSDT research. NO J1 writes/orders.
set -euo pipefail
umask 077
test "$#" -eq 2 || { echo 'D439_BLOCKED=ARGUMENTS'; exit 77; }
MODE="$1"
SHA="$2"
OWNER=cia-probe
HOST=srv1319424
BASE=/home/cia-probe/agent
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
test "$(/usr/bin/id -u "$OWNER")" -gt 0 || fail OWNER_ID
"$RUNUSER" -u "$OWNER" -- /usr/bin/id -u >/dev/null 2>&1 || fail OWNER_SWITCH
test "$(/usr/bin/timedatectl show -p NTPSynchronized --value 2>/dev/null)" = yes || fail CLOCK_NTP
"$RUNUSER" -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 "$PY" -B -c 'import websockets.sync.client' >/dev/null 2>&1 || fail WEBSSOCKETS_LIBRARY
# Preflight is J1-independent. One public BTCUSDT REST GET runs only under
# --capture, after region, rights and owner gates; no N50 pointer is read.
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
test -f "$CODE/crypto_intelligence_agent/j2_public_btc_scope_d441.py" || fail D441_MISSING
printf 'D439_PUBLIC_SCOPE=ISOLATED_BTCUSDT_REST_RESEARCH\n'
printf 'D439_PUBLIC_REST_AND_WS=ATTEMPTING_READONLY\n'
set +e
RAW="$("$TIMEOUT" 300 "$RUNUSER" -u "$OWNER" -- /usr/bin/env \
    PYTHONPATH="$CODE" PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    "$PY" -m scripts.run_j2_public_kline_session_d437_once \
    --output-dir "$OUT" \
    --max-seconds 240 --max-frames 24000 \
    --allow-public-network --allow-public-websocket \
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
print("D439_PRIVATE_EVIDENCE_RETAINED=" +
      ("YES" if v.get("private_evidence_retained") is True else "NO"))
PY
printf 'D439_J1_SERVICES_MODIFIED=NO\n'

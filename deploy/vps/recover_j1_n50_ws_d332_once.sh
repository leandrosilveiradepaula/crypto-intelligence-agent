#!/usr/bin/env bash
# J1/D332: root-only recovery of the already-installed D322 WS timers.
# Updates only the owner-pinned D322 code checkout. Never bootstraps a new
# epoch, repeats provider GETs, edits private SQLite or installs systemd units.
# If timer cutover fails after N2 quiescence, restore N2 immediately.
set -euo pipefail
umask 077

OWNER=cia-probe
HOST=srv1319424
OLD_SHA=c1fbd4cd46bba108be14859b9a04bb4184c3e91f
NEW_SHA="$1"
ORIGIN=https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git
N2=cia-j1-rest-hourly.timer
WS=cia-j1-n50-ws.timer
ROT=cia-j1-n50-ws-rotate.timer
SERVICE=cia-j1-n50-ws.service
OLD_REST=cia-j1-n50-managed.timer
PY=/home/cia-probe/agent/ws-venv/bin/python
SYSTEMCTL=/usr/bin/systemctl
RUNUSER=/usr/sbin/runuser
GIT=/usr/bin/git

if test "$(id -u)" != 0 || test "$(hostname)" != "$HOST"; then
  echo "blocked: expected root on approved VPS" >&2
  exit 77
fi
if [[ ! "$NEW_SHA" =~ ^[0-9a-f]{40}$ ]] || test "$NEW_SHA" = "$OLD_SHA"; then
  echo "blocked: reviewed exact newer SHA required" >&2
  exit 77
fi
test "$(/usr/bin/timedatectl show -p NTPSynchronized --value)" = yes
test -x "$PY"
test "$($SYSTEMCTL show "$N2" -p LoadState --value)" = loaded
test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = active
test "$($SYSTEMCTL show "$N2" -p UnitFileState --value)" = enabled
test "$($SYSTEMCTL show "$WS" -p LoadState --value)" = loaded
test "$($SYSTEMCTL show "$WS" -p ActiveState --value)" = inactive
test "$($SYSTEMCTL show "$WS" -p UnitFileState --value)" = disabled
test "$($SYSTEMCTL show "$ROT" -p LoadState --value)" = loaded
test "$($SYSTEMCTL show "$ROT" -p ActiveState --value)" = inactive
test "$($SYSTEMCTL show "$ROT" -p UnitFileState --value)" = disabled
test "$($SYSTEMCTL show "$OLD_REST" -p ActiveState --value)" = inactive
test "$($SYSTEMCTL show "$OLD_REST" -p UnitFileState --value)" = disabled
test "$($SYSTEMCTL show "$SERVICE" -p LoadState --value)" = loaded
test "$($SYSTEMCTL show "$SERVICE" -p User --value)" = "$OWNER"
test "$($SYSTEMCTL show "$SERVICE" -p UnitFileState --value)" = static
test "$($SYSTEMCTL show "$SERVICE" -p FragmentPath --value)" = /etc/systemd/system/cia-j1-n50-ws.service
test "$($SYSTEMCTL show "$SERVICE" -p ActiveState --value)" = failed
test "$($SYSTEMCTL show cia-j1-n50-ws-fallback.service -p Result --value)" = success
test "$($SYSTEMCTL show cia-j1-rest-hourly.service -p ActiveState --value)" = inactive

CODE="$($SYSTEMCTL show "$SERVICE" -p WorkingDirectory --value)"
if [[ ! "$CODE" =~ ^/home/cia-probe/agent/j1-n50-ws-70dec97d0a39-code-[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "blocked: D322 code checkout unexpected" >&2
  exit 77
fi
test -d "$CODE"
test ! -L "$CODE"
test "$(stat -c %U "$CODE")" = "$OWNER"
test "$(stat -c %a "$CODE")" = 700
test "$($RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" rev-parse HEAD)" = "$OLD_SHA"
test -z "$($RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" status --porcelain)"
test "$($RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" remote get-url origin)" = "$ORIGIN"

echo "D332_RECOVERY_STAGE_1_OLD_N2_AND_CODE_PREFLIGHT_PASS"

# Fetch exact reviewed GitHub commit into the same owner-only checkout.
# All private data is outside CODE in the immutable D321 epoch directory.
$RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" fetch --quiet --no-tags origin "$NEW_SHA"
test "$($RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" rev-parse FETCH_HEAD)" = "$NEW_SHA"
$RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" checkout --quiet --detach "$NEW_SHA"
test "$($RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" rev-parse HEAD)" = "$NEW_SHA"
test -z "$($RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" status --porcelain)"
test -f "$CODE/tests/test_j1_n50_ws_single_letter_usdt_d332.py"
test -f "$CODE/tests/test_j1_n50_ws_halt_taxonomy_d331.py"
test -f "$CODE/tests/test_j1_n50_ws_server_bounded_trade_clock_d329.py"
test -f "$CODE/tests/test_j1_n50_ws_temporal_quarantine_d328.py"
test -f "$CODE/tests/test_j1_n50_ws_open_trade_timestamp_d327.py"
test -f "$CODE/tests/test_j1_n50_ws_confirm_boundary_d326.py"
test -f "$CODE/crypto_intelligence_agent/bybit_closed_stream_cache.py"

# Local-only regression on the deployed Python and dependency set.
(cd "$CODE" && $RUNUSER -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m unittest discover -s tests -p test_j1_n50_ws_single_letter_usdt_d332.py -q)
(cd "$CODE" && $RUNUSER -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m unittest discover -s tests -p test_j1_n50_ws_halt_taxonomy_d331.py -q)
(cd "$CODE" && $RUNUSER -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m unittest discover -s tests -p test_j1_n50_ws_server_bounded_trade_clock_d329.py -q)
(cd "$CODE" && $RUNUSER -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m unittest discover -s tests -p test_j1_n50_ws_temporal_quarantine_d328.py -q)
(cd "$CODE" && $RUNUSER -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m unittest discover -s tests -p test_j1_n50_ws_open_trade_timestamp_d327.py -q)
(cd "$CODE" && $RUNUSER -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m unittest discover -s tests -p test_j1_n50_ws_confirm_boundary_d326.py -q)
# Revalidate the actual private D321 pointer and D316 admission while N2
# still runs, without printing or writing any symbol/market data.
(cd "$CODE" && $RUNUSER -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1   "$PY" -c 'import time; from pathlib import Path; from crypto_intelligence_agent.j1_n50_ws_epoch_rotation import load_active_n50_ws_epoch; a=load_active_n50_ws_epoch(state_directory=Path("/home/cia-probe/agent/j1-n50-ws-epochs/active"), current_at_ms=time.time_ns()//1000000, allow_private_pointer_read=True); assert a.status=="active_n50_ws_epoch_revalidated", "owner pointer not eligible"')
echo "D332_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS"

# Keep the N2 timer enabled until all code and owner safety gates pass.
test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = active
test "$($SYSTEMCTL show "$N2" -p UnitFileState --value)" = enabled
test "$($SYSTEMCTL show cia-j1-rest-hourly.service -p ActiveState --value)" = inactive
test "$($SYSTEMCTL show "$SERVICE" -p ActiveState --value)" = failed
test "$($SYSTEMCTL show "$WS" -p ActiveState --value)" = inactive
test "$($SYSTEMCTL show "$ROT" -p ActiveState --value)" = inactive

CUTOVER_STARTED=0
restore_n2() {
  $SYSTEMCTL disable --now "$ROT" >/dev/null 2>&1 || true
  $SYSTEMCTL disable --now "$WS" >/dev/null 2>&1 || true
  $SYSTEMCTL enable --now "$N2" >/dev/null 2>&1 || true
  test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = active &&
  test "$($SYSTEMCTL show "$N2" -p UnitFileState --value)" = enabled &&
  test "$($SYSTEMCTL show "$WS" -p ActiveState --value)" = inactive &&
  test "$($SYSTEMCTL show "$ROT" -p ActiveState --value)" = inactive
}
rollback_exit() {
  if restore_n2; then
    CUTOVER_STARTED=0
    echo "D332_RECOVERY_ROLLED_BACK_TO_N2" >&2
    exit 65
  fi
  echo "D332_RECOVERY_N2_ROLLBACK_REQUIRES_OPERATOR" >&2
  exit 75
}

rollback_on_exit() {
  if test "$CUTOVER_STARTED" = 1; then
    if restore_n2; then
      echo "D332_RECOVERY_N2_RESTORED_ON_ABORT" >&2
    else
      echo "D332_RECOVERY_N2_FAILED_ON_ABORT_OPERATOR_REQUIRED" >&2
    fi
  fi
}
trap rollback_on_exit EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

echo "D332_RECOVERY_STAGE_3_CUTOVER"
CUTOVER_STARTED=1
$SYSTEMCTL reset-failed "$SERVICE"
if ! $SYSTEMCTL disable --now "$N2"; then rollback_exit; fi
if ! $SYSTEMCTL enable --now "$WS"; then rollback_exit; fi
if ! $SYSTEMCTL enable --now "$ROT"; then rollback_exit; fi
if ! test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = inactive; then rollback_exit; fi
if ! test "$($SYSTEMCTL show "$N2" -p UnitFileState --value)" = disabled; then rollback_exit; fi
for TIMER in "$WS" "$ROT"; do
  if ! test "$($SYSTEMCTL show "$TIMER" -p ActiveState --value)" = active; then rollback_exit; fi
  if ! test "$($SYSTEMCTL show "$TIMER" -p UnitFileState --value)" = enabled; then rollback_exit; fi
done
if ! test "$($SYSTEMCTL show "$SERVICE" -p ActiveState --value)" = inactive; then rollback_exit; fi
CUTOVER_STARTED=0
echo "D332_RECOVERY_TIMERS_ENABLED_NO_ORDERS"

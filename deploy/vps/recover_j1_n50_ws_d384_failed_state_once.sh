#!/usr/bin/env bash
# D384: one-shot repair of recorded failed REST statuses before N50 WS preflight.
# No code deployment, N50 cohort reselection, market GET, SQL writes or orders.
# This is a gated *operational cutover*, never an automatic CI action.
set -euo pipefail
umask 077

OWNER=cia-probe
HOST=srv1319424
PIN=507e698bcf7ffbf55afd5b30bfa5a9f1e6ee900f
CODE=/home/cia-probe/agent/j1-n50-ws-70dec97d0a39-code-20261113T014549Z
N2=cia-j1-rest-hourly.timer
N2_SERVICE=cia-j1-rest-hourly.service
OLD=cia-j1-n50-managed.timer
OLD_SERVICE=cia-j1-n50-managed.service
WS=cia-j1-n50-ws.timer
ROT=cia-j1-n50-ws-rotate.timer
WS_SERVICE=cia-j1-n50-ws.service
SYSTEMCTL=/usr/bin/systemctl
RUNUSER=/usr/sbin/runuser
PY=/home/cia-probe/agent/ws-venv/bin/python
MUTATED=0
FINALIZED=0

if test "${1:-}" != "$PIN" || test "$#" -ne 1; then
  echo "D384_EXACT_INSTALLED_SHA_REQUIRED" >&2
  exit 77
fi
test "$(id -u)" = 0
test "$(hostname)" = "$HOST"
test "$(/usr/bin/timedatectl show -p NTPSynchronized --value)" = yes
test -x "$PY"
test -d "$CODE"
test ! -L "$CODE"
test "$(stat -c %U "$CODE")" = "$OWNER"
test "$(stat -c %a "$CODE")" = 700
test "$($RUNUSER -u "$OWNER" -- /usr/bin/git -C "$CODE" rev-parse HEAD)" = "$PIN"
test -z "$($RUNUSER -u "$OWNER" -- /usr/bin/git -C "$CODE" status --porcelain)"
test "$($SYSTEMCTL show "$WS_SERVICE" -p WorkingDirectory --value)" = "$CODE"
test "$($SYSTEMCTL show "$WS_SERVICE" -p User --value)" = "$OWNER"
test "$($SYSTEMCTL show "$WS_SERVICE" -p UnitFileState --value)" = static
test "$($SYSTEMCTL show "$N2" -p LoadState --value)" = loaded
test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = active
test "$($SYSTEMCTL show "$N2" -p UnitFileState --value)" = enabled
for T in "$WS" "$ROT" "$OLD"; do
  test "$($SYSTEMCTL show "$T" -p LoadState --value)" = loaded
  test "$($SYSTEMCTL show "$T" -p ActiveState --value)" = inactive
  test "$($SYSTEMCTL show "$T" -p UnitFileState --value)" = disabled
done
for S in "$N2_SERVICE" "$OLD_SERVICE" "$WS_SERVICE"; do
  test "$($SYSTEMCTL show "$S" -p LoadState --value)" = loaded
  test "$($SYSTEMCTL show "$S" -p UnitFileState --value)" = static
  case "$($SYSTEMCTL show "$S" -p ActiveState --value)" in
    inactive|failed) ;;
    *) echo "D384_SERVICE_RUNNING_OR_UNEXPECTED" >&2; exit 77 ;;
  esac
  test "$($SYSTEMCTL show "$S" -p MainPID --value)" = 0
  test "$($SYSTEMCTL show "$S" -p ControlPID --value)" = 0
done
test "$($SYSTEMCTL show cia-j2-owner-prospective.timer -p LoadState --value)" = not-found
test "$($SYSTEMCTL show cia-j3-owner-forward.timer -p LoadState --value)" = not-found
/usr/bin/systemd-analyze verify \
  /etc/systemd/system/cia-j1-n50-ws.service \
  /etc/systemd/system/cia-j1-n50-ws.timer \
  /etc/systemd/system/cia-j1-n50-ws-rotate.timer
# Refuse cutover near hourly boundary or rotation.
safe_hourly_window() {
  local phase
  phase=$(( $(/usr/bin/date -u +%s) % 3600 ))
  if test "$phase" -lt 180 || test "$phase" -ge 3480; then
    echo "D384_HOURLY_CUTOVER_WINDOW_BLOCKED" >&2
    return 1
  fi
}
safe_hourly_window

restore_n2() {
  $SYSTEMCTL disable --now "$ROT" >/dev/null 2>&1 || true
  $SYSTEMCTL disable --now "$WS" >/dev/null 2>&1 || true
  $SYSTEMCTL stop "$WS_SERVICE" >/dev/null 2>&1 || true
  case "$($SYSTEMCTL show "$WS_SERVICE" -p ActiveState --value)" in
    failed|inactive) ;;
    *) return 1 ;;
  esac
  $SYSTEMCTL enable --now "$N2" >/dev/null 2>&1 || true
  test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = active &&
  test "$($SYSTEMCTL show "$N2" -p UnitFileState --value)" = enabled &&
  test "$($SYSTEMCTL show "$WS" -p ActiveState --value)" = inactive &&
  test "$($SYSTEMCTL show "$ROT" -p ActiveState --value)" = inactive
}
cleanup() {
  local result="$?"
  trap - EXIT
  if test "$FINALIZED" != 1 && test "$MUTATED" = 1; then
    if restore_n2; then
      echo "D384_N2_RESTORED_ON_ABORT" >&2
    else
      echo "D384_ROLLBACK_REQUIRES_OPERATOR" >&2
      exit 75
    fi
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
echo "D384_PRECHECK_PIN_TIMER_AND_QUIESCENT_SERVICES_PASS"

# Failure is solely a *recorded unit state*; never rewrite data or weaken
# the existing read-only ExecStartPre admission criteria.
MUTATED=1
$SYSTEMCTL disable --now "$N2"
# This is the difference from D381: the N2 preflight requires inactive,
# whereas D381 accepted the previously failed but quiescent REST service.
$SYSTEMCTL reset-failed "$N2_SERVICE" "$OLD_SERVICE" "$WS_SERVICE"
for S in "$N2_SERVICE" "$OLD_SERVICE" "$WS_SERVICE"; do
  test "$($SYSTEMCTL show "$S" -p ActiveState --value)" = inactive
  test "$($SYSTEMCTL show "$S" -p MainPID --value)" = 0
done
test "$($SYSTEMCTL show "$N2" -p UnitFileState --value)" = disabled
test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = inactive
safe_hourly_window

PREFLIGHT="$(cd "$CODE" && $RUNUSER -u "$OWNER" -- \
  /usr/bin/env PYTHONDONTWRITEBYTECODE=1 "$PY" \
  -m scripts.preflight_j1_n50_ws_systemd --require-old-collectors-quiesced)"
printf '%s' "$PREFLIGHT" | /usr/bin/python3 -c '
import json,sys
p=json.load(sys.stdin)
assert p["schema_version"]=="j1-n50-ws-systemd-preflight-v1"
assert p["status"]=="old_collectors_quiesced_preflight_only"
assert p["n2_quiesced"] is True
assert p["old_rest_timer_disabled"] is True
assert p["old_rest_service_stopped"] is True
assert p["systemd_modified"] is False
assert p["orders_sent"] is False
'
echo "D384_OWNER_READONLY_SYSTEMD_PREFLIGHT_PASS"

$SYSTEMCTL enable --now "$WS"
$SYSTEMCTL enable --now "$ROT"
test "$($SYSTEMCTL show "$WS" -p ActiveState --value)" = active
test "$($SYSTEMCTL show "$WS" -p UnitFileState --value)" = enabled
test "$($SYSTEMCTL show "$ROT" -p ActiveState --value)" = active
test "$($SYSTEMCTL show "$ROT" -p UnitFileState --value)" = enabled
test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = inactive
test "$($SYSTEMCTL show "$N2" -p UnitFileState --value)" = disabled
FINALIZED=1
MUTATED=0
echo "D384_WS_TIMERS_ENABLED_WITH_N2_PREFLIGHT_PASS_NO_ORDERS"

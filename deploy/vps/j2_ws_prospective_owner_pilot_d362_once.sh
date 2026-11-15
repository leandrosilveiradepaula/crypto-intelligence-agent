#!/usr/bin/env bash
# D362 / #658: isolated owner J2 prospective pilot, never a J1 cutover.
# Deployment and first capture are separate human-gated production actions.
set -euo pipefail
umask 077

MODE="${1:-}"
SHA="${2:-}"
OWNER=cia-probe
HOST=srv1319424
BASE=/home/cia-probe/agent
PY="$BASE/ws-venv/bin/python"
ORIGIN=https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git
RUNUSER=/usr/sbin/runuser
GIT=/usr/bin/git
SYSTEMCTL=/usr/bin/systemctl
TIMEOUT=/usr/bin/timeout
WORK="$BASE/j2-owner-prospective-d362-${SHA:0:12}"
CODE="$WORK/code"

fail() { printf 'D362_BLOCKED_%s\n' "$1"; exit 77; }

case "$MODE" in
  --preflight-os|--confirm-owner-capture) test "$#" -eq 2 || fail ARGUMENTS ;;
  --score-once) test "$#" -eq 8 || fail ARGUMENTS ;;
  *) fail MODE ;;
esac
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || fail SHA40_REQUIRED
test "$(/usr/bin/id -u)" -eq 0 || fail ROOT_REQUIRED
test "$(/usr/bin/hostname)" = "$HOST" || fail HOST
test -x "$PY" || fail PYTHON_MISSING
test -d "$BASE" && test ! -L "$BASE" || fail OWNER_BASE
test "$(/usr/bin/id -u "$OWNER")" -ne 0 || fail OWNER_NONROOT
"$RUNUSER" -u "$OWNER" -- /usr/bin/test -d "$BASE" || fail OWNER_BASE_DAC
test "$(/usr/bin/timedatectl show -p NTPSynchronized --value)" = yes || fail CLOCK_NOT_SYNC
for UNIT in cia-j1-n50-ws.timer cia-j1-n50-ws-rotate.timer; do
  test "$("$SYSTEMCTL" show "$UNIT" -p ActiveState --value)" = active || fail WS_TIMER_NOT_ACTIVE
  test "$("$SYSTEMCTL" show "$UNIT" -p UnitFileState --value)" = enabled || fail WS_TIMER_NOT_ENABLED
done
test "$("$SYSTEMCTL" show cia-j1-rest-hourly.timer -p ActiveState --value)" = inactive || fail REST_CONFLICT
test "$("$SYSTEMCTL" show cia-j1-n50-managed.timer -p ActiveState --value)" = inactive || fail N50_REST_CONFLICT

if test "$MODE" = --preflight-os; then
  test ! -L "$WORK" || fail WORK_SYMLINK
  printf 'D362_OS_PREFLIGHT=PASS_NO_OWNER_READ_NO_WRITES\n'
  printf 'D362_PINNED_SHA=%s\n' "$SHA"
  exit 0
fi

if test "$MODE" = --confirm-owner-capture; then
  # A one-shot isolated checkout is created only after a separate release gate.
  test ! -L "$WORK" && test ! -L "$CODE" || fail WORK_SYMLINK
  if test ! -e "$WORK"; then
    "$RUNUSER" -u "$OWNER" -- /usr/bin/install -d -m 0700 "$WORK"
    "$TIMEOUT" 120 "$RUNUSER" -u "$OWNER" -- "$GIT" clone --quiet --no-checkout --depth 1 "$ORIGIN" "$CODE" \
      >/dev/null 2>&1 || fail PINNED_CLONE
    "$TIMEOUT" 120 "$RUNUSER" -u "$OWNER" -- "$GIT" -C "$CODE" fetch --quiet --no-tags --depth 1 origin "$SHA" \
      >/dev/null 2>&1 || fail PINNED_FETCH
    test "$("$RUNUSER" -u "$OWNER" -- "$GIT" -C "$CODE" rev-parse FETCH_HEAD)" = "$SHA" || fail FETCH_SHA
    "$RUNUSER" -u "$OWNER" -- "$GIT" -C "$CODE" checkout --quiet --detach "$SHA" \
      >/dev/null 2>&1 || fail PINNED_CHECKOUT
  fi
fi

test -d "$WORK" && test ! -L "$WORK" || fail WORK_MISSING
test -d "$CODE" && test ! -L "$CODE" || fail CODE_MISSING
test "$(/usr/bin/stat -c %U:%a "$WORK")" = "$OWNER:700" || fail WORK_DAC
test "$(/usr/bin/stat -c %U:%a "$CODE")" = "$OWNER:700" || fail CODE_DAC
test "$("$RUNUSER" -u "$OWNER" -- "$GIT" -C "$CODE" rev-parse HEAD)" = "$SHA" || fail CODE_SHA
test -z "$("$RUNUSER" -u "$OWNER" -- "$GIT" -C "$CODE" status --porcelain)" || fail CODE_DIRTY
for FILE in \
  crypto_intelligence_agent/j2_ws_owner_preflight.py \
  crypto_intelligence_agent/j2_ws_prospective_ledger.py \
  scripts/research_j2_ws_prospective_once.py; do
  test -f "$CODE/$FILE" && test ! -L "$CODE/$FILE" || fail CODE_FILE
done
printf 'D362_OWNER_CHECKOUT_PINNED=%s\n' "$SHA"

owner_cli() (
  cd "$CODE"
  "$TIMEOUT" 180 "$RUNUSER" -u "$OWNER" -- /usr/bin/env \
    PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    "$PY" -m scripts.research_j2_ws_prospective_once "$@" 2>/dev/null
)

# Never forward a raw owner JSON on stdout; print only validated allowlisted fields.
safe_report() {
  local RAW="$1" KIND="$2"
  test "${#RAW}" -le 4096 || fail OWNER_REPORT_LIMIT
  PILOT_JSON="$RAW" /usr/bin/python3 -B - "$KIND" <<'PY'
import json, os, re, sys, time
kind = sys.argv[1]
try:
    raw = os.environ["PILOT_JSON"]
    data = json.loads(raw)
    if type(data) is not dict or len(raw) > 4096:
        raise ValueError()
    status = data.get("status")
    if type(status) is not str or not re.fullmatch(r"[a-z0-9_]{1,90}", status):
        raise ValueError()
    if (data.get("orders_sent") is not False
            or data.get("approved_for_signals") is not False
            or data.get("database_mutation_statements") != 0
            or data.get("network_requests") != 0
            or data.get("systemd_modified") is not False):
        raise ValueError()
    if kind == "preflight":
        ok = (data.get("schema_version") == "j2-ws-owner-preflight-v1"
              and status == "owner_preflight_ready_no_capture"
              and all(data.get(key) is True for key in (
                "owner_nonroot_posix_verified", "owner_ledger_parent_dac_verified",
                "os_ntp_sync_reported", "capture_window_open",
                "owner_ws_50x24_readonly_replayed", "capture_eligible_now"))
              and data.get("prospective_registration_independently_verified") is False)
    elif kind == "capture":
        end = data.get("decision_closed_end_ms")
        created = data.get("capture_records_created")
        candidates = data.get("candidates_captured")
        now = time.time_ns() // 1_000_000
        ok = (data.get("schema_version") == "j2-ws-owner-ledger-status-v1"
              and status == "owner_local_decision_captured_not_independent_attestation"
              and type(end) is int and end % 3600000 == 0
              and end <= now < end + 3600000
              and type(created) is int and created == 1
              and type(candidates) is int and 0 <= candidates <= 10
              and data.get("local_decision_record_consistency_verified") is True
              and data.get("prospective_registration_independently_verified") is False
              and data.get("financial_backtest_approved") is False)
        if ok:
            print("D362_DECISION_CLOSED_END_MS=" + str(end))
            print("D362_CANDIDATES_CAPTURED=" + str(candidates))
    elif kind == "score":
        selected = data.get("selected_observations")
        matured = data.get("matured_observations")
        horizon = data.get("horizon_bars")
        ok = (data.get("schema_version") == "j3-ws-watchlist-forward-reference-v1"
              and status in (
                  "ex_post_reference_marks_scored_not_a_backtest",
                  "no_observations_selected")
              and type(horizon) is int and horizon in (1,4,8)
              and type(selected) is int and 0 <= selected <= 10
              and type(matured) is int and 0 <= matured <= selected
              and data.get("prospective_registration_independently_verified") is False
              and data.get("financial_backtest_approved") is False
              and data.get("out_of_sample_results_validated") is False)
        if ok:
            print("D362_SCORE_HORIZON_HOURS=" + str(horizon))
            print("D362_SELECTED_OBSERVATIONS=" + str(selected))
            print("D362_MATURED_OBSERVATIONS=" + str(matured))
            print("D362_REFERENCE_ONLY_NOT_FILLS=true")
    else:
        raise ValueError()
    print("D362_OWNER_" + kind.upper() + "_STATUS=" + status)
    if not ok:
        sys.exit(76)
except (ValueError, TypeError, KeyError, OverflowError):
    print("D362_REPORT_REJECTED")
    sys.exit(77)
PY
}

if test "$MODE" = --confirm-owner-capture; then
  # No change of J1 SQLite or systemd; regression suites are offline as owner.
  for SUITE in \
    test_j2_ws_owner_preflight.py \
    test_j2_ws_prospective_ledger.py \
    test_j2_n50_ws_private_screen.py; do
    (cd "$CODE" && "$TIMEOUT" 150 "$RUNUSER" -u "$OWNER" -- /usr/bin/env \
      PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
      "$PY" -m unittest discover -s tests -p "$SUITE" -q) \
      >/dev/null 2>&1 || fail OFFLINE_OWNER_REGRESSION
  done
  echo "D362_OWNER_OFFLINE_TESTS=PASS"
  if PREFLIGHT="$(owner_cli preflight --allow-private-readonly-research)"; then
    if safe_report "$PREFLIGHT" preflight; then :; else
      echo "D362_NO_CAPTURE_PREFLIGHT_ABSTAIN"
      exit 76
    fi
  else
    echo "D362_NO_CAPTURE_PREFLIGHT_ABSTAIN"
    exit 76
  fi
  test "$("$SYSTEMCTL" show cia-j1-n50-ws-rotate.service -p ActiveState --value)" = inactive \
    || fail ROTATION_IN_PROGRESS
  if CAPTURE="$(owner_cli capture --allow-private-readonly-research --allow-private-ledger-write)"; then
    safe_report "$CAPTURE" capture || exit 76
  else
    echo "D362_CAPTURE_ABSTAIN_NO_RETRY"
    exit 76
  fi
  echo "D362_CAPTURE_FINISHED_ONE_SHOT_NO_SCHEDULER"
  exit 0
fi

# --score-once: no new checkout, no capture, no authoring of local evidence.
HORIZON="$3"
case "$HORIZON" in 1|4|8) ;; *) fail HORIZON ;; esac
for VALUE in "$4" "$5" "$6" "$7" "$8"; do
  [[ "$VALUE" =~ ^[0-9]{1,9}([.][0-9]{1,8})?$ ]] || fail COST_ARGUMENTS
done
if SCORE="$(owner_cli score --allow-private-readonly-research --allow-private-ledger-read \
  --horizon-bars "$HORIZON" --notional "$4" --entry-fee-bps "$5" \
  --exit-fee-bps "$6" --entry-slippage-bps "$7" --exit-slippage-bps "$8")"; then
  safe_report "$SCORE" score || exit 76
  echo "D362_SCORE_OBSERVED_NOT_INDEPENDENT_OOS"
else
  echo "D362_SCORE_ABSTAIN_NO_RETRY"
  exit 76
fi

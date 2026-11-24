#!/usr/bin/env bash
# D515: one owner-approved PAPER-only upgrade from D507.
# The reviewed product commit must be the exact main HEAD supplied by the operator.
# No J1, policy or journal replacement, private exchange credentials, or real orders.
set -Eeuo pipefail
umask 077

APPROVED_SHA="${1:-}"
EXPECTED_HOST="${CIA_D515_EXPECT_HOST:-}"
OLD_SHA="056845fdc46b8c2d1b08acd86be75e59dd368bac"
OWNER="cia-probe"
BASE="/home/cia-probe/agent"
PY="$BASE/ws-venv/bin/python"
ROOT_PY="/usr/bin/python3"
PAPER="$BASE/d487-profile-20261123/paper_live"
POLICY="$BASE/d487-profile-20261123/strategy.json"
MOTOR="cia-paper-research-d498.service"
PANEL="cia-paper-config-d498.service"
J1="cia-j1-n50-ws.timer"
MOTOR_OLD="/etc/systemd/system/$MOTOR.d/90-cia-d507-pinned.conf"
PANEL_OLD="/etc/systemd/system/$PANEL.d/90-cia-d507-pinned.conf"
MOTOR_DROP="/etc/systemd/system/$MOTOR.d/91-cia-d515-pinned.conf"
PANEL_DROP="/etc/systemd/system/$PANEL.d/91-cia-d515-pinned.conf"
RUN_LOCK="/run/cia-paper-d515-cutover.lock"
LOCK_CREATED=0
ROLLBACK_ARMED=0
LOCK_IN=""
LOCK_PID=""
OLD_CODE=""

die() { printf 'D515_DENIED=%s\n' "$1" >&2; exit 1; }

finish() {
  local rc="$?"
  trap - EXIT
  if [ "$ROLLBACK_ARMED" = "1" ]; then
    printf 'D515_ROLLBACK=START rc=%s\n' "$rc" >&2
    systemctl stop "$MOTOR" "$PANEL" || true
    rm -f -- "$MOTOR_DROP" "$PANEL_DROP" || true
    systemctl daemon-reload || true
    if [ "$(systemctl show -P WorkingDirectory "$MOTOR")" = "$OLD_CODE" ] &&
       [ "$(systemctl show -P WorkingDirectory "$PANEL")" = "$OLD_CODE" ]; then
      systemctl start "$PANEL" || true
      systemctl start "$MOTOR" || true
      systemctl is-active "$MOTOR" "$PANEL" "$J1" || true
      printf 'D515_ROLLBACK=ATTEMPTED_VERIFY_UNITS\n' >&2
    else
      printf 'D515_ROLLBACK=MANUAL_REQUIRED_OLD_PATH_NOT_EFFECTIVE\n' >&2
    fi
  fi
  if [ -n "$LOCK_IN" ]; then
    exec {LOCK_IN}>&- || true
  fi
  if [ "$LOCK_CREATED" = "1" ]; then
    rmdir "$RUN_LOCK" || true
  fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

test "$(id -u)" = "0" || die "root_shell_required"
test "$#" = "1" && [[ "$APPROVED_SHA" =~ ^[0-9a-f]{40}$ ]] ||
  die "exact_reviewed_main_sha_required"
test "$APPROVED_SHA" != "$OLD_SHA" || die "same_as_installed_version"
test -n "$EXPECTED_HOST" && test "$(hostname)" = "$EXPECTED_HOST" ||
  die "explicit_correct_host_pin_required"
test -d "$BASE" && test ! -L "$BASE" || die "owner_home_unsafe"
test -x "$PY" && test -x "$ROOT_PY" || die "python_unavailable"
mkdir -m 0700 "$RUN_LOCK" || die "another_cutover_or_stale_lock"
LOCK_CREATED=1
for unit in "$MOTOR" "$PANEL"; do
  test "$(systemctl show -P User "$unit")" = "$OWNER" || die "service_owner_changed"
  test "$(systemctl is-active "$unit")" = "active" || die "paper_service_inactive"
done
test "$(systemctl is-active "$J1")" = "active" || die "J1_not_active"
OLD_CODE="$(systemctl show -P WorkingDirectory "$MOTOR")"
case "$OLD_CODE" in
  "$BASE"/d507-paper-cutover-????????/repo) ;;
  *) die "unexpected_D507_code_path" ;;
esac
test "$(systemctl show -P WorkingDirectory "$PANEL")" = "$OLD_CODE" ||
  die "different_paper_code_paths"
test "$(systemctl show -P DropInPaths "$MOTOR")" = "$MOTOR_OLD" ||
  die "motor_overrides_changed"
test "$(systemctl show -P DropInPaths "$PANEL")" = "$PANEL_OLD" ||
  die "panel_overrides_changed"
for file in "$MOTOR_OLD" "$PANEL_OLD"; do
  test -f "$file" && test ! -L "$file" || die "old_override_unsafe"
  cmp -s "$file" <(printf '[Service]\nWorkingDirectory=%s\n' "$OLD_CODE") ||
    die "old_override_content_changed"
done
for file in "$MOTOR_DROP" "$PANEL_DROP"; do
  test ! -e "$file" && test ! -L "$file" || die "new_override_already_exists"
done
test "$(runuser -u "$OWNER" -- git -C "$OLD_CODE" rev-parse HEAD)" = "$OLD_SHA" ||
  die "installed_sha_changed"

# Root uses only system Python for sanitized HTTP checks. Product code runs as owner.
check_zero_open() {
  curl --noproxy '*' --fail --silent --show-error --max-time 8 \
    "http://127.0.0.1:8766/api/paper-session" |
    "$ROOT_PY" -c '
import json, sys
s = json.load(sys.stdin)
if not (s.get("status") == "paper_journal_readback"
        and s.get("orders_sent") is False
        and type(s.get("open_position_count")) is int
        and s["open_position_count"] == 0
        and type(s.get("position_count")) is int
        and s["position_count"] >= 1
        and s.get("closed_position_count") == s["position_count"]):
    sys.exit("D515_DENIED=nonzero_open_or_invalid_session")
print("D515_PAPER_OPEN=0")
'
}
check_zero_open

STAGE="$(mktemp -d "$BASE/d515-paper-cutover-XXXXXXXX")"
chown "$OWNER:$OWNER" "$STAGE"
chmod 0700 "$STAGE"
REPO="$STAGE/repo"
runuser -u "$OWNER" -- env GIT_TERMINAL_PROMPT=0 \
  git clone --quiet --depth 1 --single-branch --branch main \
  "https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git" "$REPO"
test "$(runuser -u "$OWNER" -- git -C "$REPO" rev-parse HEAD)" = "$APPROVED_SHA" ||
  die "main_moved_or_unapproved_revision"
runuser -u "$OWNER" -- git -C "$REPO" checkout --quiet --detach "$APPROVED_SHA"
test -z "$(runuser -u "$OWNER" -- git -C "$REPO" status --porcelain)" ||
  die "staged_code_not_clean"
test -f "$REPO/crypto_intelligence_agent/j2_configurable_indicators_d513.py" ||
  die "indicator_delivery_missing"
test -f "$REPO/crypto_intelligence_agent/j3_archived_strategy_comparison_d512.py" ||
  die "comparison_delivery_missing"
printf 'D515_CODE_PIN=%s\n' "$APPROVED_SHA"

owner_preflight() {
  runuser -u "$OWNER" -- env PYTHONPATH="$REPO" PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m scripts.preflight_paper_owner_d505 \
      --paper-directory "$PAPER" --policy-file "$POLICY"
}
owner_preflight
check_zero_open
printf 'D515_PREFLIGHT=PASS_NO_SERVICE_CHANGED\n'
printf 'D515_SCOPE=only_two_paper_services;old_overrides_preserved;J1_untouched;no_orders\n'
printf 'Nao altere o perfil enquanto a atualizacao estiver em andamento.\n'
printf 'Para publicar o codigo PAPER acima, digite: AUTORIZO CUTOVER PAPER\n'
APPROVAL=""
if ! read -r -p 'Confirmacao: ' APPROVAL < /dev/tty; then
  printf 'D515_RELEASE=NOT_AUTHORIZED_NO_TTY\n'
  exit 0
fi
if [ "$APPROVAL" != "AUTORIZO CUTOVER PAPER" ]; then
  printf 'D515_RELEASE=NOT_AUTHORIZED\n'
  exit 0
fi
printf 'D515_RELEASE_AUTHORIZED=YES\n'

# Use the existing owner profile lock, preventing API profile saves while
# either revision is being switched/rolled back. No policy bytes are changed.
coproc PROFILE_LOCK {
  runuser -u "$OWNER" -- env PYTHONPATH="$REPO" PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -u -c '
import sys
from pathlib import Path
from crypto_intelligence_agent.paper_profile_d487 import _owner_lock, _private_directory
with _owner_lock(_private_directory(Path(sys.argv[1]).parent)):
    print("LOCKED", flush=True)
    sys.stdin.buffer.read(1)
' "$POLICY"
}
LOCK_PID="$PROFILE_LOCK_PID"
LOCK_IN="${PROFILE_LOCK[1]}"
LOCK_OUT="${PROFILE_LOCK[0]}"
read -r -t 10 -u "$LOCK_OUT" lock_status || die "profile_lock_unavailable"
test "$lock_status" = "LOCKED" && kill -0 "$LOCK_PID" ||
  die "profile_lock_not_held"

check_zero_open
ROLLBACK_ARMED=1
systemctl stop "$MOTOR"
check_zero_open
systemctl stop "$PANEL"

# Add a later drop-in, preserving the installed D507 overrides and old checkout.
( set -o noclobber; printf '[Service]\nWorkingDirectory=%s\n' "$REPO" > "$MOTOR_DROP" )
( set -o noclobber; printf '[Service]\nWorkingDirectory=%s\n' "$REPO" > "$PANEL_DROP" )
chmod 0644 "$MOTOR_DROP" "$PANEL_DROP"
systemctl daemon-reload
for unit in "$MOTOR" "$PANEL"; do
  test "$(systemctl show -P WorkingDirectory "$unit")" = "$REPO" ||
    die "new_override_not_effective"
done
kill -0 "$LOCK_PID" || die "profile_lock_lost"
systemctl start "$PANEL"

# Verify deployed product before allowing the new motor to start.
# A legitimately absent completed lease is not a broken route.
READY=0
for attempt in $(seq 1 15); do
  if "$ROOT_PY" - <<'PY'
import json
from urllib.request import build_opener, ProxyHandler
from urllib.error import HTTPError
o = build_opener(ProxyHandler({}))
def get(path):
    try:
        with o.open("http://127.0.0.1:8766" + path, timeout=4) as r:
            return r.status, r.read(2_000_001)
    except HTTPError as e:
        return e.code, e.read(2_000_001)
def load(path, status):
    code, data = get(path)
    if code not in status or len(data) > 2_000_000:
        raise RuntimeError("endpoint")
    return code, json.loads(data)
def require(ok):
    if not ok:
        raise RuntimeError("contract")
try:
    _, session = load("/api/paper-session", (200,))
    require(session.get("orders_sent") is False
            and session.get("open_position_count") == 0
            and session["paper_scorecard"]["schema_version"] ==
                "d511-observed-paper-closed-scorecard-v1")
    _, page = load("/api/paper-history?offset=0&limit=25", (200,))
    require(page.get("orders_sent") is False
            and page.get("position_count") == session["position_count"])
    _, profile = load("/api/profile", (200,))
    require(profile.get("orders_sent") is False
            and profile.get("applies_to") == "future_paper_sessions_only")
    code, funnel = load("/api/paper-decision-funnel", (200,503))
    require(funnel.get("orders_sent") is False and
            (funnel.get("schema_version") == "d509-paper-decision-funnel-v1"
             if code == 200 else funnel.get("status") == "no_valid_completed_public_lease"))
    _, comparison = load("/api/strategy-comparison", (400,))
    require(comparison.get("status") == "invalid_comparison_periods"
            and comparison.get("orders_sent") is False)
    code, html = get("/")
    require(code == 200 and b"ci-sma-0-enabled" in html
            and b"ci-pivot-enabled" in html and b"compare-history" in html)
except (OSError, ValueError, KeyError, TypeError, RuntimeError):
    raise SystemExit(1)
print("D515_PANEL_ENDPOINTS=PASS")
PY
  then
    READY=1
    break
  fi
  sleep 1
done
test "$READY" = "1" || die "new_panel_contract_not_ready"
owner_preflight
kill -0 "$LOCK_PID" || die "profile_lock_lost"
systemctl start "$MOTOR"
test "$(systemctl is-active "$MOTOR")" = "active" || die "new_motor_inactive"
test "$(systemctl is-active "$PANEL")" = "active" || die "new_panel_inactive"
test "$(systemctl is-active "$J1")" = "active" || die "J1_not_active_after_cutover"
ROLLBACK_ARMED=0
printf 'D515_RELEASE=PASS\n'
printf 'D515_CODE_SHA=%s\n' "$APPROVED_SHA"
printf 'D515_J1_UNTOUCHED=YES\n'
printf 'D515_LIVE_ORDERS=NO\n'
printf 'D515_OLD_CODE_AND_OVERRIDES_PRESERVED=YES\n'
printf 'D515_PROFILE_AND_LEDGER_NOT_REPLACED=YES\n'
printf 'D515_HISTORICAL_COMPARISON_SAMPLE_NOT_YET_VALIDATED=YES\n'

#!/usr/bin/env bash
# D519: one owner-approved PAPER-only upgrade from D515 to the tested D518 product.
# Product revision is immutable; this installer is reviewed separately from the product.
# No J1, policy or journal replacement, private exchange credentials, or real orders.
set -Eeuo pipefail
umask 077

APPROVED_SHA="${1:-}"
EXPECTED_HOST="${CIA_D519_EXPECT_HOST:-}"
OLD_SHA="4c3b123785318249c20b343ceb721dbf1a431f73"
PRODUCT_SHA="549742a5f101359b26c18eee4a522f125e7b511e"
OWNER="cia-probe"
BASE="/home/cia-probe/agent"
PY="$BASE/ws-venv/bin/python"
ROOT_PY="/usr/bin/python3"
PAPER="$BASE/d487-profile-20261123/paper_live"
POLICY="$BASE/d487-profile-20261123/strategy.json"
HISTORY="$BASE/d495-resident-20261123/j2"
MOTOR="cia-paper-research-d498.service"
PANEL="cia-paper-config-d498.service"
J1="cia-j1-n50-ws.timer"
MOTOR_BASE="/etc/systemd/system/$MOTOR.d/90-cia-d507-pinned.conf"
PANEL_BASE="/etc/systemd/system/$PANEL.d/90-cia-d507-pinned.conf"
MOTOR_OLD="/etc/systemd/system/$MOTOR.d/91-cia-d515-pinned.conf"
PANEL_OLD="/etc/systemd/system/$PANEL.d/91-cia-d515-pinned.conf"
MOTOR_DROP="/etc/systemd/system/$MOTOR.d/92-cia-d519-pinned.conf"
PANEL_DROP="/etc/systemd/system/$PANEL.d/92-cia-d519-pinned.conf"
RUN_LOCK="/run/cia-paper-d519-cutover.lock"
LOCK_CREATED=0
ROLLBACK_ARMED=0
LOCK_IN=""
LOCK_PID=""
OLD_CODE=""

die() { printf 'D519_DENIED=%s\n' "$1" >&2; exit 1; }

finish() {
  local rc="$?"
  trap - EXIT
  if [ "$ROLLBACK_ARMED" = "1" ]; then
    printf 'D519_ROLLBACK=START rc=%s\n' "$rc" >&2
    systemctl stop "$MOTOR" "$PANEL" || true
    rm -f -- "$MOTOR_DROP" "$PANEL_DROP" || true
    systemctl daemon-reload || true
    if [ "$(systemctl show -P WorkingDirectory "$MOTOR")" = "$OLD_CODE" ] &&
       [ "$(systemctl show -P WorkingDirectory "$PANEL")" = "$OLD_CODE" ]; then
      systemctl start "$PANEL" || true
      systemctl start "$MOTOR" || true
      systemctl is-active "$MOTOR" "$PANEL" "$J1" || true
      printf 'D519_ROLLBACK=ATTEMPTED_VERIFY_UNITS\n' >&2
    else
      printf 'D519_ROLLBACK=MANUAL_REQUIRED_OLD_PATH_NOT_EFFECTIVE\n' >&2
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
  die "exact_reviewed_product_sha_required"
test "$APPROVED_SHA" = "$PRODUCT_SHA" || die "unapproved_product_revision"
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
  "$BASE"/d515-paper-cutover-????????/repo) ;;
  *) die "unexpected_D515_code_path" ;;
esac
test "$(systemctl show -P WorkingDirectory "$PANEL")" = "$OLD_CODE" ||
  die "different_paper_code_paths"
test "$(systemctl show -P DropInPaths "$MOTOR")" = "$MOTOR_BASE $MOTOR_OLD" ||
  die "motor_overrides_changed"
test "$(systemctl show -P DropInPaths "$PANEL")" = "$PANEL_BASE $PANEL_OLD" ||
  die "panel_overrides_changed"
for file in "$MOTOR_BASE" "$PANEL_BASE"; do
  test -f "$file" && test ! -L "$file" || die "base_override_unsafe"
done
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
test -z "$(runuser -u "$OWNER" -- git -C "$OLD_CODE" status --porcelain --untracked-files=no)" ||
  die "installed_tracked_code_changed"

# Root uses only system Python for sanitized HTTP checks. Product code runs as owner.
check_zero_open() {
  curl --noproxy '*' --fail --silent --show-error --max-time 8 \
    "http://127.0.0.1:8766/api/paper-session" |
    "$ROOT_PY" -I -c '
import json, sys
s = json.load(sys.stdin)
if not (s.get("status") == "paper_journal_readback"
        and s.get("orders_sent") is False
        and type(s.get("open_position_count")) is int
        and s["open_position_count"] == 0
        and type(s.get("position_count")) is int
        and s["position_count"] >= 1
        and s.get("closed_position_count") == s["position_count"]):
    sys.exit("D519_DENIED=nonzero_open_or_invalid_session")
print("D519_PAPER_OPEN=0")
'
}
check_zero_open

STAGE="$(mktemp -d "$BASE/d519-paper-cutover-XXXXXXXX")"
chown "$OWNER:$OWNER" "$STAGE"
chmod 0700 "$STAGE"
REPO="$STAGE/repo"
runuser -u "$OWNER" -- git init --quiet "$REPO"
runuser -u "$OWNER" -- git -C "$REPO" remote add origin \
  "https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git"
runuser -u "$OWNER" -- env GIT_TERMINAL_PROMPT=0 \
  git -C "$REPO" fetch --quiet --depth 1 --no-tags origin "$APPROVED_SHA"
runuser -u "$OWNER" -- git -C "$REPO" checkout --quiet --detach FETCH_HEAD
test "$(runuser -u "$OWNER" -- git -C "$REPO" rev-parse HEAD)" = "$PRODUCT_SHA" ||
  die "unapproved_product_revision"
test -z "$(runuser -u "$OWNER" -- git -C "$REPO" status --porcelain)" ||
  die "staged_code_not_clean"
test -f "$REPO/crypto_intelligence_agent/j2_configurable_indicators_d513.py" ||
  die "indicator_delivery_missing"
test -f "$REPO/crypto_intelligence_agent/j3_archived_strategy_comparison_d512.py" ||
  die "comparison_delivery_missing"
for module in j3_retrospective_warmup_d516 j3_observed_exit_scenarios_d517 j3_intrahour_replay_d518; do
  test -f "$REPO/crypto_intelligence_agent/$module.py" || die "research_delivery_missing"
done
printf 'D519_CODE_PIN=%s\n' "$APPROVED_SHA"

owner_preflight() {
  runuser -u "$OWNER" -- env PYTHONPATH="$REPO" PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m scripts.preflight_paper_owner_d505 \
      --paper-directory "$PAPER" --policy-file "$POLICY"
}

# Read the successful owner's existing research supplements, without a new
# capture or profile write. Use the same smoke parameters as the D518 receipt.
owner_research_preflight() {
  timeout 120 runuser -u "$OWNER" -- env PYTHONPATH="$REPO" PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m scripts.run_j3_retrospective_warmup_d516 \
      --historical-directory "$HISTORY" --policy-file "$POLICY" \
      --history-hours 122 --ema-periods 10 30 60 \
      --horizon-hours 4 --resolution 5m --reuse |
    "$ROOT_PY" -I -c '
import json, sys
d = json.load(sys.stdin)
r = d.get("comparison", {})
e = r.get("exit_replay") or {}
assert d.get("orders_sent") is False
assert d["capture"]["status"] == "saved_retrospective_warmup_reused"
assert d["capture"]["public_gets"] == 0
assert d["intrahour_capture"]["status"] == "saved_intrahour_supplement_reused"
assert d["intrahour_capture"]["public_gets"] == 0
assert r.get("schema_version") == "d512-archived-rest-strategy-comparison-v1"
assert r.get("retrospective_warmup_requested") is True
assert e.get("interval") == "5m" and e.get("horizon_hours") == 4
assert e.get("orders_sent") is False
assert e.get("funding_settlement_verified") is False
assert e.get("liquidation_verified") is False
assert e.get("financial_backtest_approved") is False
assert type(e["results"]["reference_long"]["complete_path_count"]) is int
print("D519_OWNER_RESEARCH_REUSE=PASS")
print("D519_OWNER_RESEARCH_COVERED_REFERENCE_PATHS=" +
      str(e["results"]["reference_long"]["complete_path_count"]))
'
}
owner_preflight
owner_research_preflight
check_zero_open
printf 'D519_PREFLIGHT=PASS_NO_SERVICE_CHANGED\n'
printf 'D519_SCOPE=only_two_paper_services;old_overrides_preserved;J1_untouched;no_orders\n'
printf 'Nao altere o perfil enquanto a atualizacao estiver em andamento.\n'
printf 'Para publicar o codigo PAPER acima, digite: AUTORIZO CUTOVER PAPER\n'
APPROVAL=""
if ! read -r -p 'Confirmacao: ' APPROVAL < /dev/tty; then
  printf 'D519_RELEASE=NOT_AUTHORIZED_NO_TTY\n'
  exit 0
fi
if [ "$APPROVAL" != "AUTORIZO CUTOVER PAPER" ]; then
  printf 'D519_RELEASE=NOT_AUTHORIZED\n'
  exit 0
fi
printf 'D519_RELEASE_AUTHORIZED=YES\n'

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

# Add a later drop-in, preserving both D507 and D515 overrides and old checkouts.
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
  if "$ROOT_PY" -I - <<'PY'
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
            and b"ci-pivot-enabled" in html and b"compare-history" in html
            and b"compare-retro" in html and b"compare-resolution" in html
            and b"compare-horizon" in html)
except (OSError, ValueError, KeyError, TypeError, RuntimeError):
    raise SystemExit(1)
print("D519_PANEL_ENDPOINTS=PASS")
PY
  then
    READY=1
    break
  fi
  sleep 1
done
test "$READY" = "1" || die "new_panel_contract_not_ready"

# One live local GET of the actual new feature. The route is local-only and
# reads saved supplements; no new provider requests and no profile changes.
"$ROOT_PY" -I - <<'PY'
import json
from urllib.request import build_opener, ProxyHandler
o = build_opener(ProxyHandler({}))
url = ("http://127.0.0.1:8766/api/strategy-comparison"
       "?fast=10&mid=30&trend=60&retro=1&horizon=4&resolution=5m")
with o.open(url, timeout=120) as response:
    raw = response.read(2_000_001)
    assert response.status == 200 and len(raw) <= 2_000_000
r = json.loads(raw)
assert r["schema_version"] == "d512-archived-rest-strategy-comparison-v1"
assert r["retrospective_warmup_requested"] is True
assert r["out_of_sample_results_validated"] is False
assert r["orders_sent"] is False
e = r["exit_replay"]
assert e["schema_version"] == "d517-observed-ohlc-exit-scenarios-v1"
assert e["interval"] == "5m" and e["horizon_hours"] == 4
for flag in ("orders_sent", "execution_verified", "funding_settlement_verified",
             "liquidation_verified", "intrabar_path_verified", "financial_backtest_approved"):
    assert e[flag] is False
results = e["results"]
hourly = e["matched_hourly_reference"]
assert results.keys() == hourly.keys() and "reference_long" in results
for name, data in results.items():
    for key in ("candidate_count", "complete_path_count", "missing_path_count"):
        assert type(data[key]) is int and data[key] >= 0
    assert data["complete_path_count"] + data["missing_path_count"] == data["candidate_count"]
    assert data["complete_path_count"] == hourly[name]["complete_path_count"]
print("D519_RESEARCH_ENDPOINT=PASS")
print(json.dumps({"schema":"d519-release-research-readback-v1",
                  "resolution":"5m","horizon_hours":4,
                  "common_eligible_symbol_hours":r["common_eligible_symbol_hours"],
                  "covered_paths":{k:v["complete_path_count"] for k,v in results.items()},
                  "coverage_may_roll_forward":True,
                  "orders_sent":False},sort_keys=True,separators=(",",":")))
PY
owner_preflight
kill -0 "$LOCK_PID" || die "profile_lock_lost"
systemctl start "$MOTOR"
test "$(systemctl is-active "$MOTOR")" = "active" || die "new_motor_inactive"
test "$(systemctl is-active "$PANEL")" = "active" || die "new_panel_inactive"
test "$(systemctl is-active "$J1")" = "active" || die "J1_not_active_after_cutover"
ROLLBACK_ARMED=0
printf 'D519_RELEASE=PASS\n'
printf 'D519_CODE_SHA=%s\n' "$APPROVED_SHA"
printf 'D519_J1_UNTOUCHED=YES\n'
printf 'D519_LIVE_ORDERS=NO\n'
printf 'D519_OLD_CODE_AND_OVERRIDES_PRESERVED=YES\n'
printf 'D519_PROFILE_AND_LEDGER_NOT_REPLACED=YES\n'
printf 'D519_EXISTING_RESEARCH_SUPPLEMENTS_REUSED=YES\n'
printf 'D519_FUNDING_LIQUIDATION_OOS_NOT_VALIDATED=YES\n'

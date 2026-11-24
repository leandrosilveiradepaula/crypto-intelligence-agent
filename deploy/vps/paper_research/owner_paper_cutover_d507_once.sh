#!/usr/bin/env bash
# D507: explicit, reversible PAPER-only code cutover on srv1319424.
# No J1 service, trading credentials, order API, policy or SQLite writes.
# The cutover REQUIRES a fresh interactive human approval in this script.
set -Eeuo pipefail
umask 077

APPROVED_SHA="056845fdc46b8c2d1b08acd86be75e59dd368bac"
EXPECTED_HOST="srv1319424"
OWNER="cia-probe"
BASE="/home/cia-probe/agent"
PY="$BASE/ws-venv/bin/python"
PAPER="$BASE/d487-profile-20261123/paper_live"
POLICY="$BASE/d487-profile-20261123/strategy.json"
MOTOR="cia-paper-research-d498.service"
PANEL="cia-paper-config-d498.service"
J1="cia-j1-n50-ws.timer"
OLD_MOTOR="$BASE/d495-resident-20261123/repo"
OLD_PANEL="$BASE/d497-mobile-readback-20261123/repo"
MOTOR_DROP="/etc/systemd/system/$MOTOR.d/90-cia-d507-pinned.conf"
PANEL_DROP="/etc/systemd/system/$PANEL.d/90-cia-d507-pinned.conf"
ROLLBACK_ARMED=0

die() { printf 'D507_DENIED=%s\n' "$1" >&2; exit 1; }

rollback() {
  local rc="$?"
  if [ "$ROLLBACK_ARMED" = "1" ]; then
    printf 'D507_ROLLBACK=START rc=%s\n' "$rc" >&2
    rm -f -- "$MOTOR_DROP" "$PANEL_DROP" || true
    systemctl daemon-reload || true
    systemctl restart "$PANEL" || true
    systemctl start "$MOTOR" || true
    systemctl is-active "$MOTOR" "$PANEL" "$J1" || true
    printf 'D507_ROLLBACK=ATTEMPTED_VERIFY_UNITS\n' >&2
  fi
  exit "$rc"
}
trap rollback EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

test "$(id -u)" = "0" || die "root_shell_required"
test "$(hostname)" = "$EXPECTED_HOST" || die "wrong_host"
test -d "$BASE" && test ! -L "$BASE" || die "owner_home_missing_or_symlink"
test -x "$PY" || die "python_venv_unavailable"
command -v runuser >/dev/null || die "runuser_unavailable"
command -v git >/dev/null || die "git_unavailable"
command -v curl >/dev/null || die "curl_unavailable"
test ! -e "$MOTOR_DROP" && test ! -L "$MOTOR_DROP" || die "motor_override_already_exists"
test ! -e "$PANEL_DROP" && test ! -L "$PANEL_DROP" || die "panel_override_already_exists"
test "$(systemctl show -P User "$MOTOR")" = "$OWNER" || die "motor_owner_changed"
test "$(systemctl show -P User "$PANEL")" = "$OWNER" || die "panel_owner_changed"
test "$(systemctl show -P WorkingDirectory "$MOTOR")" = "$OLD_MOTOR" || die "motor_code_path_changed"
test "$(systemctl show -P WorkingDirectory "$PANEL")" = "$OLD_PANEL" || die "panel_code_path_changed"
test "$(systemctl is-active "$MOTOR")" = "active" || die "motor_inactive"
test "$(systemctl is-active "$PANEL")" = "active" || die "panel_inactive"
test "$(systemctl is-active "$J1")" = "active" || die "J1_not_active"

# Read only the existing localhost snapshot. Fail closed if new OPEN appears.
check_zero_open() {
  curl --fail --silent --show-error --max-time 7 \
    "http://127.0.0.1:8766/api/paper-session" |
    "$PY" -c '
import json, sys
s = json.load(sys.stdin)
if (s.get("status") != "paper_journal_readback"
        or s.get("orders_sent") is not False
        or type(s.get("open_position_count")) is not int
        or s["open_position_count"] != 0
        or type(s.get("position_count")) is not int
        or s["position_count"] < 1):
    sys.exit("D507_DENIED=nonzero_open_or_invalid_paper_session")
print("D507_PAPER_OPEN=0")
'
}

# The staged revision must remain PAPER-only, with no user config rewrite.
STAGE="$(mktemp -d "$BASE/d507-paper-cutover-XXXXXXXX")"
chown "$OWNER:$OWNER" "$STAGE"
chmod 0700 "$STAGE"
REPO="$STAGE/repo"
printf 'D507_STAGE_CREATED=owner_private\n'
runuser -u "$OWNER" -- env GIT_TERMINAL_PROMPT=0 \
  git clone --quiet --depth 10 --single-branch --branch main \
  "https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git" "$REPO"
runuser -u "$OWNER" -- git -C "$REPO" cat-file -e "$APPROVED_SHA^{commit}" ||
  die "pinned_revision_not_available"
runuser -u "$OWNER" -- git -C "$REPO" checkout --quiet --detach "$APPROVED_SHA"
test "$(runuser -u "$OWNER" -- git -C "$REPO" rev-parse HEAD)" = "$APPROVED_SHA" ||
  die "pinned_revision_mismatch"
test -z "$(runuser -u "$OWNER" -- git -C "$REPO" status --porcelain)" ||
  die "staged_code_not_clean"
printf 'D507_CODE_PIN=%s\n' "$APPROVED_SHA"

# Run the new D505 reader as the unprivileged owner. It performs no writes
# to the financial journal, policy, services or exchange.
runuser -u "$OWNER" -- env PYTHONPATH="$REPO" PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m scripts.preflight_paper_owner_d505 \
    --paper-directory "$PAPER" --policy-file "$POLICY"
check_zero_open
printf 'D507_PREFLIGHT=PASS_NO_SERVICE_CHANGED\n'
printf 'D507_SCOPE=only_two_paper_services;J1_not_modified;no_real_orders\n'

# A production service update is a separate human gate. Without this exact
# confirmation, only a private code clone and read-only checks have occurred.
printf '\n'
printf 'Para ATUALIZAR os dois servicos PAPER (sem J1 e sem ordens reais),\n'
printf 'digite exatamente: AUTORIZO CUTOVER PAPER\n'
printf 'Qualquer outra resposta encerra sem alterar os servicos.\n'
APPROVAL=""
if ! read -r -p 'Confirmacao: ' APPROVAL < /dev/tty; then
  printf 'D507_RELEASE=NOT_AUTHORIZED_NO_TTY\n'
  exit 0
fi
if [ "$APPROVAL" != "AUTORIZO CUTOVER PAPER" ]; then
  printf 'D507_RELEASE=NOT_AUTHORIZED\n'
  exit 0
fi
printf 'D507_RELEASE_AUTHORIZED=YES\n'

# A second check and stop prevent changing code underneath a live watcher.
check_zero_open
ROLLBACK_ARMED=1
systemctl stop "$MOTOR"
check_zero_open

# Override ONLY the source-code working directories, retaining the existing
# ExecStart, sandbox, write paths, capital policy and journals unchanged.
install -d -m 0755 "/etc/systemd/system/$MOTOR.d"
install -d -m 0755 "/etc/systemd/system/$PANEL.d"
printf '[Service]\nWorkingDirectory=%s\n' "$REPO" > "$MOTOR_DROP"
printf '[Service]\nWorkingDirectory=%s\n' "$REPO" > "$PANEL_DROP"
chmod 0644 "$MOTOR_DROP" "$PANEL_DROP"
systemctl daemon-reload
test "$(systemctl show -P WorkingDirectory "$MOTOR")" = "$REPO" ||
  die "motor_override_not_effective"
test "$(systemctl show -P WorkingDirectory "$PANEL")" = "$REPO" ||
  die "panel_override_not_effective"
systemctl start "$MOTOR"
systemctl restart "$PANEL"

# Verify the NEW endpoint (404 on the old code), integrity-checked history,
# current PAPER counts, and both services. Rollback if any check fails.
READY=0
for attempt in $(seq 1 20); do
  if curl --fail --silent --max-time 4 \
      "http://127.0.0.1:8766/api/paper-history?offset=0&limit=25" |
      "$PY" -c '
import json, sys
try:
    p = json.load(sys.stdin)
    assert p["schema_version"] == "d502-owner-paper-history-page-v1"
    assert p["orders_sent"] is False
    assert p["position_count"] >= 1
    assert len(p["positions"]) >= 1
except (ValueError, KeyError, TypeError, AssertionError):
    sys.exit(1)
' 2>/dev/null; then
    READY=1
    break
  fi
  sleep 1
done
test "$READY" = "1" || die "new_history_endpoint_not_ready"
test "$(systemctl is-active "$MOTOR")" = "active" || die "new_motor_not_active"
test "$(systemctl is-active "$PANEL")" = "active" || die "new_panel_not_active"
test "$(systemctl is-active "$J1")" = "active" || die "J1_not_active_after_cutover"

runuser -u "$OWNER" -- env PYTHONPATH="$REPO" PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m scripts.preflight_paper_owner_d505 \
    --paper-directory "$PAPER" --policy-file "$POLICY"
ROLLBACK_ARMED=0
printf 'D507_RELEASE=PASS\n'
printf 'D507_CODE_SHA=%s\n' "$APPROVED_SHA"
printf 'D507_HISTORY_ENDPOINT=HTTP200\n'
printf 'D507_J1_UNTOUCHED=YES\n'
printf 'D507_LIVE_ORDERS=NO\n'
printf 'D507_ROLLBACK_CODE_PATHS_PRESERVED=YES\n'

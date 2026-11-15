#!/usr/bin/env bash
# D359: owner-only, isolated, one-shot PIT Top50 research audit.
# Does not replace production code or systemd units, does not access SQLite,
# does not create orders, and must not be retried after a failed API census.
set -euo pipefail
umask 077

SHA="${1:-}"
OWNER=cia-probe
HOST=srv1319424
ORIGIN=https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git
BASE=/home/cia-probe/agent
PY="$BASE/ws-venv/bin/python"
WORK="$BASE/j1-d359-top50-pit-20261115T190130Z"
CODE="$WORK/code"
SCOPE="$WORK/scope"
TARGET_UTC=2026-11-15T19:01:30Z
RUNUSER=/usr/sbin/runuser
GIT=/usr/bin/git
SYSTEMCTL=/usr/bin/systemctl

if test "$(id -u)" != 0 || test "$(hostname)" != "$HOST"; then
  echo "D359_BLOCKED_EXPECTED_VPS_ROOT" >&2
  exit 77
fi
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "D359_BLOCKED_EXACT_SHA_REQUIRED" >&2
  exit 77
fi
test "$(/usr/bin/timedatectl show -p NTPSynchronized --value)" = yes
test -x "$PY"
test -d "$BASE"
test ! -L "$BASE"
test ! -e "$WORK"
test ! -L "$WORK"

for timer in cia-j1-n50-ws.timer cia-j1-n50-ws-rotate.timer; do
  test "$($SYSTEMCTL show "$timer" -p ActiveState --value)" = active
  test "$($SYSTEMCTL show "$timer" -p UnitFileState --value)" = enabled
done
test "$($SYSTEMCTL show cia-j1-rest-hourly.timer -p ActiveState --value)" = inactive
test "$($SYSTEMCTL show cia-j1-n50-managed.timer -p ActiveState --value)" = inactive

# Keep all audit code, public symbol manifest and receipts inaccessible to
# the gateway. No writes to any active epoch, service checkout or SQLite.
$RUNUSER -u "$OWNER" -- /usr/bin/install -d -m 0700 "$WORK"
$RUNUSER -u "$OWNER" -- /usr/bin/install -d -m 0700 "$SCOPE"
echo "D359_STAGE_PRIVATE_AUDIT_WORKSPACE_CREATED"

$RUNUSER -u "$OWNER" -- "$GIT" clone --quiet --no-checkout --depth 1 "$ORIGIN" "$CODE"
$RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" fetch --quiet --no-tags --depth 1 origin "$SHA"
test "$($RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" rev-parse FETCH_HEAD)" = "$SHA"
$RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" checkout --quiet --detach "$SHA"
test "$($RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" rev-parse HEAD)" = "$SHA"
test -z "$($RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" status --porcelain)"
test "$(stat -c %U "$CODE")" = "$OWNER"
test "$(stat -c %a "$CODE")" = 700
test -f "$CODE/docs/J1_TOP50_RANK_COVERAGE_AUDIT_D357.md"
test -f "$CODE/crypto_intelligence_agent/j1_auto_research_epoch.py"
test -f "$CODE/scripts/run_j1_current_ranked_epoch_once.py"
test -f "$CODE/tests/test_j1_auto_research_epoch.py"
echo "D359_STAGE_SHA_PIN_VERIFIED=$SHA"

# Same Python interpreter/dependencies as the owner WS, but NO production
# checkout modifications. Fail before GET on a regression.
for suite in \
  test_j1_auto_current_closed24h_once.py \
  test_j1_auto_research_epoch.py \
  test_j1_n50_ws_epoch_rotation_d321.py; do
  (cd "$CODE" && $RUNUSER -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m unittest discover -s tests -p "$suite" -q)
done
echo "D359_OFFLINE_OWNER_REGRESSION=PASS"

# Hard stop at this single preauthorized UTC hour; never roll silently into
# another hour or a future rotation. Census D286 requires HH:01..HH:15.
TARGET=$(/usr/bin/date -u -d "$TARGET_UTC" +%s)
NOW=$(/usr/bin/date -u +%s)
if (( NOW < TARGET )); then
  /usr/bin/sleep "$(( TARGET - NOW ))"
fi
NOW=$(/usr/bin/date -u +%s)
if (( NOW < TARGET || NOW > TARGET + 25 )) || \
   test "$(/usr/bin/date -u +%Y-%m-%dT%H)" != 2026-11-15T19; then
  echo "D359_PIT_WINDOW_MISSED_NO_GET"
  exit 76
fi
test "$($SYSTEMCTL show cia-j1-n50-ws-rotate.service -p ActiveState --value)" = inactive
test "$($SYSTEMCTL show cia-j1-n50-ws.timer -p ActiveState --value)" = active
test "$($SYSTEMCTL show cia-j1-n50-ws-rotate.timer -p ActiveState --value)" = active
echo "D359_PIT_CAPTURE_STARTED_UTC=$(/usr/bin/date -u +%Y-%m-%dT%H:%M:%SZ)"

# A single 372-GET (as budget allows) current full-catalog census. This
# single capture-seal operation is owner-only, requests public Bybit V5 data,
# and emits only sanitized aggregate fields. No retry and no trading.
REPORT="$(cd "$CODE" && $RUNUSER -u "$OWNER" -- /usr/bin/env PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m scripts.run_j1_current_ranked_epoch_once capture-seal \
    --manifest-directory "$SCOPE" \
    --allow-public-network \
    --confirm-region-and-personal-research \
    --allow-private-manifest-write)"

# Fail closed if the owner report lacks the D357 coverage fields.
printf '%s\n' "$REPORT" | /usr/bin/python3 -B -c '
import json, sys
try:
    data = json.load(sys.stdin)
    allowed = ("status", "requests_attempted", "network_accessed",
               "rank_closed_hour_end_ms", "rank_candidate_pool_count",
               "rank_complete_positive_24h_candidates",
               "rank_incomplete_24h_candidates",
               "rank_complete_zero_turnover_candidates",
               "rank_all_candidate_windows_complete24h",
               "rank_catalog_census_matches_before_after",
               "rank_candidate_pool_digest_sha256", "rank_digest_sha256",
               "selection_closed_hour_end_ms", "scope_digest_sha256",
               "manifest_written", "database_modified", "orders_sent",
               "marketwide_top50_verified", "live_trading_authorized")
    safe = {key: data.get(key) for key in allowed}
    if (data.get("status") != "sealed_current_auto_rank_research_scope_only"
            or data.get("manifest_written") is not True
            or data.get("database_modified") is not False
            or data.get("orders_sent") is not False
            or data.get("marketwide_top50_verified") is not False
            or data.get("live_trading_authorized") is not False
            or data.get("rank_catalog_census_matches_before_after") is not True
            or type(data.get("rank_candidate_pool_count")) is not int
            or type(data.get("rank_complete_positive_24h_candidates")) is not int
            or type(data.get("rank_incomplete_24h_candidates")) is not int
            or type(data.get("rank_complete_zero_turnover_candidates")) is not int
            or data["rank_candidate_pool_count"] !=
                (data["rank_complete_positive_24h_candidates"] +
                 data["rank_incomplete_24h_candidates"] +
                 data["rank_complete_zero_turnover_candidates"])):
        print("D359_REPORT_INVALID_OR_ABSTAIN", file=sys.stderr)
        raise SystemExit(77)
    print("D359_SANITIZED_RESULT=" +
          json.dumps(safe, sort_keys=True, separators=(",", ":")))
    if (data["rank_all_candidate_windows_complete24h"] is not True
            or data["rank_incomplete_24h_candidates"] != 0):
        print("D359_POOL_COMPLETENESS=INCOMPLETE_RESEARCH_ONLY")
        raise SystemExit(3)
    print("D359_POOL_COMPLETENESS=PASS_RESEARCH_ONLY")
except (ValueError, TypeError, KeyError, OverflowError):
    print("D359_REPORT_PARSE_REJECTED", file=sys.stderr)
    raise SystemExit(77)
'
echo "D359_AUDIT_FINISHED_UTC=$(/usr/bin/date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "D359_VPS_WS_TIMERS_AND_SQLITE_UNTOUCHED=true"

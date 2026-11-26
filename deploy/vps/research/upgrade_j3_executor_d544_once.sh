#!/bin/bash
# D544: owner-authorized, one-shot upgrade of the existing fixed research executor.
# Run locally as administrator ONLY after the reviewed, integrated SHA passes CI.
set -euo pipefail
umask 077

test "$(id -u)" -eq 0
test "$#" -eq 5
OLD_SHA="$1"
NEW_SHA="$2"
RUN_SHA="$3"
UNIT_SHA="$4"
LOCK="$5"

[[ "$OLD_SHA" =~ ^[0-9a-f]{40}$ && "$NEW_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$RUN_SHA" =~ ^[0-9a-f]{64}$ && "$UNIT_SHA" =~ ^[0-9a-f]{64}$ ]]
test "$OLD_SHA" != "$NEW_SHA"

DEST=/opt/cia-j3-research
UNIT=/etc/systemd/system/cia-j3-research@.service
REPO=https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git

root_controlled() {
  test ! -L "$1"
  test "$(stat -c %u -- "$1")" = 0
  local mode
  mode="$(stat -c %a -- "$1")"
  (( (8#$mode & 022) == 0 ))
}

test -d "$DEST/repo"
test -f "$DEST/run.sh"
test -f "$UNIT"
for PATHNAME in /opt "$DEST" "$DEST/repo" "$DEST/run.sh" "$UNIT"; do
  root_controlled "$PATHNAME"
done

test "$(sha256sum "$DEST/run.sh" | cut -d ' ' -f 1)" = "$RUN_SHA"
test "$(sha256sum "$UNIT" | cut -d ' ' -f 1)" = "$UNIT_SHA"
test "$(git -C "$DEST/repo" rev-parse HEAD)" = "$OLD_SHA"

# The lock must be the existing owner lock, explicitly supplied locally.
# Read-only open; never create, truncate, replace or alter ownership.
test -f "$LOCK"
test ! -L "$LOCK"
test "$(basename "$LOCK")" = d539-history.lock
test "$(stat -c %u "$LOCK")" = "$(id -u cia-probe)"
test "$(stat -c %a "$LOCK")" = 600
exec 9<"$LOCK"
flock -n -x 9 || { echo RESEARCH_BUSY; exit 75; }

ACTIVE="$(systemctl list-units --type=service --state=active,activating,deactivating \
  --no-legend --plain 'cia-j3-research@*.service' 'cia-j3-history-*.service')"
test -z "$ACTIVE" || { echo RESEARCH_BUSY; exit 75; }

export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_TERMINAL_PROMPT=0

STAGE="$(mktemp -d "$DEST/.d544-upgrade-XXXXXXXX")"
chmod 0700 "$STAGE"
MOVED=0
RUNNER_SWAPPED=0
COMMITTED=0

rollback() {
  local rc=$?
  trap - EXIT
  if [ "$COMMITTED" -ne 1 ]; then
    if [ "$RUNNER_SWAPPED" -eq 1 ]; then
      mv -- "$STAGE/old-run.sh" "$DEST/run.sh"
    fi
    if [ "$MOVED" -eq 1 ]; then
      if [ -d "$DEST/repo" ]; then
        mv -- "$DEST/repo" "$STAGE/rejected-repo"
      fi
      mv -- "$STAGE/old-repo" "$DEST/repo"
    fi
    echo D544_UPGRADE_NOT_COMMITTED
  fi
  exit "$rc"
}
trap rollback EXIT

# Everything staged is root controlled; the new code is pinned, not a moving branch.
git init --quiet "$STAGE/new-repo"
git -C "$STAGE/new-repo" remote add origin "$REPO"
git -C "$STAGE/new-repo" fetch --quiet --depth 1 --no-tags origin "$NEW_SHA"
git -C "$STAGE/new-repo" -c core.hooksPath=/dev/null checkout --quiet --detach FETCH_HEAD
test "$(git -C "$STAGE/new-repo" rev-parse HEAD)" = "$NEW_SHA"

# Isolated stdlib helper only; no owner paths or arbitrary commands are evaluated.
python3 -I "$STAGE/new-repo/scripts/prepare_j3_executor_upgrade_d544.py" \
  --old "$DEST/run.sh" --expected-sha256 "$RUN_SHA" --output "$STAGE/new-run.sh"
bash -n "$STAGE/new-run.sh"

# Root-controlled code must be readable by the existing unprivileged service.
chmod -R a+rX,go-w "$STAGE/new-repo"
chmod 0755 "$STAGE/new-run.sh"
cp -p -- "$DEST/run.sh" "$STAGE/old-run.sh"

# Preserve old files for recovery. Nothing under the owner's data tree is changed.
mv -- "$DEST/repo" "$STAGE/old-repo"
MOVED=1
mv -- "$STAGE/new-repo" "$DEST/repo"
mv -- "$STAGE/new-run.sh" "$DEST/run.sh"
RUNNER_SWAPPED=1

test "$(sha256sum "$UNIT" | cut -d ' ' -f 1)" = "$UNIT_SHA"
test "$(git -C "$DEST/repo" rev-parse HEAD)" = "$NEW_SHA"
systemctl start --wait cia-j3-research@probe.service
COMMITTED=1
echo D544_UPGRADE_PASS
echo "BACKUP=$STAGE"

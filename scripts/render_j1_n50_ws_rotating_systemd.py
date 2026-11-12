"""D321: inert rendering of future rotating WS units; no install/enable."""
from __future__ import annotations

from pathlib import Path

from scripts.render_j1_n50_managed_systemd import OWNER_RE,PATH_RE

ROOT=Path(__file__).resolve().parents[1]/"deploy"/"systemd"
_EXPECTED_EPOCH_ROOT="/home/cia-probe/agent/j1-n50-ws-epochs"
_EXPECTED_STATE=_EXPECTED_EPOCH_ROOT+"/active"
_FILES=(
    "cia-j1-n50-ws-rotating.service.template",
    "cia-j1-n50-ws-rotate.timer.template",
    "cia-j1-n50-ws-rotate.service.template",
)


def render_rotating_ws_systemd(
    *,owner:str,repo:str,python:str,epoch_root:str,state_directory:str,
)->tuple[str,str,str]:
    """Root release may use these validated bytes only at a separate gate."""
    if (type(owner) is not str or OWNER_RE.fullmatch(owner) is None
            or owner=="root"
            or type(epoch_root) is not str
            or type(state_directory) is not str
            or epoch_root!=_EXPECTED_EPOCH_ROOT
            or state_directory!=_EXPECTED_STATE):
        raise ValueError("N50 WS rotation owner/path mismatch")
    for value in (repo,python,epoch_root,state_directory):
        if (type(value) is not str or PATH_RE.fullmatch(value) is None
                or ".." in Path(value).parts):
            raise ValueError("N50 WS rotating path unsafe")
    if repo in (epoch_root,state_directory) or python in (epoch_root,state_directory):
        raise ValueError("N50 WS rotating checkout overlaps private state")

    units=[(ROOT/name).read_text(encoding="ascii") for name in _FILES]
    mapping={
        "@OWNER@":owner,"@REPO@":repo,"@PYTHON@":python,
        "@EPOCH_ROOT@":epoch_root,"@STATE_DIR@":state_directory,
    }
    for a,b in mapping.items():
        units=[u.replace(a,b) for u in units]
    ws,timer,rotator=units
    if any("@" in u for u in units):
        raise ValueError("N50 WS unrendered placeholder")
    if not all((
        ws.count("ExecStart=")==1,
        ws.count("ExecStartPre=")==1,
        "scripts.run_j1_n50_ws_owner_active_once" in ws,
        " --state-directory "+state_directory+" " in ws,
        "ReadWritePaths="+epoch_root+"\n" in ws,
        "OnFailure=cia-j1-n50-ws-fallback.service\n" in ws,
        "scripts.run_j1_n50_managed_once" not in ws,
        "scripts.run_j1_n50_ws_owner_cached_once" not in ws,
        "scripts.rotate_j1_n50_ws_epoch_once" in rotator,
        " --epoch-root "+epoch_root+" " in rotator,
        "ReadWritePaths="+epoch_root+"\n" in rotator,
        rotator.count("ExecStart=")==1,
        "OnCalendar=*-*-* *:01:15 UTC\n" in timer,
        "Persistent=false\n" in timer,
        "AccuracySec=1s\n" in timer,
        "Unit=cia-j1-n50-ws-rotate.service\n" in timer,
        "systemctl" not in "".join(units),
        "cia-j1-n50-managed.timer" not in "".join(units),
        "ExecStartPre="+python+
        " -m scripts.preflight_j1_n50_ws_systemd"
        " --require-old-collectors-quiesced\n" in ws,
        "ExecStartPre="+python+
        " -m scripts.preflight_j1_n50_ws_systemd"
        " --require-old-collectors-quiesced\n" in rotator,
    )):
        raise ValueError("N50 WS rotating units invariant failed")
    return ws,timer,rotator

"""D295: render inert N50 managed service/timer; never install or start."""
from __future__ import annotations
import argparse
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent.parent / "deploy" / "systemd"
OWNER_RE=re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
PATH_RE=re.compile(r"/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\Z")


def render_n50_managed_systemd(
    *, owner: str, repo: str, python: str, root: str,
) -> tuple[str,str]:
    if (type(owner) is not str or OWNER_RE.fullmatch(owner) is None
            or owner == "root"):
        raise ValueError("unsafe_n50_owner")
    paths=(repo,python,root)
    if (any(type(p) is not str or PATH_RE.fullmatch(p) is None
            or ".." in Path(p).parts or len(p)>230 for p in paths)
            or len(set(paths))!=3):
        raise ValueError("unsafe_n50_service_path")
    rp,py,storage = (Path(p) for p in paths)
    if (rp in storage.parents or storage in rp.parents
            or py in storage.parents or storage in py.parents):
        raise ValueError("n50_root_overlaps_code")
    service=(ROOT/"cia-j1-n50-managed.service.template").read_text("ascii")
    timer=(ROOT/"cia-j1-n50-managed.timer.template").read_text("ascii")
    for name,value in (("OWNER",owner),("REPO",repo),
                       ("PYTHON",python),("ROOT",root)):
        service=service.replace("@"+name+"@",value)
    if "@" in service or "@" in timer:
        raise ValueError("n50_template_unrendered")
    if (service.count("ExecStart=")!=1 or service.count("ExecStartPre=")!=1
            or "User="+owner+"\n" not in service
            or "ReadWritePaths="+root+"\n" not in service
            or "--enable-managed-n50-tick" not in service
            or "ExecStartPre="+python+
               " -m scripts.preflight_j1_n50_systemd_isolation --require-n2-quiesced\n"
               not in service
            or "OnCalendar=*-*-* *:01:05 UTC\n" not in timer
            or "Persistent=false\n" not in timer
            or "Unit=cia-j1-n50-managed.service\n" not in timer):
        raise ValueError("n50_template_invariant_failed")
    return service,timer


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner",required=True)
    p.add_argument("--repo",required=True)
    p.add_argument("--python",required=True)
    p.add_argument("--root",required=True)
    args=p.parse_args(argv)
    service,timer=render_n50_managed_systemd(**vars(args))
    print("# SERVICE - NOT INSTALLED\n"+service+
          "\n# TIMER - NOT INSTALLED\n"+timer)
    return 0


if __name__=="__main__":
    raise SystemExit(main())

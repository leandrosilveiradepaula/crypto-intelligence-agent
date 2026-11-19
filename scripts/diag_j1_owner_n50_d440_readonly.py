"""D440: safely diagnose current owner J1 epoch without importing deployed code.

Run only as cia-probe with Python -I -B, via a verified owner-readable stdin.
No network calls, writes, symbol output, source paths or provider prices.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

BASE = Path("/home/cia-probe/agent")
REPO = BASE / "repo"
ROOT = BASE / "j1-n50-ws-epochs"
STATE = ROOT / "active"
POINTER = STATE / "active-n50-ws-epoch.json"
RANK_FILE = "j1-auto-ranked-research-scope-v1.json"
CACHE_FILE = "ws-dynamic-n50-admission.json"
MAX_AGE_MS = 48 * 3_600_000
SHA = re.compile(r"[a-f0-9]{64}\Z")


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key")
        out[key] = value
    return out


def secure_owner_file(path: Path, limit: int) -> dict:
    """Strict owner/0700 parent + owner/0600 regular file, no symlinks."""
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
        raise ValueError("unsafe path")
    parent = path.parent.lstat()
    before = path.lstat()
    owner = os.geteuid()
    if (owner == 0 or parent.st_uid != owner or before.st_uid != owner
            or not stat.S_ISDIR(parent.st_mode)
            or stat.S_IMODE(parent.st_mode) != 0o700
            or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or not 1 <= before.st_size <= limit):
        raise ValueError("unsafe owner file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        inside = os.fstat(fd)
        raw = os.read(fd, limit + 1)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (inside.st_dev, inside.st_ino, inside.st_size, inside.st_mtime_ns) != (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
    ) or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
    ) or len(raw) != before.st_size:
        raise ValueError("changed owner file")
    result = json.loads(raw.decode("ascii"), object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(
                            ValueError("nonfinite")))
    if type(result) is not dict:
        raise ValueError("invalid JSON")
    return result


def safe_epoch_directory(value: object) -> Path:
    if type(value) is not str or len(value) > 300:
        raise ValueError("invalid directory")
    path = Path(value)
    if (not path.is_absolute() or path == STATE or ROOT not in path.parents
            or path.is_symlink() or path.resolve(strict=True) != path):
        raise ValueError("outside owner epoch directory")
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("unsafe directory")
    return path


def age_status(now_ms: int, observed_ms: object) -> str:
    if type(observed_ms) is not int or observed_ms <= 0:
        return "INVALID_TIMESTAMP"
    age = now_ms - observed_ms
    if age < 0:
        return "FUTURE_TIMESTAMP"
    return "EXPIRED_48H" if age > MAX_AGE_MS else "WITHIN_48H"


def report() -> dict:
    out = {
        "OWNER_DIAG": "READ_ONLY_NO_NETWORK",
        "OWNER_REPO_HEAD": "UNAVAILABLE",
        "DEPLOYED_EPOCH_MODULE": "ABSENT",
        "POINTER": "NOT_CHECKED",
        "MANIFEST": "NOT_CHECKED",
        "METADATA_CACHE": "NOT_CHECKED",
        "EPOCH_BINDING": "NOT_CHECKED",
        "J1_MODIFIED": "NO",
        "ORDERS_SENT": "NO",
    }
    if os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() == 0:
        out["POINTER"] = "NONROOT_OWNER_REQUIRED"
        return out
    try:
        result = subprocess.run(
            ["/usr/bin/git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        value = result.stdout.strip()
        if result.returncode == 0 and re.fullmatch(r"[a-f0-9]{40}", value):
            out["OWNER_REPO_HEAD"] = value
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    out["DEPLOYED_EPOCH_MODULE"] = (
        "PRESENT" if (REPO / "crypto_intelligence_agent"
                      / "j1_n50_ws_epoch_rotation.py").is_file() else "ABSENT"
    )
    try:
        pointer = secure_owner_file(POINTER, 4096)
        keys = {
            "schema_version", "manifest_directory", "ws_directory",
            "ranked_scope_sha256", "ws_metadata_sha256",
            "activated_at_ms", "pointer_sha256",
        }
        if (set(pointer) != keys
                or pointer["schema_version"] != "j1-n50-ws-active-owner-epoch-v1"
                or any(type(pointer[k]) is not str or not SHA.fullmatch(pointer[k])
                       for k in ("ranked_scope_sha256", "ws_metadata_sha256",
                                 "pointer_sha256"))
                or sha256(canonical({k: v for k, v in pointer.items()
                                     if k != "pointer_sha256"})).hexdigest()
                       != pointer["pointer_sha256"]):
            raise ValueError("invalid pointer digest")
        out["POINTER"] = "STRUCTURE_AND_DIGEST_VALID"
    except FileNotFoundError:
        out["POINTER"] = "MISSING"
        return out
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError):
        out["POINTER"] = "MISSING_OR_INVALID"
        return out
    now = time.time_ns() // 1_000_000
    out["POINTER_CLOCK"] = (
        "VALID" if type(pointer.get("activated_at_ms")) is int
        and 0 < pointer["activated_at_ms"] <= now else "INVALID_OR_FUTURE")
    try:
        manifest_dir = safe_epoch_directory(pointer["manifest_directory"])
        ws_dir = safe_epoch_directory(pointer["ws_directory"])
        if manifest_dir == ws_dir:
            raise ValueError("overlapping directories")
    except (OSError, ValueError, TypeError):
        out["EPOCH_BINDING"] = "DIRECTORIES_MISSING_OR_UNSAFE"
        return out

    manifest = None
    try:
        manifest = secure_owner_file(manifest_dir / RANK_FILE, 20_000)
        out["MANIFEST"] = age_status(now, manifest.get("catalog_post_observed_at_ms"))
        if (out["MANIFEST"] == "WITHIN_48H"
                and manifest.get("scope_digest_sha256")
                    != pointer["ranked_scope_sha256"]):
            out["MANIFEST"] = "RANK_DIGEST_MISMATCH"
    except FileNotFoundError:
        out["MANIFEST"] = "MISSING"
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError):
        out["MANIFEST"] = "MISSING_OR_INVALID"

    cached = None
    try:
        cached = secure_owner_file(ws_dir / CACHE_FILE, 8_000_000)
        payload = cached.get("payload")
        if type(payload) is not dict or type(cached.get("payload_sha256")) is not str:
            raise ValueError("cache shape")
        if sha256(canonical(payload)).hexdigest() != cached["payload_sha256"]:
            raise ValueError("cache digest")
        out["METADATA_CACHE"] = age_status(now, payload.get("captured_at_ms"))
        if (cached.get("ranked_scope_sha256") != pointer["ranked_scope_sha256"]
                or cached.get("metadata_sha256") != pointer["ws_metadata_sha256"]):
            out["METADATA_CACHE"] = "METADATA_DIGEST_MISMATCH"
    except FileNotFoundError:
        out["METADATA_CACHE"] = "MISSING"
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError):
        out["METADATA_CACHE"] = "MISSING_OR_INVALID"

    if (out["MANIFEST"] == "WITHIN_48H"
            and out["METADATA_CACHE"] == "WITHIN_48H"):
        out["EPOCH_BINDING"] = "BASIC_TIMES_AND_DIGESTS_MATCH"
    else:
        out["EPOCH_BINDING"] = "NOT_CURRENTLY_VERIFIABLE"
    return out


def main() -> None:
    for key, value in report().items():
        print("D440_" + key + "=" + value, flush=True)


if __name__ == "__main__":
    main()

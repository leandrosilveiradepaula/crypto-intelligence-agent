"""Generate D544 runner from the exact locally installed D541 source.

Offline text transformation only, no shell execution, no path discovery or
permission changes. Root installer must independently verify the old digest.
"""
import argparse
import hashlib
from pathlib import Path


def updated_runner(old, expected_sha256):
    if hashlib.sha256(old).hexdigest()!=expected_sha256:
        raise ValueError("unexpected installed runner digest")
    src=old.decode("utf-8")
    def replace(a,b):
        nonlocal src
        if src.count(a)!=1:
            raise ValueError("D541 runner contract mismatch")
        src=src.replace(a,b)
    replace('  echo "D541_OWNER_PROBE=PASS"',
            '  "$PY" -m scripts.summarize_j3_financial_evidence_d542 --help >/dev/null\n'
            '  "$PY" -m scripts.run_j3_long_history_d528 --help >/dev/null\n'
            '  echo "D544_OWNER_PROBE=PASS"')
    replace("    --max-gets 100","    --max-gets 50")
    replace('      --oldest-first','      --exact-missing')
    replace('elif [ "$TASK" = replay-annual ]; then',
            'elif [ "$TASK" = summary-annual ]; then\n\n'
            '  "$PY" -m scripts.summarize_j3_financial_evidence_d542 \\\n'
            '    --annual-directory "$OUT" --compact\n\n'
            'elif [ "$TASK" = replay-annual ]; then')
    replace("    --maintenance-stress-bps 50 100 150 \\\n",
            "    --maintenance-stress-bps 50 100 150 \\\n"
            "    --exposure-diagnostics \\\n")
    return src.encode("utf-8")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old",type=Path,required=True)
    p.add_argument("--expected-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.old.stat().st_size>65536 or a.output.exists():
        raise ValueError("D544 invalid runner size or output already exists")
    a.output.write_bytes(updated_runner(a.old.read_bytes(),a.expected_sha256))


if __name__=="__main__":
    main()

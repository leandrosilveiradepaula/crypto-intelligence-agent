"""D546 offline transformation of an exact D544 runner; no service changes."""
import argparse
import hashlib
from pathlib import Path


def updated_runner(old,expected_sha256):
    if hashlib.sha256(old).hexdigest()!=expected_sha256:
        raise ValueError("unexpected installed runner digest")
    src=old.decode("utf-8")
    def replace(a,b):
        nonlocal src
        if src.count(a)!=1:
            raise ValueError("D544 runner contract mismatch")
        src=src.replace(a,b)
    replace('  echo "D544_OWNER_PROBE=PASS"',
            '  "$PY" -m scripts.run_j3_history_campaign_d546 --help >/dev/null\n'
            '  echo "D546_OWNER_PROBE=PASS"')
    replace('elif [ "$TASK" = summary-annual ]; then',
            'elif [[ "$TASK" =~ ^campaign-trade-5m-(365|730)$ ]]; then\n'
            '  DAYS="${BASH_REMATCH[1]}"\n'
            '  "$PY" -m scripts.run_j3_history_campaign_d546 \\\n'
            '    --directory "$HISTORY" --days "$DAYS" \\\n'
            '    --allow-public-network --confirm-personal-readonly-research \\\n'
            '    --confirm-region-eligible --confirm-public-data-rights\n\n'
            'elif [ "$TASK" = summary-annual ]; then')
    return src.encode("utf-8")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old",type=Path,required=True)
    p.add_argument("--expected-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.old.stat().st_size>65536 or a.output.exists():
        raise ValueError("invalid runner size or output already exists")
    a.output.write_bytes(updated_runner(a.old.read_bytes(),a.expected_sha256))


if __name__=="__main__":
    main()

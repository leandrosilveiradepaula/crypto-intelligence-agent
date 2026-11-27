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
    # D547 groups mark acquisition and fine replay into the same administrative upgrade.
    replace('  echo "D546_OWNER_PROBE=PASS"',
            '  "$PY" -m scripts.run_j3_research_d547 --help >/dev/null\n'
            '  echo "D546_OWNER_PROBE=PASS"\n'
            '  echo "D547_OWNER_PROBE=PASS"')
    replace('elif [ "$TASK" = summary-annual ]; then',
            "elif [ \"$TASK\" = campaign-mark-5m-365 ]; then\n  \"$PY\" -m scripts.run_j3_research_d547 \\\n    --directory \"$HISTORY\" --task campaign-mark-5m-365 \\\n    --allow-public-network --confirm-personal-readonly-research \\\n    --confirm-region-eligible --confirm-public-data-rights\n\nelif [ \"$TASK\" = preflight-annual-5m ]; then\n  \"$PY\" -m scripts.run_j3_research_d547 \\\n    --directory \"$HISTORY\" --task preflight-annual-5m\n\nelif [ \"$TASK\" = summary-annual-5m ]; then\n  \"$PY\" -m scripts.summarize_j3_financial_evidence_d542 \\\n    --report \"$OUT/annual5m-d547.json\" --compact\n\nelif [ \"$TASK\" = replay-annual-5m ]; then\n  REPORT=\"$OUT/annual5m-d547.json\"\n  test ! -e \"$REPORT\" && test ! -L \"$REPORT\" || {\n    echo D547_REPORT_EXISTS\n    exit 2\n  }\n  \"$PY\" -m scripts.run_j3_research_d547 \\\n    --directory \"$HISTORY\" --task preflight-annual-5m\n  TMP=\"$(mktemp \"$OUT/annual5m-d547-tmp-XXXXXXXX.json\")\"\n  \"$PY\" -m scripts.run_j3_long_replay_d529 \\\n    --directory \"$HISTORY\" --policy-file \"$POLICY\" \\\n    --days 365 --partition development --preserve-recent-90d \\\n    --matrix-file docs/examples/d530_entry_controls_matrix.json \\\n    --entry-experiments-file docs/examples/d532_squeeze_optimization.json \\\n    --exit-experiments-file docs/examples/d533_runner_experiments.json \\\n    --strategy-names squeeze_bb_20_2_strict squeeze_bb_20_2_strict_rsi \\\n      sq_w04_v2 sq_w04_v15 sq_sma_30_60 sq_sma_10_30 sq_ema_9_21 sq_pivot \\\n    --horizon-hours 48 168 720 1440 2160 \\\n    --research-max-horizon-hours 2160 --stop-grid-bps 150 --resolution 5m \\\n    --target-diagnostics --separate-open-mark --observed-funding \\\n    --maintenance-stress-bps 50 100 150 --exposure-diagnostics \\\n    > \"$TMP\" || { echo D547_REPLAY_FAILED_PRIVATE_REPORT_PRESERVED; exit 1; }\n  \"$PY\" -m scripts.summarize_j3_financial_evidence_d542 --report \"$TMP\" --compact\n  ln -- \"$TMP\" \"$REPORT\"\n  rm -- \"$TMP\"\n  echo D547_FINE_REPLAY=PASS\n\n" +
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

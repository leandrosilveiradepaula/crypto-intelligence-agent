"""D400: bounded offline CPU/memory profiling of the EXISTING D396 N50 proof.

Not a network throughput test, not a service or live performance claim.
No provider data, prices, symbols, credentials, or private positions in output.
"""
from __future__ import annotations

import argparse
import json
import time
import tracemalloc

from scripts.demo_public_n50_coverage_d396 import run_demo

MAX_RUNS = 20


def run_benchmark(runs: int = 5) -> dict:
    if type(runs) is not int or not 1 <= runs <= MAX_RUNS:
        raise ValueError("D400 runs must be an integer between 1 and 20")
    elapsed_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    tracemalloc.start()
    frames = epochs = 0
    try:
        for _ in range(runs):
            result = run_demo()  # exactly two synthetic N50 epochs, no network
            if (result["schema_version"] != "bybit-public-n50-coverage-pilot-d396-v1"
                    or result["status"] != "finite_samples_observed_not_continuous"
                    or result["all_observed_coverage"] is not True
                    or result["attempted_epochs"] != 2
                    or result["continuous_24x7_verified"] is not False
                    or result["orders_sent"] is not False):
                raise RuntimeError("D400 fixture coverage invalid or changed")
            for epoch in result["epochs"]:
                if (epoch["ranked_count"] != 50
                        or epoch["usable_ranked_observed"] != 50
                        or epoch["usable_monitored_observed"] != epoch["monitored_count"]
                        or epoch["fresh_monitored_at_lease_end"] != epoch["monitored_count"]):
                    raise RuntimeError("D400 fixture no longer covers complete cohort")
                frames += epoch["ticker_frames_accepted"]
                epochs += 1
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    elapsed_ns = time.perf_counter_ns() - elapsed_start
    cpu_ns = time.process_time_ns() - cpu_start
    if elapsed_ns <= 0 or cpu_ns < 0 or frames <= 0:
        raise RuntimeError("D400 invalid local measurement")
    return {
        "schema_version": "bybit-public-offline-resource-d400-v1",
        "status": "offline_synthetic_resource_sample",
        "runs": runs, "epochs": epochs,
        "ranked_per_epoch": 50,
        "ticker_frames_accepted": frames,
        "elapsed_wall_ms": round(elapsed_ns / 1_000_000, 3),
        "process_cpu_ms": round(cpu_ns / 1_000_000, 3),
        "tracemalloc_peak_bytes": peak_bytes,
        "synthetic_frames_per_wall_second": round(frames * 1_000_000_000 / elapsed_ns, 3),
        "measurement_scope": "python_d396_two_epoch_inprocess_fixture",
        "includes_socket_and_os_rss": False,
        "real_network_latency_or_load_verified": False,
        "continuous_24x7_verified": False,
        "marketwide_top50_verified": False,
        "orders_sent": False,
        "order_submission_enabled": False,
        "approved_for_live_use": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="D400 benchmark strictly offline N50 fixture")
    p.add_argument("--runs", type=int, default=5)
    args = p.parse_args(argv)
    try:
        result = run_benchmark(args.runs)
    except (ValueError, RuntimeError) as exc:
        p.error(str(exc))
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

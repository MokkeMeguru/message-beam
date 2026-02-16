"""パラメータグリッドサーチ。"""

import csv
import itertools
import time

from simulator.config import SimulationConfig
from simulator.engine import PipelineSimulator

# 探索するパラメータ空間
PARAM_GRID = {
    "num_keys": [1, 2, 3, 5, 10, 20],
    "batch_size": [20, 25, 30, 35, 40, 50, 75],
    "max_buffering_duration_secs": [0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
    "max_concurrent_sends": [1, 2, 3, 5, 10],
    "send_sleep_secs": [0.0, 0.3, 0.5, 0.8, 1.0, 1.5],
}

DEFAULT_OUTPUT_CSV = "exploration_results.csv"
DEFAULT_DURATION = 30.0

_SUMMARY_HEADER = (
    f"{'keys':>5} {'batch':>6} {'buffer':>7} "
    f"{'concur':>7} {'sleep':>6} "
    f"{'max/3s':>7} {'avg/3s':>7} {'tput':>8} {'pending':>8}"
)


def _format_row(r: dict) -> str:
    return (
        f"{r['num_keys']:>5} {r['batch_size']:>6} "
        f"{r['max_buffering_duration_secs']:>7} "
        f"{r['max_concurrent_sends']:>7} "
        f"{r.get('send_sleep_secs', '-'):>6} "
        f"{r['max_requests_in_window']:>7} "
        f"{r['avg_requests_in_window']:>7} "
        f"{float(r['throughput']):>8.1f} "
        f"{r['pending_messages']:>8}"
    )


def run_grid_search(
    output_csv: str = DEFAULT_OUTPUT_CSV,
    duration: float = DEFAULT_DURATION,
) -> str:
    """グリッドサーチを実行し、結果を CSV に出力する。"""
    keys_list = sorted(PARAM_GRID.keys())
    combinations = list(
        itertools.product(*(PARAM_GRID[k] for k in keys_list))
    )
    total = len(combinations)

    print(f"Total combinations: {total}")
    print(f"Output: {output_csv}")
    print()

    fieldnames = [
        "num_keys",
        "batch_size",
        "max_buffering_duration_secs",
        "max_concurrent_sends",
        "send_sleep_secs",
        "max_requests_in_window",
        "avg_requests_in_window",
        "throughput",
        "total_delivered",
        "total_batches",
        "pending_messages",
        "constraint_violated",
    ]

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        satisfied_count = 0
        start_time = time.time()

        for i, values in enumerate(combinations):
            params = dict(zip(keys_list, values))

            config = SimulationConfig(
                input_rate=4000.0,
                num_keys=params["num_keys"],
                batch_size=params["batch_size"],
                max_buffering_duration_secs=params[
                    "max_buffering_duration_secs"
                ],
                max_concurrent_sends=params["max_concurrent_sends"],
                send_sleep_secs=params["send_sleep_secs"],
                simulation_duration=duration,
                window_secs=3.0,
                window_max_requests=165,
            )

            sim = PipelineSimulator(config, seed=42)
            result = sim.run()

            row = {
                "num_keys": params["num_keys"],
                "batch_size": params["batch_size"],
                "max_buffering_duration_secs": params[
                    "max_buffering_duration_secs"
                ],
                "max_concurrent_sends": params["max_concurrent_sends"],
                "send_sleep_secs": params["send_sleep_secs"],
                "max_requests_in_window": result.max_requests_in_window,
                "avg_requests_in_window": round(
                    result.avg_requests_in_window, 1
                ),
                "throughput": round(result.throughput, 1),
                "total_delivered": result.total_messages_delivered,
                "total_batches": result.total_batches_sent,
                "pending_messages": result.pending_messages,
                "constraint_violated": result.constraint_violated,
            }
            writer.writerow(row)

            if not result.constraint_violated:
                satisfied_count += 1

            if (i + 1) % 100 == 0 or (i + 1) == total:
                elapsed = time.time() - start_time
                eta = elapsed / (i + 1) * (total - i - 1)
                print(
                    f"  [{i+1}/{total}] "
                    f"elapsed={elapsed:.1f}s "
                    f"ETA={eta:.1f}s "
                    f"satisfied={satisfied_count}/{i+1}",
                    flush=True,
                )

    elapsed = time.time() - start_time
    print()
    print(f"Completed in {elapsed:.1f}s")
    print(f"Constraint satisfied: {satisfied_count}/{total}")
    print(f"Results saved to {output_csv}")
    return output_csv


def print_summary(output_csv: str = DEFAULT_OUTPUT_CSV):
    """CSV から結果を読み込み、サマリーを表示する。"""
    rows = []
    with open(output_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    satisfied = [r for r in rows if r["constraint_violated"] == "False"]
    violated = [r for r in rows if r["constraint_violated"] == "True"]

    print(f"\n{'='*80}")
    print("EXPLORATION SUMMARY")
    print(f"{'='*80}")
    print(f"Total combinations: {len(rows)}")
    print(f"Constraint satisfied (< 165 reqs/3s): {len(satisfied)}")
    print(f"Constraint violated (>= 165 reqs/3s): {len(violated)}")

    if satisfied:
        satisfied.sort(
            key=lambda r: float(r["throughput"]), reverse=True
        )
        print(
            "\n--- Top 20 (highest throughput, constraint satisfied) ---"
        )
        print(_SUMMARY_HEADER)
        print("-" * 80)
        for r in satisfied[:20]:
            print(_format_row(r))

    if violated:
        violated.sort(key=lambda r: int(r["max_requests_in_window"]))
        print("\n--- Near-miss (just over 165 reqs/3s) ---")
        print(_SUMMARY_HEADER)
        print("-" * 80)
        for r in violated[:10]:
            print(_format_row(r))

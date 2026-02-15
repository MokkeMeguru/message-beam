"""
Dataflow ハイパーパラメータのグリッドサーチ探索。

simulation.py のシミュレータを使い、パラメータ空間を網羅的に探索する。
結果を CSV に出力し、制約 (3 秒ウィンドウで 165 件未満) を満たす組み合わせを特定する。
"""

import csv
import itertools
import sys
import time

from simulation import PipelineSimulator, SimulationConfig

# 探索するパラメータ空間
PARAM_GRID = {
    "num_keys": [1, 2, 3, 5, 10, 20],
    "batch_size": [20, 25, 30, 35, 40],
    "max_buffering_duration_secs": [0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
    "max_concurrent_sends": [1, 2, 3, 5, 10],
}

OUTPUT_CSV = "exploration_results.csv"
SIMULATION_DURATION = 30.0  # 各シナリオ 30 秒間シミュレート


def run_exploration():
    """グリッドサーチを実行し、結果を CSV に出力する。"""
    keys_list = sorted(PARAM_GRID.keys())
    combinations = list(itertools.product(*(PARAM_GRID[k] for k in keys_list)))
    total = len(combinations)

    print(f"Total combinations: {total}")
    print(f"Output: {OUTPUT_CSV}")
    print()

    fieldnames = [
        "num_keys",
        "batch_size",
        "max_buffering_duration_secs",
        "max_concurrent_sends",
        "max_messages_in_window",
        "avg_messages_in_window",
        "throughput",
        "total_delivered",
        "total_batches",
        "pending_messages",
        "constraint_violated",
    ]

    with open(OUTPUT_CSV, "w", newline="") as f:
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
                max_buffering_duration_secs=params["max_buffering_duration_secs"],
                max_concurrent_sends=params["max_concurrent_sends"],
                simulation_duration=SIMULATION_DURATION,
                window_secs=3.0,
                window_max_messages=165,
            )

            sim = PipelineSimulator(config, seed=42)
            result = sim.run()

            row = {
                "num_keys": params["num_keys"],
                "batch_size": params["batch_size"],
                "max_buffering_duration_secs": params["max_buffering_duration_secs"],
                "max_concurrent_sends": params["max_concurrent_sends"],
                "max_messages_in_window": result.max_messages_in_window,
                "avg_messages_in_window": round(result.avg_messages_in_window, 1),
                "throughput": round(result.throughput, 1),
                "total_delivered": result.total_messages_delivered,
                "total_batches": result.total_batches_sent,
                "pending_messages": result.pending_messages,
                "constraint_violated": result.constraint_violated,
            }
            writer.writerow(row)

            if not result.constraint_violated:
                satisfied_count += 1

            if (i + 1) % 50 == 0 or (i + 1) == total:
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
    print(f"Results saved to {OUTPUT_CSV}")


def print_summary():
    """CSV から結果を読み込み、サマリーを表示する。"""
    rows = []
    with open(OUTPUT_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # 制約を満たす組み合わせ
    satisfied = [r for r in rows if r["constraint_violated"] == "False"]
    violated = [r for r in rows if r["constraint_violated"] == "True"]

    print(f"\n{'='*70}")
    print(f"EXPLORATION SUMMARY")
    print(f"{'='*70}")
    print(f"Total combinations: {len(rows)}")
    print(f"Constraint satisfied (< 165 msgs/3s): {len(satisfied)}")
    print(f"Constraint violated (>= 165 msgs/3s): {len(violated)}")

    if satisfied:
        # スループットが高い順にソート
        satisfied.sort(key=lambda r: float(r["throughput"]), reverse=True)

        print(f"\n--- Top 20 configurations (highest throughput, constraint satisfied) ---")
        print(
            f"{'keys':>5} {'batch':>6} {'buffer':>7} {'concur':>7} "
            f"{'max/3s':>7} {'avg/3s':>7} {'tput':>8} {'pending':>8}"
        )
        print("-" * 70)
        for r in satisfied[:20]:
            print(
                f"{r['num_keys']:>5} {r['batch_size']:>6} "
                f"{r['max_buffering_duration_secs']:>7} "
                f"{r['max_concurrent_sends']:>7} "
                f"{r['max_messages_in_window']:>7} "
                f"{r['avg_messages_in_window']:>7} "
                f"{float(r['throughput']):>8.1f} "
                f"{r['pending_messages']:>8}"
            )

    if violated:
        # ウィンドウ最大が 165 に最も近いもの (ギリギリ超過)
        violated.sort(key=lambda r: int(r["max_messages_in_window"]))

        print(f"\n--- Near-miss configurations (just over 165 msgs/3s) ---")
        print(
            f"{'keys':>5} {'batch':>6} {'buffer':>7} {'concur':>7} "
            f"{'max/3s':>7} {'avg/3s':>7} {'tput':>8} {'pending':>8}"
        )
        print("-" * 70)
        for r in violated[:10]:
            print(
                f"{r['num_keys']:>5} {r['batch_size']:>6} "
                f"{r['max_buffering_duration_secs']:>7} "
                f"{r['max_concurrent_sends']:>7} "
                f"{r['max_messages_in_window']:>7} "
                f"{r['avg_messages_in_window']:>7} "
                f"{float(r['throughput']):>8.1f} "
                f"{r['pending_messages']:>8}"
            )


if __name__ == "__main__":
    if "--summary" in sys.argv:
        print_summary()
    else:
        run_exploration()
        print_summary()

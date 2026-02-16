"""argparse エントリポイント。"""

import argparse
import sys

from simulator.config import SimulationConfig
from simulator.engine import PipelineSimulator


def _cmd_simulate(args: argparse.Namespace) -> None:
    """単一シミュレーション実行。"""
    config = SimulationConfig(
        input_rate=args.input_rate,
        num_keys=args.num_keys,
        batch_size=args.batch_size,
        max_buffering_duration_secs=args.buffer_duration,
        max_concurrent_sends=args.max_concurrent,
        api_latency_min=args.api_latency_min,
        api_latency_max=args.api_latency_max,
        send_sleep_secs=args.send_sleep,
        simulation_duration=args.duration,
    )
    sim = PipelineSimulator(config, seed=args.seed)
    result = sim.run()

    print("=== Simulation Result ===")
    print(
        f"Config: keys={config.num_keys}, batch={config.batch_size}, "
        f"buffer={config.max_buffering_duration_secs}s, "
        f"concurrency={config.max_concurrent_sends}, "
        f"sleep={config.send_sleep_secs}s"
    )
    print(
        f"Max requests in {config.window_secs}s window: "
        f"{result.max_requests_in_window}"
    )
    print(
        f"Avg requests in {config.window_secs}s window: "
        f"{result.avg_requests_in_window:.1f}"
    )
    print(f"Throughput: {result.throughput:.1f} msg/s")
    print(f"Total delivered: {result.total_messages_delivered}")
    print(f"Total batches: {result.total_batches_sent}")
    print(f"Pending: {result.pending_messages}")
    print(f"Constraint violated: {result.constraint_violated}")


def _cmd_explore(args: argparse.Namespace) -> None:
    """グリッドサーチ実行。"""
    from simulator.explore import print_summary, run_grid_search

    if args.summary:
        print_summary(args.output)
    else:
        run_grid_search(output_csv=args.output, duration=args.duration)
        print_summary(args.output)


def _cmd_charts(args: argparse.Namespace) -> None:
    """Mermaid チャート生成。"""
    from simulator.charts import (
        batch_chart,
        concurrency_chart,
        throughput_chart,
        workers_chart,
    )

    generators = {
        "concurrency": concurrency_chart,
        "batch": batch_chart,
        "workers": workers_chart,
        "throughput": throughput_chart,
    }

    if args.chart == "all":
        charts = list(generators.keys())
    else:
        charts = [args.chart]

    sections = []
    for name in charts:
        sections.append(f"## {name}\n")
        sections.append(generators[name]())
        sections.append("")

    output = "\n".join(sections)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output + "\n")
        print(f"Charts written to {args.output}")
    else:
        print(output)


def build_parser() -> argparse.ArgumentParser:
    """ArgumentParser を構築する。"""
    parser = argparse.ArgumentParser(
        prog="simulator",
        description="Dataflow パイプラインの離散イベントシミュレータ",
    )
    sub = parser.add_subparsers(dest="command")

    # --- simulate ---
    sim_p = sub.add_parser("simulate", help="単一シミュレーション実行")
    sim_p.add_argument("--input-rate", type=float, default=4000.0)
    sim_p.add_argument("--num-keys", type=int, default=10)
    sim_p.add_argument("--batch-size", type=int, default=40)
    sim_p.add_argument("--buffer-duration", type=float, default=2.0)
    sim_p.add_argument("--max-concurrent", type=int, default=5)
    sim_p.add_argument("--api-latency-min", type=float, default=0.0)
    sim_p.add_argument("--api-latency-max", type=float, default=1.0)
    sim_p.add_argument("--send-sleep", type=float, default=0.0)
    sim_p.add_argument("--duration", type=float, default=30.0)
    sim_p.add_argument("--seed", type=int, default=42)

    # --- explore ---
    exp_p = sub.add_parser("explore", help="グリッドサーチ実行")
    exp_p.add_argument(
        "--output", default="exploration_results.csv", help="CSV 出力先"
    )
    exp_p.add_argument(
        "--summary", action="store_true", help="サマリーのみ表示"
    )
    exp_p.add_argument("--duration", type=float, default=30.0)

    # --- charts ---
    ch_p = sub.add_parser("charts", help="Mermaid チャート生成")
    ch_p.add_argument(
        "--chart",
        default="all",
        choices=["all", "concurrency", "batch", "workers", "throughput"],
    )
    ch_p.add_argument("--output", default=None, help="Markdown 出力先")

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI エントリポイント。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "simulate": _cmd_simulate,
        "explore": _cmd_explore,
        "charts": _cmd_charts,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()

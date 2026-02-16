"""Mermaid xychart-beta チャート生成。"""

from simulator.config import SimulationConfig
from simulator.engine import PipelineSimulator


def _run_sim(**kwargs) -> dict:
    """シミュレーションを実行して結果を dict で返す。"""
    config = SimulationConfig(**kwargs)
    sim = PipelineSimulator(config, seed=42)
    r = sim.run()
    return {
        "max_req_3s": r.max_requests_in_window,
        "avg_req_3s": r.avg_requests_in_window,
        "throughput": r.throughput,
        "violated": r.constraint_violated,
    }


def concurrency_chart() -> str:
    """同時送信数 vs スループット / リクエスト数。"""
    concurrencies = [1, 2, 3, 5, 10]
    throughputs = []
    max_reqs = []

    for c in concurrencies:
        r = _run_sim(
            num_keys=3,
            batch_size=50,
            max_buffering_duration_secs=2.0,
            max_concurrent_sends=c,
            send_sleep_secs=0.0,
        )
        throughputs.append(round(r["throughput"], 1))
        max_reqs.append(r["max_req_3s"])

    x = ", ".join(f'"{c}"' for c in concurrencies)
    tp = ", ".join(str(v) for v in throughputs)
    rq = ", ".join(str(v) for v in max_reqs)

    return f"""\
```mermaid
xychart-beta
    title "同時送信数 vs スループット / max req(3s)"
    x-axis "同時送信数" [{x}]
    y-axis "件数"
    bar "throughput (msg/s)" [{tp}]
    bar "max req/3s" [{rq}]
```"""


def batch_chart() -> str:
    """バッチサイズ vs スループット (concurrency=5)。"""
    batches = [20, 30, 40, 50, 75]
    throughputs = []
    max_reqs = []

    for bs in batches:
        r = _run_sim(
            num_keys=3,
            batch_size=bs,
            max_buffering_duration_secs=2.0,
            max_concurrent_sends=5,
            send_sleep_secs=0.0,
        )
        throughputs.append(round(r["throughput"], 1))
        max_reqs.append(r["max_req_3s"])

    x = ", ".join(f'"{bs}"' for bs in batches)
    tp = ", ".join(str(v) for v in throughputs)
    rq = ", ".join(str(v) for v in max_reqs)

    return f"""\
```mermaid
xychart-beta
    title "バッチサイズ vs スループット (concurrency=5)"
    x-axis "batch_size" [{x}]
    y-axis "件数"
    bar "throughput (msg/s)" [{tp}]
    bar "max req/3s" [{rq}]
```"""


def workers_chart() -> str:
    """ワーカー数 vs スループット (batch=20, keys=8)。"""
    workers = [1, 2, 3, 4, 5, 6, 8]
    throughputs = []
    max_reqs = []

    for w in workers:
        r = _run_sim(
            num_keys=8,
            batch_size=20,
            max_buffering_duration_secs=2.0,
            max_concurrent_sends=w,
            send_sleep_secs=0.0,
        )
        throughputs.append(round(r["throughput"], 1))
        max_reqs.append(r["max_req_3s"])

    x = ", ".join(f'"{w}"' for w in workers)
    tp = ", ".join(str(v) for v in throughputs)
    rq = ", ".join(str(v) for v in max_reqs)
    limit = ", ".join(["165"] * len(workers))

    return f"""\
```mermaid
xychart-beta
    title "ワーカー数 vs スループット (batch=20, keys=8)"
    x-axis "workers" [{x}]
    y-axis "件数"
    bar "throughput (msg/s)" [{tp}]
    bar "max req/3s" [{rq}]
    line "制約 165 req/3s" [{limit}]
```"""


def throughput_chart() -> str:
    """おすすめ構成スループット比較。"""
    configs = [
        ("b75/c10", dict(
            num_keys=5, batch_size=75, max_concurrent_sends=10,
            send_sleep_secs=0.0, max_buffering_duration_secs=2.0,
        )),
        ("b50/c10", dict(
            num_keys=5, batch_size=50, max_concurrent_sends=10,
            send_sleep_secs=0.0, max_buffering_duration_secs=2.0,
        )),
        ("b20/c8", dict(
            num_keys=8, batch_size=20, max_concurrent_sends=8,
            send_sleep_secs=0.0, max_buffering_duration_secs=2.0,
        )),
        ("b20/c3", dict(
            num_keys=8, batch_size=20, max_concurrent_sends=3,
            send_sleep_secs=0.0, max_buffering_duration_secs=2.0,
        )),
    ]

    labels = []
    throughputs = []
    max_reqs = []

    for label, kw in configs:
        r = _run_sim(**kw)
        labels.append(label)
        throughputs.append(round(r["throughput"], 1))
        max_reqs.append(r["max_req_3s"])

    x = ", ".join(f'"{l}"' for l in labels)
    tp = ", ".join(str(v) for v in throughputs)
    rq = ", ".join(str(v) for v in max_reqs)
    limit = ", ".join(["165"] * len(labels))

    return f"""\
```mermaid
xychart-beta
    title "おすすめ構成比較"
    x-axis "構成" [{x}]
    y-axis "件数"
    bar "throughput (msg/s)" [{tp}]
    bar "max req/3s" [{rq}]
    line "制約 165 req/3s" [{limit}]
```"""

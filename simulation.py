"""
Dataflow パイプラインの離散イベントシミュレーション。

Beam の GroupIntoBatches + 外部 API 送信をモデル化し、
3 秒スライディングウィンドウでのメッセージ到達数を計測する。
"""

import heapq
import random
from dataclasses import dataclass, field


@dataclass
class SimulationConfig:
    """シミュレーションのハイパーパラメータ。"""

    # 入力レート (msg/s)
    input_rate: float = 4000.0
    # ランダムキー数 (AddRandomKeyFn の範囲)
    num_keys: int = 10
    # GroupIntoBatches のバッチサイズ
    batch_size: int = 40
    # GroupIntoBatches のバッファリングタイムアウト (秒)
    max_buffering_duration_secs: float = 2.0
    # 最大同時 API 送信数 (ワーカー並列度)
    max_concurrent_sends: int = 5
    # API レイテンシ範囲 (秒)
    api_latency_min: float = 0.0
    api_latency_max: float = 1.0
    # シミュレーション時間 (秒)
    simulation_duration: float = 30.0
    # レート制約: ウィンドウサイズ (秒)
    window_secs: float = 3.0
    # レート制約: ウィンドウ内の最大メッセージ数
    window_max_messages: int = 165


@dataclass
class SimulationResult:
    """シミュレーション結果。"""

    config: SimulationConfig
    # 3 秒ウィンドウ内の最大メッセージ数
    max_messages_in_window: int = 0
    # 3 秒ウィンドウ内の平均メッセージ数
    avg_messages_in_window: float = 0.0
    # 総処理メッセージ数
    total_messages_delivered: int = 0
    # 総バッチ送信回数
    total_batches_sent: int = 0
    # 実効スループット (msg/s)
    throughput: float = 0.0
    # 制約違反があったか
    constraint_violated: bool = False
    # 未処理メッセージ数 (バッファ残)
    pending_messages: int = 0


# イベント種別
EVENT_MESSAGE_ARRIVE = 0
EVENT_BATCH_READY = 1
EVENT_SEND_COMPLETE = 2
EVENT_BUFFER_TIMEOUT = 3


@dataclass(order=True)
class Event:
    time: float
    event_type: int = field(compare=False)
    key: int = field(compare=False, default=-1)
    data: dict = field(compare=False, default_factory=dict)


class PipelineSimulator:
    """Beam パイプラインの離散イベントシミュレータ。"""

    def __init__(self, config: SimulationConfig, seed: int = 42):
        self.config = config
        self.rng = random.Random(seed)

        # イベントキュー
        self.event_queue: list[Event] = []

        # キーごとのバッファ
        self.key_buffers: dict[int, list[float]] = {
            k: [] for k in range(config.num_keys)
        }
        # キーごとのバッファ開始時刻 (最初のメッセージが入った時刻)
        self.key_buffer_start: dict[int, float | None] = {
            k: None for k in range(config.num_keys)
        }
        # キーごとのタイムアウトイベント登録済みフラグ
        self.key_timeout_scheduled: dict[int, float | None] = {
            k: None for k in range(config.num_keys)
        }

        # 送信中のバッチ数
        self.active_sends: int = 0
        # 送信待ちキュー (batch_size 分溜まったが送信枠がないバッチ)
        self.send_queue: list[tuple[int, int]] = []  # (key, count)

        # メッセージ配信記録 [(timestamp, count)]
        self.deliveries: list[tuple[float, int]] = []

        # 統計
        self.total_delivered: int = 0
        self.total_batches: int = 0
        self.total_arrived: int = 0

    def run(self) -> SimulationResult:
        """シミュレーション実行。"""
        cfg = self.config

        # メッセージ到着イベントをスケジュール
        interval = 1.0 / cfg.input_rate
        t = 0.0
        while t < cfg.simulation_duration:
            key = self.rng.randint(0, cfg.num_keys - 1)
            heapq.heappush(
                self.event_queue,
                Event(time=t, event_type=EVENT_MESSAGE_ARRIVE, key=key),
            )
            t += interval

        # イベントループ
        while self.event_queue:
            event = heapq.heappop(self.event_queue)

            if event.time > cfg.simulation_duration + 10:
                # シミュレーション時間 + 余裕分を超えたら終了
                break

            if event.event_type == EVENT_MESSAGE_ARRIVE:
                self._handle_message_arrive(event)
            elif event.event_type == EVENT_SEND_COMPLETE:
                self._handle_send_complete(event)
            elif event.event_type == EVENT_BUFFER_TIMEOUT:
                self._handle_buffer_timeout(event)

        # 結果集計
        return self._compute_result()

    def _handle_message_arrive(self, event: Event):
        """メッセージ到着を処理。"""
        cfg = self.config
        key = event.key
        self.total_arrived += 1

        self.key_buffers[key].append(event.time)

        # バッファ開始時刻を記録
        if self.key_buffer_start[key] is None:
            self.key_buffer_start[key] = event.time
            # タイムアウトイベントをスケジュール
            timeout_time = event.time + cfg.max_buffering_duration_secs
            self.key_timeout_scheduled[key] = timeout_time
            heapq.heappush(
                self.event_queue,
                Event(
                    time=timeout_time, event_type=EVENT_BUFFER_TIMEOUT, key=key
                ),
            )

        # バッチサイズに達したら送信
        if len(self.key_buffers[key]) >= cfg.batch_size:
            self._try_send_batch(key, event.time)

    def _handle_buffer_timeout(self, event: Event):
        """バッファリングタイムアウトを処理。"""
        key = event.key

        # このタイムアウトが最新のものか確認
        if self.key_timeout_scheduled[key] != event.time:
            return

        if len(self.key_buffers[key]) > 0:
            self._try_send_batch(key, event.time)

    def _try_send_batch(self, key: int, current_time: float):
        """バッチ送信を試行。"""
        cfg = self.config
        buf = self.key_buffers[key]

        if len(buf) == 0:
            return

        count = min(len(buf), cfg.batch_size)

        if self.active_sends < cfg.max_concurrent_sends:
            # 送信実行
            self.active_sends += 1
            # バッファからメッセージを取り出す
            self.key_buffers[key] = buf[count:]

            # バッファ状態をリセット
            if len(self.key_buffers[key]) > 0:
                self.key_buffer_start[key] = current_time
                timeout_time = current_time + cfg.max_buffering_duration_secs
                self.key_timeout_scheduled[key] = timeout_time
                heapq.heappush(
                    self.event_queue,
                    Event(
                        time=timeout_time,
                        event_type=EVENT_BUFFER_TIMEOUT,
                        key=key,
                    ),
                )
            else:
                self.key_buffer_start[key] = None
                self.key_timeout_scheduled[key] = None

            # API レイテンシ
            latency = self.rng.uniform(
                cfg.api_latency_min, cfg.api_latency_max
            )
            complete_time = current_time + latency

            heapq.heappush(
                self.event_queue,
                Event(
                    time=complete_time,
                    event_type=EVENT_SEND_COMPLETE,
                    key=key,
                    data={"count": count},
                ),
            )
        else:
            # 送信枠がない場合はキューに追加
            self.send_queue.append((key, count))
            # バッファからは取り出しておく
            self.key_buffers[key] = buf[count:]
            if len(self.key_buffers[key]) > 0:
                self.key_buffer_start[key] = current_time
                timeout_time = current_time + cfg.max_buffering_duration_secs
                self.key_timeout_scheduled[key] = timeout_time
                heapq.heappush(
                    self.event_queue,
                    Event(
                        time=timeout_time,
                        event_type=EVENT_BUFFER_TIMEOUT,
                        key=key,
                    ),
                )
            else:
                self.key_buffer_start[key] = None
                self.key_timeout_scheduled[key] = None

    def _handle_send_complete(self, event: Event):
        """送信完了を処理。"""
        count = event.data["count"]
        self.active_sends -= 1
        self.total_delivered += count
        self.total_batches += 1
        self.deliveries.append((event.time, count))

        # 送信待ちキューから次のバッチを送信
        if self.send_queue and self.active_sends < self.config.max_concurrent_sends:
            next_key, next_count = self.send_queue.pop(0)
            self.active_sends += 1

            latency = self.rng.uniform(
                self.config.api_latency_min, self.config.api_latency_max
            )
            complete_time = event.time + latency

            heapq.heappush(
                self.event_queue,
                Event(
                    time=complete_time,
                    event_type=EVENT_SEND_COMPLETE,
                    key=next_key,
                    data={"count": next_count},
                ),
            )

    def _compute_result(self) -> SimulationResult:
        """結果を集計。"""
        cfg = self.config

        if not self.deliveries:
            return SimulationResult(
                config=cfg,
                pending_messages=sum(
                    len(b) for b in self.key_buffers.values()
                ),
            )

        # 3 秒スライディングウィンドウの集計
        window_counts = []
        step = 0.1  # 100ms ステップでウィンドウをスライド
        max_time = self.deliveries[-1][0]
        t = 0.0
        while t <= max_time:
            window_start = t
            window_end = t + cfg.window_secs
            count = sum(
                c
                for ts, c in self.deliveries
                if window_start <= ts < window_end
            )
            window_counts.append(count)
            t += step

        max_in_window = max(window_counts) if window_counts else 0
        avg_in_window = (
            sum(window_counts) / len(window_counts) if window_counts else 0
        )

        pending = sum(len(b) for b in self.key_buffers.values())
        pending += sum(c for _, c in self.send_queue)

        effective_duration = min(max_time, cfg.simulation_duration)
        throughput = (
            self.total_delivered / effective_duration
            if effective_duration > 0
            else 0
        )

        return SimulationResult(
            config=cfg,
            max_messages_in_window=max_in_window,
            avg_messages_in_window=avg_in_window,
            total_messages_delivered=self.total_delivered,
            total_batches_sent=self.total_batches,
            throughput=throughput,
            constraint_violated=max_in_window >= cfg.window_max_messages,
            pending_messages=pending,
        )


if __name__ == "__main__":
    # サンプル実行
    config = SimulationConfig()
    sim = PipelineSimulator(config)
    result = sim.run()

    print(f"=== Simulation Result ===")
    print(f"Config: keys={config.num_keys}, batch={config.batch_size}, "
          f"buffer={config.max_buffering_duration_secs}s, "
          f"concurrency={config.max_concurrent_sends}")
    print(f"Max messages in {config.window_secs}s window: "
          f"{result.max_messages_in_window}")
    print(f"Avg messages in {config.window_secs}s window: "
          f"{result.avg_messages_in_window:.1f}")
    print(f"Throughput: {result.throughput:.1f} msg/s")
    print(f"Total delivered: {result.total_messages_delivered}")
    print(f"Total batches: {result.total_batches_sent}")
    print(f"Pending: {result.pending_messages}")
    print(f"Constraint violated: {result.constraint_violated}")

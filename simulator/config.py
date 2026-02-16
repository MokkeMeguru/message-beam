"""シミュレーション設定。"""

from dataclasses import dataclass


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
    # 送信後の強制 sleep (秒) — DoFn 内で time.sleep() を入れる想定
    send_sleep_secs: float = 0.0
    # シミュレーション時間 (秒)
    simulation_duration: float = 30.0
    # レート制約: ウィンドウサイズ (秒)
    window_secs: float = 3.0
    # レート制約: ウィンドウ内の最大リクエスト数
    window_max_requests: int = 165

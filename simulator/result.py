"""シミュレーション結果。"""

from dataclasses import dataclass

from simulator.config import SimulationConfig


@dataclass
class SimulationResult:
    """シミュレーション結果。"""

    config: SimulationConfig
    # 3 秒ウィンドウ内の最大リクエスト数 (API 呼び出し回数)
    max_requests_in_window: int = 0
    # 3 秒ウィンドウ内の平均リクエスト数
    avg_requests_in_window: float = 0.0
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

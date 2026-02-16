import random
import time
import threading
from collections import deque

from flask import Flask, request
import logging

app = Flask(__name__)

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MockServer")

# --- 3 秒スライディングウィンドウの計測 (リクエスト回数) ---
WINDOW_SECS = 3.0
request_log: deque[float] = deque()  # リクエスト到着時刻
request_lock = threading.Lock()
max_in_window = 0


def _count_window() -> int:
    """現在の 3 秒ウィンドウ内のリクエスト数を返す。"""
    now = time.time()
    cutoff = now - WINDOW_SECS
    with request_lock:
        while request_log and request_log[0] < cutoff:
            request_log.popleft()
        return len(request_log)


@app.route("/batch-endpoint", methods=["POST"])
def receive_batch():
    global max_in_window

    data = request.json
    items = data.get("items", [])
    count = len(items)

    # API レイテンシをシミュレート (0~1 秒)
    latency = random.uniform(0.0, 1.0)
    time.sleep(latency)

    # リクエスト記録 (1 回の API 呼び出し = 1 カウント)
    now = time.time()
    with request_lock:
        request_log.append(now)

    window_count = _count_window()
    if window_count > max_in_window:
        max_in_window = window_count

    constraint = "OK" if window_count < 165 else "NG"

    logger.info(
        f"Batch: {count} items | "
        f"Window(3s): {window_count} reqs [{constraint}] | "
        f"Max: {max_in_window} | "
        f"Latency: {latency:.2f}s"
    )

    return {"status": "ok"}, 200


@app.route("/stats", methods=["GET"])
def stats():
    """現在の統計を返す。"""
    window_count = _count_window()
    return {
        "window_3s_current": window_count,
        "window_3s_max": max_in_window,
        "total_requests": len(request_log),
        "constraint_165_reqs": "OK" if max_in_window < 165 else "NG",
    }


if __name__ == "__main__":
    app.run(port=9000)

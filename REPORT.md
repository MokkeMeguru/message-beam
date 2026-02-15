# Dataflow ハイパーパラメータ探索レポート

## 調査目的

以下の条件下で、外部サーバが 3 秒間に受け取るメッセージ数を 165 件未満に抑える Dataflow パラメータの組み合わせを探索する。

| 項目 | 値 |
| --- | --- |
| 入力レート | 4,000 msg/s (Pub/Sub 経由) |
| バッチサイズ | 20〜40 件/バッチ |
| 外部 API レイテンシ | 0〜1 秒 (一様分布) |
| 制約 | 3 秒スライディングウィンドウで 165 件未満 |

## 調査手法

離散イベントシミュレーション (`simulation.py`) を構築し、4 つのパラメータについてグリッドサーチを実施した。

### 探索パラメータ

| パラメータ | 探索範囲 | 説明 |
| --- | --- | --- |
| `num_keys` | 1, 2, 3, 5, 10, 20 | `AddRandomKeyFn` のキー数 |
| `batch_size` | 20, 25, 30, 35, 40 | `GroupIntoBatches` のバッチサイズ |
| `max_buffering_duration_secs` | 0.5, 1, 2, 3, 5, 10 | バッファリングタイムアウト |
| `max_concurrent_sends` | 1, 2, 3, 5, 10 | 同時 API 送信数 (ワーカー並列度) |

合計 900 通りの組み合わせを各 30 秒間シミュレートした。

## 結果

### 制約を満たす組み合わせ: 0 / 900

900 通りすべてで 3 秒ウィンドウ内の最大メッセージ数が 165 を超過した。

### 同時送信数ごとの傾向

| 同時送信数 | ウィンドウ最大 (最小〜最大) | 平均スループット |
| --- | --- | --- |
| 1 | 200〜440 | 87.3 msg/s |
| 2 | 340〜720 | 167.7 msg/s |
| 3 | 480〜1,000 | 241.7 msg/s |
| 5 | 760〜1,600 | 405.6 msg/s |
| 10 | 1,380〜2,960 | 804.1 msg/s |

同時送信数が 1 の場合でもウィンドウ最大は 200 に達する。

### 同時送信数 = 1 での上位組み合わせ

最もウィンドウ最大が小さかった組み合わせは以下のとおり。

| keys | batch | buffer | max/3s | avg/3s | throughput |
| --- | --- | --- | --- | --- | --- |
| 3 | 20 | 0.5s | 200 | 113.3 | 52.7 msg/s |
| 3 | 20 | 1.0s | 200 | 113.3 | 52.7 msg/s |
| 1 | 20 | 0.5s | 220 | 134.0 | 61.3 msg/s |
| 5 | 20 | 0.5s | 220 | 128.2 | 58.0 msg/s |

平均は 165 件未満だが、API レイテンシのばらつきによるバーストで瞬間的に超過する。

### バースト発生メカニズム

`keys=3, batch_size=20, max_concurrent_sends=1` の配信タイムライン。

```text
time(s)  count  window[t-3, t]
  0.157     20      20
  0.660     20      40
  0.909     20      60
  1.647     20      80
  1.972     20     100
  2.232     20     120   ← 2.2 秒で 120 件到達
  3.170     20     100   ← ウィンドウがスライドし減少
```

API レイテンシが短い送信 (0.15s, 0.25s 等) が連続すると、3 秒ウィンドウ内に多くのバッチが集中する。
レイテンシの一様分布 (0〜1s) では、一定確率で短レイテンシが連続するため、バーストは避けられない。

## 根本原因の分析

### 1. 入力レートと出力制約のミスマッチ

```text
入力:  4,000 msg/s
制約:  165 msg / 3s = 55 msg/s
比率:  4,000 / 55 = 72.7 倍
```

入力レートが出力制約の約 73 倍あるため、単一パイプラインではメッセージが際限なく滞留する。
30 秒のシミュレーションで約 118,000 件の未処理メッセージが残った。

### 2. API レイテンシの分散によるバースト

同時送信数を 1 に絞っても、レイテンシが 0 に近い送信が連続すると瞬間的にレートが跳ね上がる。
Beam の `GroupIntoBatches` はバッチの「サイズ」と「待機時間」のみ制御でき、**送信レート (単位時間あたりの送信数)** は制御しない。

### 3. GroupIntoBatches の限界

`GroupIntoBatches` は以下を保証する。

- バッチ内のメッセージ数が `batch_size` 以下
- バッファリング時間が `max_buffering_duration_secs` 以下

しかし、以下は保証しない。

- 単位時間あたりの出力バッチ数
- スライディングウィンドウ内の総メッセージ数

## 推奨対策

### 対策 1: SendBatchToApiFn にレートリミッターを実装する

`GroupIntoBatches` のパラメータだけでは制約を満たせないため、送信側で明示的に流量制御を行う。

```python
import time
import threading

class RateLimiter:
    """トークンバケットによるレートリミッター。"""

    def __init__(self, max_messages: int, window_secs: float):
        self.max_messages = max_messages
        self.window_secs = window_secs
        self.timestamps: list[float] = []
        self.lock = threading.Lock()

    def acquire(self, count: int):
        while True:
            with self.lock:
                now = time.time()
                cutoff = now - self.window_secs
                self.timestamps = [
                    t for t in self.timestamps if t > cutoff
                ]
                current = sum(1 for _ in self.timestamps)
                if current + count <= self.max_messages:
                    self.timestamps.extend([now] * count)
                    return
            time.sleep(0.1)
```

### 対策 2: Dataflow ワーカー数でスケールアウトする

1 ワーカーあたりの出力レートを制約内に収め、ワーカー数でスループットを稼ぐ。

```text
必要ワーカー数 = 入力レート / 1 ワーカーの処理レート
             = 4,000 / 55
             ≈ 73 ワーカー
```

各ワーカーが独立したレートリミッターを持ち、外部サーバの負荷分散と組み合わせる。

### 対策 3: Pub/Sub のフロー制御を活用する

Pub/Sub の `FlowControl` で同時処理メッセージ数を制限し、パイプラインへの入力レートを抑制する。

```python
from apache_beam.io.gcp.pubsub import ReadFromPubSub

# subscriber_options で max_outstanding_messages を制限
```

## 追加検証: API レイテンシ 0-3 秒の場合

API レイテンシを 0-1 秒から 0-3 秒に変更した場合の結果 (`max_concurrent_sends=1`)。

| keys | batch | buffer | max/3s | avg/3s | throughput | result |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | 20 | 2.0s | 80 | 44.4 | 19.3 msg/s | OK |
| 10 | 20 | 2.0s | 80 | 44.4 | 19.3 msg/s | OK |
| 5 | 30 | 2.0s | 120 | 66.6 | 29.0 msg/s | OK |
| 10 | 30 | 2.0s | 120 | 66.6 | 29.0 msg/s | OK |
| 1 | 20 | 2.0s | 100 | 45.2 | 20.7 msg/s | OK |
| 1 | 30 | 2.0s | 150 | 67.7 | 31.0 msg/s | OK |
| 5 | 40 | 2.0s | 160 | 88.7 | 38.7 msg/s | OK |
| 10 | 40 | 2.0s | 160 | 88.5 | 38.7 msg/s | OK |
| 1 | 40 | 2.0s | 200 | 90.3 | 41.3 msg/s | NG |

API レイテンシが長くなると送信間隔が自然に広がり、制約を満たしやすくなる。
ただしスループットは大幅に低下する (最大でも 38.7 msg/s)。

## 追加検証: Dataflow 側で sleep を入れる場合

`SendBatchToApiFn` 内で `time.sleep()` を追加した場合の結果 (`api_latency=0-1s, concurrency=1`)。

### batch_size=20 の場合

| keys | sleep | max/3s | avg/3s | throughput | result |
| --- | --- | --- | --- | --- | --- |
| 3 | 0.0s | 200 | 113.3 | 52.7 msg/s | NG |
| 3 | 0.5s | 100 | 61.7 | 28.0 msg/s | OK |
| 3 | 1.0s | 60 | 41.5 | 18.7 msg/s | OK |

### batch_size=30 の場合

| keys | sleep | max/3s | avg/3s | throughput | result |
| --- | --- | --- | --- | --- | --- |
| 3 | 0.0s | 300 | 170.0 | 79.0 msg/s | NG |
| 3 | 0.5s | 150 | 92.6 | 42.0 msg/s | OK |
| 3 | 1.0s | 90 | 62.3 | 28.0 msg/s | OK |

### batch_size=40 の場合

| keys | sleep | max/3s | avg/3s | throughput | result |
| --- | --- | --- | --- | --- | --- |
| 3 | 0.0s | 400 | 226.7 | 105.3 msg/s | NG |
| 3 | 0.5s | 200 | 123.4 | 56.0 msg/s | NG |
| 3 | 1.0s | 120 | 83.0 | 37.3 msg/s | OK |

### sleep 方式の評価

sleep 方式は制約を満たす有効な手段である。

**スループットを最大化する最適な組み合わせ:**

| 構成 | sleep | max/3s | throughput |
| --- | --- | --- | --- |
| batch=40, sleep=1.0s | 1.0s | 120 | 37.3 msg/s |
| batch=30, sleep=0.5s | 0.5s | 150 | 42.0 msg/s |
| batch=20, sleep=0.5s | 0.5s | 100 | 28.0 msg/s |

**`batch_size=30, sleep=0.5s` が最もスループットが高く、制約に対して余裕もある。**

ただし以下の注意点がある。

- sleep 中もワーカーリソースを占有するため、Dataflow のコスト効率が悪化する
- 4000 msg/s の入力に対して 42 msg/s の処理は約 1% であり、メッセージは滞留し続ける
- 滞留対策として複数ワーカーへの分散、または Pub/Sub の FlowControl による入力制限が必要

## 結論

`GroupIntoBatches` のパラメータ調整だけでは、3 秒ウィンドウ 165 件の制約を安定的に満たせない。
API レイテンシの分散によるバーストが根本原因である。

**sleep 方式は有効だが、単独では不十分。**
`batch_size=30, sleep=0.5s, max_concurrent_sends=1` を基本とし、以下を組み合わせる必要がある。

1. `SendBatchToApiFn` に `time.sleep(0.5)` を追加 (バースト抑制)
2. 複数ワーカーで並列処理し、各ワーカーが独立にレート制限 (スループット確保)
3. トークンバケット等のレートリミッターで厳密に制御 (安全マージン確保)

## 再現手順

```bash
# シミュレーション単体実行
uv run python simulation.py

# グリッドサーチ実行 (約 3 分)
uv run python explore_params.py

# 結果サマリーのみ表示
uv run python explore_params.py --summary
```

## 関連ファイル

| ファイル | 役割 |
| --- | --- |
| `simulation.py` | 離散イベントシミュレーションエンジン |
| `explore_params.py` | パラメータグリッドサーチスクリプト |
| `exploration_results.csv` | 全 900 通りの探索結果データ |

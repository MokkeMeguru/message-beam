# バッチ Publish 機能 ローカル検証環境 設計書

## 1. 概要

本環境は、Google Cloud Dataflow (Apache Beam) を用いたメッセージのバッチ処理および流量制御機能を、GCP 課金を発生させずにローカルマシン上で再現・検証することを目的とする。

## 2. システム構成

クラウド上のコンポーネントをローカルの代替手段に置き換える。

| クラウド構成       | ローカル検証構成            | 役割                                                          |
| ------------------ | --------------------------- | ------------------------------------------------------------- |
| **Publisher**      | **Load Generator (Python)** | 1000 msg/s の負荷を生成するスクリプト                         |
| **Cloud Pub/Sub**  | **Pub/Sub Emulator**        | Google 公式のエミュレータ (gcloud component)                  |
| **Cloud Dataflow** | **DirectRunner**            | Apache Beam のローカル実行エンジン                            |
| **External API**   | **Mock Server (Python)**    | バッチ化されたリクエストを受け取り、ログ出力する簡易Webサーバ |

### データフロー図

```mermaid
graph LR
    A[Load Generator] -- 1. Publish (1000/s) --> B(Pub/Sub Emulator)
    B -- 2. Streaming Pull --> C{Beam Pipeline\n(DirectRunner)}
    C -- 3. GroupIntoBatches --> C
    C -- 4. POST Batch JSON --> D[Mock API Server]

```

---

## 3. コンポーネント詳細設計

### 3.1. Pub/Sub Emulator (インフラ)

Google Cloud CLI (`gcloud`) に含まれるエミュレータを使用する。

- **起動コマンド:** `gcloud beta emulators pubsub start --host-port=localhost:8085`
- **環境変数:** 検証を実行する全ターミナルで `export PUBSUB_EMULATOR_HOST=localhost:8085` を設定する必要がある。

### 3.2. Mock API Server (受信側)

バッチ化されたリクエストが正しく届いているか検証するための簡易サーバー。
フレームワークを使わずとも Python 標準ライブラリ (`http.server`) で十分だが、可読性のため `Flask` や `FastAPI` 推奨。ここでは軽量な実装例を示す。

**検証ポイント:**

- リクエストボディ内のメッセージ数が `BATCH_SIZE` (例: 100) と一致しているか。
- リクエストの頻度が `10 req/s` (1000msgs / 100batch) に収まっているか。

### 3.3. Load Generator (送信側)

テストデータを大量に Pub/Sub Emulator へ投入するスクリプト。

**機能:**

- 非同期 (AsyncIO) で高速に Publish を行う。
- 送信レートを調整可能にする (例: 1000/s)。

### 3.4. Beam Pipeline (処理本体)

前述の Dataflow コードを流用するが、実行ランナーを `DirectRunner` に変更する。

---

## 4. 実装コード (検証用ツールキット)

以下の3つのファイルを用意して検証を行います。

### 準備: 必要なライブラリ

```bash
pip install apache-beam[gcp] google-cloud-pubsub flask requests

```

### ファイル1: `mock_server.py` (受け手)

```python
from flask import Flask, request
import logging

app = Flask(__name__)

# ログ設定: 受信したバッチサイズを見やすく表示
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MockServer")

@app.route('/batch-endpoint', methods=['POST'])
def receive_batch():
    data = request.json
    items = data.get('items', [])

    # ここが検証の核心: バッチサイズが期待通りか確認
    logger.info(f"Received Batch! Count: {len(items)} items. (Sample ID: {items[0].get('id') if items else 'N/A'})")

    return {"status": "ok"}, 200

if __name__ == '__main__':
    app.run(port=9000)

```

### ファイル2: `generator.py` (送り手)

```python
import os
import time
import json
import random
from google.cloud import pubsub_v1

# エミュレータを向くように設定 (重要)
os.environ["PUBSUB_EMULATOR_HOST"] = "localhost:8085"
os.environ["PUBSUB_PROJECT_ID"] = "my-local-project"

project_id = "my-local-project"
topic_id = "my-topic"

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(project_id, topic_id)

# トピックがない場合は作成 (エミュレータ用)
try:
    publisher.create_topic(request={"name": topic_path})
    print(f"Topic created: {topic_path}")
except Exception:
    pass

print("Start publishing messages...")
for i in range(1000): # 1000件送信テスト
    data = {"id": i, "content": f"msg-{i}", "timestamp": time.time()}
    data_bytes = json.dumps(data).encode("utf-8")

    publisher.publish(topic_path, data_bytes)

    # 1000msg/s をシミュレートするための微小な待機 (必要に応じて調整)
    # time.sleep(0.001)

print("Finished publishing 1000 messages.")

```

### ファイル3: `local_pipeline.py` (処理本体の修正版)

前回のコードの `run` 関数の一部をローカル実行用に変更します。

```python
# ... (前回のimportsとクラス定義はそのまま) ...

# 変更点: API URLをローカルに向ける
class SendBatchToApiFn(beam.DoFn):
    def process(self, batch_element):
        key, messages = batch_element
        payload_list = []
        for msg in messages:
            payload_list.append(json.loads(msg.decode('utf-8')))

        # ローカルのMock Serverへ
        api_url = "http://localhost:9000/batch-endpoint"
        try:
            requests.post(api_url, json={"items": payload_list})
            logging.info(f"Sent batch of {len(payload_list)}")
        except Exception as e:
            logging.error(f"Error: {e}")

def run():
    # エミュレータ設定
    os.environ["PUBSUB_EMULATOR_HOST"] = "localhost:8085"

    options = PipelineOptions()
    options.view_as(StandardOptions).streaming = True # ストリーミング必須

    project_id = "my-local-project"
    sub_id = "my-sub"
    input_subscription = f"projects/{project_id}/subscriptions/{sub_id}"

    # サブスクリプション作成 (エミュレータ用)
    with pubsub_v1.SubscriberClient() as subscriber:
        topic_path = subscriber.topic_path(project_id, "my-topic")
        sub_path = subscriber.subscription_path(project_id, sub_id)
        try:
            subscriber.create_subscription(request={"name": sub_path, "topic": topic_path})
        except Exception:
            pass

    with beam.Pipeline(options=options) as p:
        (
            p
            | 'Read' >> beam.io.ReadFromPubSub(subscription=input_subscription)
            | 'AddKeys' >> beam.ParDo(AddRandomKeyFn())
            | 'Batch' >> beam.GroupIntoBatches(batch_size=100, max_buffering_duration_secs=2) # テスト用に2秒
            | 'Send' >> beam.ParDo(SendBatchToApiFn())
        )

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run()

```

---

## 5. 検証シナリオと手順

ターミナルを4つ開いて実行します。

### 手順1: エミュレータ起動 (Terminal 1)

```bash
gcloud beta emulators pubsub start --host-port=localhost:8085

```

### 手順2: Mock Server 起動 (Terminal 2)

```bash
python mock_server.py

```

### 手順3: Dataflow パイプライン起動 (Terminal 3)

```bash
export PUBSUB_EMULATOR_HOST=localhost:8085
python local_pipeline.py

```

- 起動すると待機状態になります。

### 手順4: 負荷生成 (Terminal 4)

```bash
export PUBSUB_EMULATOR_HOST=localhost:8085
python generator.py

```

- 1000件のメッセージが一気に投入されます。

### 期待される結果 (検証完了条件)

Terminal 2 (Mock Server) のログを確認します。

1. **バッチ化の確認:**
   ログに `Received Batch! Count: 100 items.` が表示されること。
   1000件送信した場合、理論上は `100 items` のログが **10回** 出力されるはずです。
   （※タイミングによっては `99` や `101` にはなりませんが、端数が出る場合は `Count: 35` などが出ます）
2. **タイムアウトの確認:**
   `generator.py` を修正して、メッセージを **5件だけ** 送信してみてください。
   Mock Server に即座にはログが出ず、**約2秒後** (パイプラインで設定した `max_buffering_duration_secs`) に `Count: 5` のログが出れば、タイムアウト機能が正常動作しています。

---

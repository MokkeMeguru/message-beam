# Message Beam - ローカル検証環境

## プロジェクト概要

Google Cloud Dataflow (Apache Beam) のバッチ Publish 機能をローカルで検証する環境。
Pub/Sub Emulator + DirectRunner を使い、メッセージのバッチ化と流量制御を GCP 課金なしで検証できる。

## 技術スタック

- **Python 3.11+** / パッケージ管理: `uv`
- **Apache Beam** (DirectRunner) — ストリーミングパイプライン
- **Google Cloud Pub/Sub Emulator** — ローカル Pub/Sub
- **Flask** — Mock API サーバー

## ファイル構成

| ファイル | 役割 |
|---|---|
| `mock_server.py` | バッチ受信用 Mock API サーバー (port 9000) |
| `generator.py` | Pub/Sub Emulator に 1000 件メッセージを Publish |
| `local_pipeline.py` | Beam パイプライン (ReadFromPubSub → GroupIntoBatches → POST) |
| `Makefile` | 各コンポーネントの起動コマンド |
| `INSTRUCTION.md` | 設計書 |

## 起動方法

```bash
make all  # 手順を表示
```

4 つのターミナルで順に実行:

1. `make emulator` — Pub/Sub Emulator 起動
2. `make mock-server` — Mock API Server 起動
3. `make pipeline` — Beam Pipeline 起動
4. `make generate` — 1000 件メッセージ送信

## パイプライン処理フロー

1. `ReadFromPubSub` — Pub/Sub からストリーミング読み取り
2. `AddRandomKeyFn` — ランダムキー (0-9) を付与して KV ペア化
3. `GroupIntoBatches(batch_size=100, max_buffering_duration_secs=2)` — 100 件ずつバッチ化 (2 秒タイムアウト)
4. `SendBatchToApiFn` — Mock Server に POST

## 重要な設定

- Pub/Sub Emulator: `localhost:8085`
- Mock Server: `localhost:9000`
- Project ID: `my-local-project`
- Topic: `my-topic` / Subscription: `my-sub`
- バッチサイズ: 100 / バッファリング最大待機: 2 秒

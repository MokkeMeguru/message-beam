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
| --- | --- |
| `mock_server.py` | バッチ受信用 Mock API サーバー (port 9000, 3s ウィンドウ計測付き) |
| `generator.py` | Pub/Sub Emulator に 1000 件メッセージを Publish |
| `local_pipeline.py` | Beam パイプライン (CLI 引数でパラメータ設定可能) |
| `simulator/` | 離散イベントシミュレータパッケージ (`python -m simulator`) |
| `simulator/config.py` | `SimulationConfig` dataclass |
| `simulator/result.py` | `SimulationResult` dataclass |
| `simulator/engine.py` | DES コア (`Event`, `PipelineSimulator`) |
| `simulator/explore.py` | グリッドサーチ (`itertools.product`) |
| `simulator/charts.py` | Mermaid xychart-beta チャート生成 |
| `simulator/cli.py` | argparse エントリポイント (simulate / explore / charts) |
| `simulation.py` | 互換 shim → `simulator` パッケージ |
| `explore_params.py` | 互換 shim → `simulator.explore` |
| `Makefile` | 各コンポーネントの起動コマンド |
| `INSTRUCTION.md` | 設計書 |
| `REPORT.md` | 初回パラメータ探索レポート |
| `REPORT-batch20-keys8.md` | batch=20/keys=8 構成の検証レポート |

## 起動方法

```bash
make all  # 手順を表示
```

4 つのターミナルで順に実行:

1. `make emulator` — Pub/Sub Emulator 起動
2. `make mock-server` — Mock API Server 起動
3. `make pipeline-recommend` — おすすめ構成で Pipeline 起動
4. `make generate` — 1000 件メッセージ送信

## パイプライン処理フロー

1. `ReadFromPubSub` — Pub/Sub からストリーミング読み取り
2. `AddRandomKeyFn` — ランダムキー (0-9) を付与して KV ペア化
3. `GroupIntoBatches` — バッチ化 (サイズ・タイムアウト設定可能)
4. `SendBatchToApiFn` — Mock Server に POST (sleep によるレート制御対応)

## パイプラインの CLI 引数

```bash
uv run python local_pipeline.py --batch-size 50 --sleep 0.8 --buffer-duration 2.0
```

| 引数 | デフォルト | 説明 |
| --- | --- | --- |
| `--batch-size` | 100 | GroupIntoBatches のバッチサイズ |
| `--sleep` | 0.0 | バッチ送信後の sleep 秒数 |
| `--buffer-duration` | 2.0 | バッファリングタイムアウト (秒) |

## 重要な設定

- Pub/Sub Emulator: `localhost:8085`
- Mock Server: `localhost:9000`
- Project ID: `my-local-project`
- Topic: `my-topic` / Subscription: `my-sub`

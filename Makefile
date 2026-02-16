.PHONY: install emulator stop-emulator mock-server \
       pipeline pipeline-a pipeline-b pipeline-recommend \
       generate simulate explore charts all

install:
	uv sync

emulator:
	gcloud beta emulators pubsub start --host-port=localhost:8085

stop-emulator:
	@ps aux | grep 'cloud-pubsub-emulator' | grep -v grep | awk '{print $$2}' | xargs -r kill -9 2>/dev/null; \
	ps aux | grep 'emulators pubsub start' | grep -v grep | awk '{print $$2}' | xargs -r kill -9 2>/dev/null; \
	echo "Pub/Sub Emulator stopped."

mock-server:
	uv run python mock_server.py

# デフォルト (パラメータ自由指定)
# 例: make pipeline ARGS="--batch-size 50 --sleep 1.0"
pipeline:
	PUBSUB_EMULATOR_HOST=localhost:8085 uv run python local_pipeline.py $(ARGS)

# おすすめ構成: batch=50, sleep=0.8s (単一ワーカー最高スループット)
pipeline-recommend:
	@echo "=== Recommend: batch_size=50, sleep=0.8s ==="
	@echo "  期待: max/3s=150, throughput=51.7 msg/s"
	@echo ""
	PUBSUB_EMULATOR_HOST=localhost:8085 uv run python local_pipeline.py \
		--batch-size 50 --sleep 0.8

# 構成 A: batch=30, sleep=0.5s (低レイテンシ)
pipeline-a:
	@echo "=== Config A: batch_size=30, sleep=0.5s ==="
	@echo "  期待: max/3s=150, throughput=42 msg/s"
	@echo ""
	PUBSUB_EMULATOR_HOST=localhost:8085 uv run python local_pipeline.py \
		--batch-size 30 --sleep 0.5

# 構成 B: batch=75, sleep=1.5s (大バッチ)
pipeline-b:
	@echo "=== Config B: batch_size=75, sleep=1.5s ==="
	@echo "  期待: max/3s=150, throughput=50 msg/s"
	@echo ""
	PUBSUB_EMULATOR_HOST=localhost:8085 uv run python local_pipeline.py \
		--batch-size 75 --sleep 1.5

generate:
	PUBSUB_EMULATOR_HOST=localhost:8085 uv run python generator.py

# シミュレーション
# 例: make simulate ARGS="--batch-size 50 --send-sleep 0.8 --max-concurrent 1"
simulate:
	uv run python -m simulator simulate $(ARGS)

explore:
	uv run python -m simulator explore $(ARGS)

charts:
	uv run python -m simulator charts $(ARGS)

all:
	@echo "=== Message Beam ローカル検証環境 ==="
	@echo ""
	@echo "以下の順番で、それぞれ別のターミナルで実行してください:"
	@echo ""
	@echo "  Terminal 1: make emulator"
	@echo "  Terminal 2: make mock-server"
	@echo "  Terminal 3: make pipeline-recommend  (おすすめ: batch=50, sleep=0.8s)"
	@echo "          or: make pipeline-a          (構成A: batch=30, sleep=0.5s)"
	@echo "          or: make pipeline-b          (構成B: batch=75, sleep=1.5s)"
	@echo "          or: make pipeline ARGS=\"--batch-size 20 --sleep 1.0\""
	@echo "  Terminal 4: make generate"
	@echo ""
	@echo "Mock Server のログで Window(3s) のリクエスト数が 165 未満なら制約 OK"
	@echo "統計確認: curl http://localhost:9000/stats"

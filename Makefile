.PHONY: install emulator stop-emulator mock-server pipeline generate all

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

pipeline:
	PUBSUB_EMULATOR_HOST=localhost:8085 uv run python local_pipeline.py

generate:
	PUBSUB_EMULATOR_HOST=localhost:8085 uv run python generator.py

all:
	@echo "=== Message Beam ローカル検証環境 ==="
	@echo ""
	@echo "以下の順番で、それぞれ別のターミナルで実行してください:"
	@echo ""
	@echo "  Terminal 1: make emulator"
	@echo "  Terminal 2: make mock-server"
	@echo "  Terminal 3: make pipeline"
	@echo "  Terminal 4: make generate"
	@echo ""
	@echo "期待結果: Mock Server に 'Count: 100 items' のログが約10回出力される"

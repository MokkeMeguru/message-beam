from flask import Flask, request
import logging

app = Flask(__name__)

# ログ設定: 受信したバッチサイズを見やすく表示
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MockServer")


@app.route("/batch-endpoint", methods=["POST"])
def receive_batch():
    data = request.json
    items = data.get("items", [])

    # ここが検証の核心: バッチサイズが期待通りか確認
    logger.info(
        f"Received Batch! Count: {len(items)} items. "
        f"(Sample ID: {items[0].get('id') if items else 'N/A'})"
    )

    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(port=9000)

import os
import time
import json

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
for i in range(1000):  # 1000件送信テスト
    data = {"id": i, "content": f"msg-{i}", "timestamp": time.time()}
    data_bytes = json.dumps(data).encode("utf-8")

    publisher.publish(topic_path, data_bytes)

print("Finished publishing 1000 messages.")

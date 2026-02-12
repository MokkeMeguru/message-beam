import json
import logging
import os
import random

import apache_beam as beam
import requests
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from google.cloud import pubsub_v1


class AddRandomKeyFn(beam.DoFn):
    """メッセージにランダムキーを付与し、GroupIntoBatches で使う KV ペアを生成する。"""

    def process(self, element):
        key = random.randint(0, 9)
        yield (key, element)


class SendBatchToApiFn(beam.DoFn):
    """バッチ化されたメッセージをローカル Mock Server に POST する。"""

    def process(self, batch_element):
        key, messages = batch_element
        payload_list = []
        for msg in messages:
            payload_list.append(json.loads(msg.decode("utf-8")))

        # ローカルの Mock Server へ
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
    options.view_as(StandardOptions).streaming = True  # ストリーミング必須

    project_id = "my-local-project"
    sub_id = "my-sub"
    input_subscription = f"projects/{project_id}/subscriptions/{sub_id}"

    # トピック作成 (エミュレータ用 — サブスクリプション作成前にトピックが必要)
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, "my-topic")
    try:
        publisher.create_topic(request={"name": topic_path})
        logging.info(f"Topic created: {topic_path}")
    except Exception:
        logging.info(f"Topic already exists: {topic_path}")

    # サブスクリプション作成 (エミュレータ用)
    with pubsub_v1.SubscriberClient() as subscriber:
        sub_path = subscriber.subscription_path(project_id, sub_id)
        try:
            subscriber.create_subscription(
                request={"name": sub_path, "topic": topic_path}
            )
            logging.info(f"Subscription created: {sub_path}")
        except Exception:
            logging.info(f"Subscription already exists: {sub_path}")

    with beam.Pipeline(options=options) as p:
        (
            p
            | "Read" >> beam.io.ReadFromPubSub(subscription=input_subscription)
            | "AddKeys" >> beam.ParDo(AddRandomKeyFn())
            | "Batch"
            >> beam.GroupIntoBatches(
                batch_size=100, max_buffering_duration_secs=2
            )  # テスト用に2秒
            | "Send" >> beam.ParDo(SendBatchToApiFn())
        )


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    run()

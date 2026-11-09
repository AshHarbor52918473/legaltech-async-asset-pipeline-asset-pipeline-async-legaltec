import base64
import io

from src.legaltech_pipeline import MatterIntake, queue_intake, run_worker_once


class FakeClient:
    def __init__(self):
        self.published = []

    def ensure_bucket(self, name):
        return {"name": name}

    def presign(self, bucket, key, op):
        return {"url": f"https://upload.test/{bucket}/{key}?op={op}"}

    def publish(self, payload):
        self.published.append(payload)

    def consume(self):
        return {"items": [{"message_id": "m1", "payload": self.published[0]}]}

    def process_image(self, image, ops):
        assert base64.b64decode(image["base64"], validate=True) == b"image bytes"
        assert ops == [{"op": "resize", "params": {"width": 1600}}]
        return {"image": image, "status": "done"}


def test_intake_is_queued_and_worker_marks_processed(monkeypatch):
    def fetch_image(url, timeout):
        assert url == "https://upload.test/legal-matters/m-7/signed.png?op=get"
        assert timeout == 30
        return io.BytesIO(b"image bytes")

    monkeypatch.setattr("urllib.request.urlopen", fetch_image)
    client = FakeClient()
    intake = MatterIntake("m-7", "Ruth", "m-7/signed.png", "2026-11-12")
    accepted = queue_intake(client, intake)
    assert accepted["state"] == "queued"
    assert client.published[0]["matter_id"] == "m-7"
    result = run_worker_once(client)
    assert result["state"] == "processed"
    assert result["download_url"].startswith("https://upload.test/")
    assert base64.b64decode(result["processed"]["image"]["base64"]) == b"image bytes"


def test_client_sends_required_request_fields():
    from src.legaltech_pipeline import InfraiClient

    client = InfraiClient(api_key="test")
    calls = []
    client.call = lambda method, path, body: calls.append((path, body))
    client.publish({"matter_id": "m-7"})
    client.consume()
    client.process_image({"base64": "aW1hZ2UgYnl0ZXM="})
    assert calls == [
        ("/v1/queue/publish", {"queue": "legal-matters", "payload": {"matter_id": "m-7"}}),
        ("/v1/queue/consume", {"queue": "legal-matters", "max_messages": 1, "visibility_timeout": 60}),
        ("/v1/image/process", {"image": {"base64": "aW1hZ2UgYnl0ZXM="}, "ops": []}),
    ]
    ops = [{"op": "resize", "width": 100}]
    client.publish({}, queue="custom")
    client.consume(queue="custom")
    client.process_image({"base64": "aW1hZ2UgYnl0ZXM="}, ops=ops)
    assert calls[-3][1]["queue"] == calls[-2][1]["queue"] == "custom"
    assert calls[-1][1]["ops"] == ops

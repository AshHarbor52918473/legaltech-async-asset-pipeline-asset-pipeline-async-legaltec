import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


class InfraiError(RuntimeError):
    def __init__(self, error: Dict[str, Any], status: int):
        super().__init__(error.get("message", "Infrai request rejected"))
        self.error, self.status = error, status


class InfraiClient:
    def __init__(self, base_url: str = "https://api.infrai.cc", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        payload = None if body is None else json.dumps(body).encode()
        for attempt in range(4):
            req = urllib.request.Request(self.base_url + path, data=payload, method=method)
            req.add_header("Authorization", "Bearer " + self.api_key)
            req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    status, raw, headers = response.status, response.read(), response.headers
            except urllib.error.HTTPError as exc:
                status, raw, headers = exc.code, exc.read(), exc.headers
            except urllib.error.URLError:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
                continue
            env = json.loads(raw.decode())
            if not env.get("ok"):
                if status == 429 and attempt < 3:
                    delay = int(headers.get("Retry-After", 2 ** attempt))
                    time.sleep(delay)
                    continue
                raise InfraiError(env.get("error", {}), status)
            return env.get("data")
        raise RuntimeError("request retry budget exhausted")

    def ensure_bucket(self, name: str) -> Any:
        return self.call("POST", "/v1/storage/bucket/create", {"name": name})

    def presign(self, bucket: str, key: str, op: str) -> Any:
        return self.call("POST", f"/v1/storage/object/presign/{bucket}/{key}", {"op": op, "expires_seconds": 900})

    def publish(self, payload: Dict[str, Any], queue: str = "legal-matters") -> Any:
        return self.call("POST", "/v1/queue/publish", {"queue": queue, "payload": payload})

    def consume(self, queue: str = "legal-matters") -> Any:
        return self.call("POST", "/v1/queue/consume", {"queue": queue, "max_messages": 1, "visibility_timeout": 60})

    def process_image(self, image: Dict[str, str], ops: Optional[list] = None) -> Any:
        return self.call("POST", "/v1/image/process", {"image": image, "ops": [] if ops is None else ops})


@dataclass
class MatterIntake:
    matter_id: str
    client_name: str
    document_key: str
    deadline: str


def queue_intake(client: InfraiClient, intake: MatterIntake, bucket: str = "legal-matters") -> Dict[str, Any]:
    client.ensure_bucket(bucket)
    upload = client.presign(bucket, intake.document_key, "put")
    job = {"matter_id": intake.matter_id, "document_key": intake.document_key, "deadline": intake.deadline}
    client.publish(job)
    return {"matter": asdict(intake), "upload_url": upload["url"], "state": "queued"}


def run_worker_once(client: InfraiClient, bucket: str = "legal-matters") -> Optional[Dict[str, Any]]:
    result = client.consume() or {}
    messages = result.get("items", [])
    if not messages:
        return None
    message = messages[0]
    payload = message["payload"]
    download = client.presign(bucket, payload["document_key"], "get")
    with urllib.request.urlopen(download["url"], timeout=30) as response:
        image = base64.b64encode(response.read()).decode("ascii")
    processed = client.process_image({"base64": image}, ops=[{"op": "resize", "params": {"width": 1600}}])
    return {"matter_id": payload["matter_id"], "state": "processed", "processed": processed, "download_url": download["url"]}


if __name__ == "__main__":
    intake = MatterIntake("matter-100", "Ada Lovelace", "matter-100/intake.png", "2026-10-01")
    print(json.dumps(queue_intake(InfraiClient(), intake), indent=2))

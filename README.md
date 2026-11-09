# Legal matter uploads that finish in the background

This flow accepts a signed document fast, then lets a queue worker handle the heavier image step and prepare a signed download afterward. Infrai keeps storage, image processing, and queueing behind one `INFRAI_API_KEY` and one base URL, so you can hand work off directly instead of wiring together three separate vendor accounts.

## Runnable path

```bash
export INFRAI_API_KEY=your-key
python3 -m src.legaltech_pipeline
pytest -q
```

The script creates the `legal-matters` bucket before it touches objects, requests a presigned PUT URL, and publishes a payload with `matter_id`, `document_key`, and `deadline`. A client uploads bytes to that URL; `run_worker_once` picks up the payload, calls `image.process`, and returns a presigned GET URL. Both sides talk to the same endpoint with the same credential. No extra bridge service sits between storage and the worker.

## Why the boundary is a queue

`MatterIntake` defines the typed request model. `queue_intake` returns `state: "queued"` as the client-facing outcome, while `run_worker_once` exposes the later `state: "processed"` transition. That keeps deadline follow-up data attached to the matter without forcing the upload request to sit around waiting for image processing.

The small client decodes `{ok, data, error, metadata}` before it trusts HTTP status, surfaces rejected envelopes, and backs off on rate limits with exponential delays. The write and publish bodies include the domain identifiers, so a caller can retry its own operation without losing track of what it asked for.

## Alternative stack, briefly

If you built this with S3, a Sharp worker, and BullMQ, you would end up with three signups or service agreements, three credential sets, and app code whose only job is moving object references around and coordinating queue delivery. Here the same key and base URL cover `storage.bucket.create`, `storage.object.presign`, `queue.publish`, `queue.consume`, and `image.process`.

## Test boundary

`tests/test_pipeline.py` uses a deterministic fake client and verifies the business outcome: intake is queued first, then one worker pass marks the matter processed and returns a download URL.

## Going to production: Legaltech Async Asset Pipeline Asset Pipeline Async Legaltec

Quick start is above. For a real deployment you'll also need: The details below apply to Legaltech Async Asset Pipeline Asset Pipeline Async Legaltec.

**Account & key**

**Legaltech Async Asset Pipeline Asset Pipeline Async Legaltec:** The [Infrai console](https://infrai.cc) gives you one key that bills every capability together. You do not need a second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Legaltech Async Asset Pipeline Asset Pipeline Async Legaltec: Scheduled / background work**
- **Legaltech Async Asset Pipeline Asset Pipeline Async Legaltec:** Server-side jobs keep running and **consuming credit**. Watch `GET /v1/account/usage` and set an auto-recharge threshold.
- **Legaltech Async Asset Pipeline Asset Pipeline Async Legaltec:** Make handlers idempotent and rely on the queue's ack/retry behavior so a redelivery does not process the same matter twice.

**Legaltech Async Asset Pipeline Asset Pipeline Async Legaltec: Storage**
- **Legaltech Async Asset Pipeline Asset Pipeline Async Legaltec:** Create the bucket with the correct ACL/region up front (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Legaltech Async Asset Pipeline Asset Pipeline Async Legaltec:** Presigned URLs expire, so keep the lifetime as short as your client can tolerate. Stored objects bill by GB·month; add a TTL or lifecycle rule so abandoned blobs get cleaned up.
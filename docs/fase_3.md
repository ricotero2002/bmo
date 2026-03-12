# Arreglar upload
----------------------------------

## 6.2 RabbitMQ restarts

- Queues declared with `durable=True` and messages with `delivery_mode=2` survive restart.
- Tasks in-flight at crash time: if `acks_late=True`, they are re-queued on reconnect. ✅


Each document should have a lifecycle tracked in Postgres:

RECEIVED → QUEUED → PROCESSING → CHUNKING → EMBEDDING → STORED → INDEXED
                                     │
                                     ▼ (on error)
                                   FAILED (retryable) → QUEUED (retry)
                                   DEAD (max retries exceeded)



## RabbitMQ — Durable Queue Declaration (Python / Celery)
In your Celery app configuration
app.conf.task_queues = [
    Queue(
        "ingest_q",
        Exchange("ingest_q", type="direct", durable=True),
        routing_key="ingest_q",
        durable=True,                  # survives broker restart
        queue_arguments={
            "x-message-ttl": 86400000,  # 24h TTL (ms)
            "x-dead-letter-exchange": "ingest_dlx",  # dead-letter exchange
        }
    )
]
app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True


### Dead-Letter Queue (DLQ)
Always configure a DLQ so that permanently-failing messages are not lost:
# Messages that exceed max_retries go here for manual inspection
Queue(
    "ingest_dlq",
    Exchange("ingest_dlx", type="direct", durable=True),
    routing_key="ingest_dlq",
    durable=True,
)

```python
# workers/tasks/ingest.py
from celery import Celery
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

@app.task(
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=5,
)
def ingest_document(self, file_path: str, doc_id: str, metadata: dict):
    try:
        _update_status(doc_id, "processing")
        _process_document(file_path, doc_id, metadata)
        _update_status(doc_id, "indexed")

    except TransientError as exc:
        # Exponential backoff: 60s, 120s, 240s, 480s, 960s
        delay = 60 * (2 ** self.request.retries)
        logger.warning(f"Transient error for {doc_id}, retry {self.request.retries} in {delay}s")
        _update_status(doc_id, "failed", error=str(exc))
        raise self.retry(exc=exc, countdown=delay)

    except PermanentError as exc:
        # Don't retry — log and mark dead immediately
        logger.error(f"Permanent error for {doc_id}: {exc}")
        _update_status(doc_id, "dead", error=str(exc))
        # Do NOT call self.retry() — let the task finish, RabbitMQ ACKs it
        # The DLQ is for RabbitMQ-level failures, not application logic failures
```

#### Type 2 — Permanent failures (corrupt file, unsupported format, embedding error)
Do **not** retry — they will always fail. Mark the document as `dead` in Postgres and alert (optionally send to RabbitMQ DLQ for manual inspection).

#### The full retry flow

```
Task fails (attempt 1)
      │
      ├─ Transient? ──► self.retry(countdown=60s)
      │                  → message stays in ingest_q
      │                  → status = "failed" in Postgres
      │
      ├─ Permanent? ──► mark "dead" in Postgres, ACK message
      │
      └─ max_retries exceeded? ──► Celery sends to RabbitMQ DLQ (ingest_dlq)
                                   → status = "dead" in Postgres
                                   → alert / dashboard shows it
```

#### Distinguish transient vs permanent errors

```python
# Classify errors explicitly
TRANSIENT_EXCEPTIONS = (
    ConnectionError,       # ChromaDB / Postgres network issue
    TimeoutError,          # embedding API timeout
    RateLimitError,        # OpenAI / Gemini rate limit
)
PERMANENT_EXCEPTIONS = (
    FileNotFoundError,     # file missing from storage
    UnsupportedFileType,   # .xlsx, .zip without handler
    CorruptFileError,      # PDF that can't be parsed
)
```


# Large Batch Upload (Many Files at Once)

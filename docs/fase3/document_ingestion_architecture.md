# Robust Document Ingestion Architecture
## Guaranteeing No Data Loss, Exactly-Once Processing, and Efficient Storage

> **Context:** This document is tailored to this project's stack:
> FastAPI · Celery · RabbitMQ · Redis · ChromaDB · Postgres.
> It explains when and how to add Kafka and how to wire everything together
> for three distinct ingestion scenarios.

---

## 1. The Core Problem

Sending large documents (or batches) through a pipeline creates three failure zones:

| Zone | What can go wrong |
|---|---|
| **Upload / Transfer** | Network drops mid-upload, partial file written |
| **Message Broker** | Message lost if broker restarts without persistence |
| **Processing / Storage** | Worker crashes after dequeue but before saving to vector DB |

The goal is **exactly-once semantics**: a document is ingested and stored in the vector DB **exactly one time**, even if any component crashes and recovers.

---

## 2. Decision Framework: Do You Need Kafka?

Before adding Kafka, use this decision tree:

```
Is your data arriving as a continuous stream
(e.g., watching a Drive folder, email inbox, real-time feed)?
├── YES → You NEED Kafka. Go to Section 4.
└── NO
    └── Is each upload a single file or a small batch (< ~100 docs)?
        ├── YES → RabbitMQ + Celery is enough. Go to Section 3.
        └── NO (large batch, hundreds/thousands of files)
            └── Is ordering or replay of the batch important?
                ├── YES → Use Kafka. Go to Section 4.
                └── NO → RabbitMQ + Celery with chunked publish. Go to Section 3B.
```

**Short answer for your project today (Phase 2):**
You do NOT need Kafka yet. RabbitMQ + Celery already gives you durability
and retry semantics for individual uploads and moderate batches.
Add Kafka in **Phase 3** when you implement Drive monitoring or real-time feeds.

---

## 3. Scenario A — Single File Upload (Current Stack, Phase 2)

### Architecture

```
User HTTP Request
      │  (multipart/form-data)
      ▼
┌─────────────┐   1. Save raw file      ┌─────────────────┐
│  FastAPI    │ ──────────────────────► │  Local FS /     │
│  /upload    │                         │  S3 / MinIO     │
└─────────────┘                         └────────┬────────┘
      │                                          │
      │  2. Publish task message                 │
      │  (file_path + metadata)                  │
      ▼                                          │
┌─────────────┐                                  │
│  RabbitMQ   │  durable=True                    │
│  Queue:     │  delivery_mode=PERSISTENT        │
│  ingest_q   │                                  │
└─────────────┘                                  │
      │  3. Celery worker consumes               │
      ▼                                          │
┌─────────────────────────────────────┐          │
│  Celery Worker (ingest_document)    │◄─────────┘
│                                     │  4. Read file from storage
│  a) Load file from storage          │
│  b) Split into chunks               │
│  c) Generate embeddings             │
│  d) Upsert to ChromaDB              │  ← idempotent by doc_id
│  e) Record in Postgres              │
└─────────────────────────────────────┘
```

### Key Guarantees

#### 2a. Durability in RabbitMQ
```python
# workers/tasks/ingest.py
from celery import Celery

app = Celery(...)

@app.task(
    bind=True,
    acks_late=True,          # ACK only AFTER successful processing
    reject_on_worker_lost=True,  # Re-queue if worker dies mid-task
    max_retries=5,
    default_retry_delay=60,
)
def ingest_document(self, file_path: str, doc_id: str, metadata: dict):
    try:
        # Load → chunk → embed → store
        _process_document(file_path, doc_id, metadata)
    except Exception as exc:
        raise self.retry(exc=exc)
```

**`acks_late=True`** is the single most important setting.
By default, Celery ACKs the message when it **receives** it, not when it **finishes**.
With `acks_late`, a worker crash means the message goes back to the queue automatically.

#### 2b. Idempotent Storage (No Duplicates)
Use LangChain's `RecordManager` (backed by your existing Postgres DB)
to track which `doc_id` chunks have already been stored:

```python
from langchain.indexes import SQLRecordManager, index
from langchain_community.vectorstores import Chroma

record_manager = SQLRecordManager(
    namespace=f"chroma/{collection_name}",
    db_url=settings.POSTGRES_URL,
)
record_manager.create_schema()

# This call is IDEMPOTENT — safe to re-run on retry
result = index(
    docs_to_embed,
    record_manager,
    vector_store,
    cleanup="incremental",   # removes stale chunks if doc changes
    source_id_key="source",  # links chunks back to original doc_id
)
```

If the worker retries the same `doc_id`, `index()` detects existing chunks via the
record manager and skips or replaces them without creating duplicates.

#### 2c. File Safety Before Publishing
Never publish a RabbitMQ task until the file is safely persisted:

```python
# api/routes/ingest.py
@router.post("/upload")
async def upload_document(file: UploadFile):
    doc_id = str(uuid4())
    file_path = await save_to_storage(file, doc_id)  # S3 / MinIO / disk
    await db.mark_received(doc_id, status="queued")  # Postgres record

    # Only now send to the queue
    ingest_document.apply_async(
        kwargs={"file_path": file_path, "doc_id": doc_id},
        queue="ingest_q",
    )
    return {"doc_id": doc_id, "status": "queued"}
```

---

## 3B. Scenario B — Large Batch Upload (Many Files at Once)

When a user uploads a ZIP, a folder, or sends 500+ documents at once,
**do not publish 500 individual tasks at once**. That floods the queue and makes
partial-failure recovery very hard. Instead, use a **coordinator + fan-out** pattern:

```
User uploads batch (ZIP / list of paths)
      │
      ▼
┌─────────────┐
│  FastAPI    │  Creates one BatchJob record in Postgres
│  /upload    │  (batch_id, total_files, status=pending)
│  /batch     │
└─────────────┘
      │
      ▼  publish ONE coordination task
┌─────────────┐
│  RabbitMQ   │  queue: batch_coordinator_q
│             │
└─────────────┘
      │
      ▼
┌──────────────────────────────────────┐
│  Celery: coordinate_batch()          │
│                                      │
│  for each file in batch:             │
│      ingest_document.apply_async(    │
│          {"file_path": ...,          │
│           "batch_id": batch_id,      │
│           "doc_id": file_doc_id},    │
│          queue="ingest_q"            │
│      )                               │
│  Mark batch_id = dispatching in DB   │
└──────────────────────────────────────┘
      │
      ▼  (fan-out: N individual tasks)
┌─────────────┐
│  RabbitMQ   │  queue: ingest_q
│             │  (one message per file)
└─────────────┘
      │
      ▼
┌─────────────────────┐
│  Celery Workers (N) │  (your current docker-compose has replicas: 2)
│  ingest_document()  │  each handles one file independently
└─────────────────────┘
      │
      ▼
  On completion → update batch progress in Postgres
  (batch_id: completed_files += 1)
  When completed_files == total_files → batch_status = done
```

### Why this is better than uploading 500 messages at once

| Concern | Naive (500 tasks at once) | Coordinator pattern |
|---|---|---|
| Partial failure recovery | Hard — you don't know which succeeded | Easy — poll `batch_id` status in Postgres |
| Queue overflow | Possible | Controlled fan-out |
| Progress visibility | None | Real-time via Postgres |
| Retry granularity | Individual but no batch context | Individual + batch context |

---

## 4. Scenario C — Continuous Stream (Drive, Email, Real-Time) — Phase 3

This is where **Kafka becomes essential**. RabbitMQ is a task queue: messages are consumed and gone. Kafka is an **event log**: messages are retained and replayable. This distinction is critical for streaming scenarios.

### Full Architecture

```
External Source                 Ingestion Layer                Processing Layer
(Google Drive /                 ─────────────────              ─────────────────
 Email / Webhook)

     │ file created/changed
     ▼
┌──────────────┐  produce event   ┌─────────────────────┐
│  Connector   │ ───────────────► │  Kafka Topic:        │
│  (Drive API  │                  │  raw-documents       │
│   watcher /  │                  │                      │
│   webhook)   │                  │  Partition key:      │
└──────────────┘                  │  user_id (ensures    │
                                  │  order per user)     │
                                  └──────────┬──────────┘
                                             │
                          ┌──────────────────┴──────────────────┐
                          │                                      │
                          ▼                                      ▼
                 ┌─────────────────┐                  ┌──────────────────┐
                 │  Kafka Consumer │                  │  Kafka Consumer  │
                 │  (Python /      │                  │  Group B:        │
                 │  Spark if big)  │                  │  Audit log /     │
                 │  Group A        │                  │  monitoring      │
                 └────────┬────────┘                  └──────────────────┘
                          │
                          │  publish to RabbitMQ
                          ▼
                 ┌─────────────────┐
                 │  RabbitMQ:      │
                 │  ingest_q       │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────────────────┐
                 │  Celery Worker              │
                 │  ingest_document()          │
                 │  (same as Scenario A)       │
                 └─────────────────────────────┘
                          │
                          ▼
                 ┌─────────────────────────────┐
                 │  ChromaDB + Postgres        │
                 │  (idempotent via            │
                 │   RecordManager)            │
                 └─────────────────────────────┘
```

### Why Kafka before RabbitMQ?

Because Kafka provides things RabbitMQ cannot in a streaming scenario:

| Feature | RabbitMQ | Kafka |
|---|---|---|
| Message replay (re-process from offset) | ❌ No | ✅ Yes |
| Fan-out to multiple consumers independently | Manual exchanges | ✅ Native consumer groups |
| Retention / audit log | ❌ No | ✅ Configurable (days/weeks) |
| Throughput (millions of events/sec) | Medium | Very High |
| Ordering guarantees | Per-queue | Per-partition |
| Exactly-once within Kafka | ❌ | ✅ Transactional API |

RabbitMQ **is still needed** even with Kafka because Celery tasks need a traditional task queue (RabbitMQ is its native broker). Kafka is the event bus; RabbitMQ is the task dispatcher.

### Exactly-Once from Kafka → ChromaDB

Kafka alone does not touch ChromaDB. The full chain needs each hop to be safe:

```
Kafka Offset Commit ──► RabbitMQ (durable) ──► Celery (acks_late) ──► ChromaDB (idempotent)
```

**Step by step:**

1. **Kafka consumer reads message but does NOT commit the offset yet.**
2. Consumer publishes to RabbitMQ (durable queue).
3. Consumer **only commits Kafka offset after RabbitMQ confirms persistence** (publisher confirms enabled).
4. Celery worker picks up task with `acks_late=True`.
5. Worker calls `index()` with `RecordManager` (idempotent upsert).
6. Worker returns → Celery ACKs the RabbitMQ message.

If the worker crashes at step 5, the RabbitMQ message is re-queued (acks_late).
If RabbitMQ crashes at step 2, the Kafka offset was never committed → re-consumed.
ChromaDB's `index()` call at step 5 is idempotent → no duplicate chunks.

```python
# workers/kafka_consumer.py (Phase 3)
from confluent_kafka import Consumer, KafkaError
import pika  # or use Celery's send_task

consumer = Consumer({
    "bootstrap.servers": settings.KAFKA_BROKERS,
    "group.id": "document-ingestor",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,   # CRITICAL: manual commit only
})

consumer.subscribe(["raw-documents"])

while True:
    msg = consumer.poll(1.0)
    if msg is None or msg.error():
        continue

    payload = json.loads(msg.value())

    # Publish to RabbitMQ with publisher confirms
    channel.confirm_delivery()
    channel.basic_publish(
        exchange="",
        routing_key="ingest_q",
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2),  # persistent
    )

    # Only commit after confirmed by RabbitMQ (publisher confirms)
    # NOTE: We do NOT wait for the worker to finish. 
    # RabbitMQ confirms once the message is safe on its disk.
    # Waiting for the worker would block the Kafka partition for minutes.
    consumer.commit(message=msg)
```

### Do you need Spark?

**For this project: probably not.**

Spark adds significant operational overhead (cluster management, JVM memory, etc.).
Use Spark only if:
- You have **millions of documents per hour** continuously
- You need **distributed transformation** (joins, aggregations across documents)
- You are processing **structured data at scale** (not plain text/PDF)

For this AI assistant, a plain Python Kafka consumer (or even Faust / AIOKafka)
is more than sufficient and much simpler to operate.

---

## 5. Exactly-Once Summary Table

| Scenario | Storage of raw file | Message durability | Worker durability | De-duplication |
|---|---|---|---|---|
| **Single file** | S3/disk before queue publish | RabbitMQ durable + persistent delivery | `acks_late=True` + retry | LangChain `RecordManager` |
| **Batch** | S3/disk before coordinator publish | Same + batch coordinator | Same per-file | Same per `doc_id` |
| **Stream (Kafka)** | Kafka log (retention) | Kafka → RabbitMQ with pub confirms + manual offset commit | Same | Same |

---

## 6. Failure Scenarios and Recovery

### 6.1 Worker crashes mid-processing

- **With `acks_late=True`**: message goes back to `ingest_q` automatically.
- Worker restarts, picks up the same message, calls `index()` → `RecordManager` skips already-stored chunks. No duplicate. ✅

### 6.2 RabbitMQ restarts

- Queues declared with `durable=True` and messages with `delivery_mode=2` survive restart.
- Tasks in-flight at crash time: if `acks_late=True`, they are re-queued on reconnect. ✅

### 6.3 ChromaDB restarts

- All data is persisted to volume (`chroma-data` in your docker-compose).
- Worker retries (via RabbitMQ) and `index()` safely re-upserts. ✅

### 6.4 Kafka consumer crashes (Phase 3)

- Kafka offsets are only committed after RabbitMQ confirms → the event is re-consumed.
- The downstream chain is idempotent, so re-processing is safe. ✅

### 6.5 Partial batch failure

- Each file in the batch is an independent Celery task.
- Each updates `batch_job` table with its own status.
- A monitoring endpoint can show `{batch_id: {total: 100, done: 97, failed: 3}}`.
- Failed tasks can be retried individually without re-processing the whole batch. ✅

---

## 7. State Machine for a Document

Each document should have a lifecycle tracked in Postgres:

```
RECEIVED → QUEUED → PROCESSING → CHUNKING → EMBEDDING → STORED → INDEXED
                                     │
                                     ▼ (on error)
                                   FAILED (retryable) → QUEUED (retry)
                                   DEAD (max retries exceeded)
```

```sql
-- Minimal Postgres schema for tracking
CREATE TABLE ingestion_jobs (
    doc_id      UUID PRIMARY KEY,
    batch_id    UUID,                   -- NULL for single-file uploads
    source_path TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'received',
    attempts    INT NOT NULL DEFAULT 0,
    error_msg   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON ingestion_jobs(batch_id);
CREATE INDEX ON ingestion_jobs(status);
```

---

## 8. Recommended Implementation Order (Mapped to Your Phases)

### Phase 2 (Now) — Implement First
- [x] RabbitMQ with `durable=True` queues and `delivery_mode=PERSISTENT`
- [ ] `acks_late=True` + `reject_on_worker_lost=True` on all Celery ingest tasks
- [ ] Save file to persistent storage **before** publishing task
- [ ] `RecordManager` (Postgres-backed) for idempotent ChromaDB upsert
- [ ] `ingestion_jobs` table to track document lifecycle
- [ ] Batch coordinator task + `batch_jobs` table

### Phase 3 (Streaming)
- [ ] Kafka topic `raw-documents` with retention policy
- [ ] Python Kafka consumer with manual offset commit + RabbitMQ publisher confirms
- [ ] Drive connector (Google Drive API webhook → Kafka producer)
- [ ] Dead-letter topic in Kafka for events that consistently fail

### Phase 5 (Production Cloud)
- [ ] Replace local Kafka with AWS MSK (Managed Streaming for Kafka)
- [ ] Replace MinIO/disk with S3 for raw file storage
- [ ] AWS SQS as alternative to RabbitMQ (evaluate based on scale)
- [ ] CloudWatch / OpenTelemetry for end-to-end tracing of each `doc_id`

---

## 9. Quick Configuration Reference

### RabbitMQ — Durable Queue Declaration (Python / Celery)
```python
# In your Celery app configuration
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
```

### Dead-Letter Queue (DLQ)
Always configure a DLQ so that permanently-failing messages are not lost:
```python
# Messages that exceed max_retries go here for manual inspection
Queue(
    "ingest_dlq",
    Exchange("ingest_dlx", type="direct", durable=True),
    routing_key="ingest_dlq",
    durable=True,
)
```

### Kafka Topic (Phase 3)
```yaml
# kafka topic config (via kafka-topics.sh or Confluent)
Topic: raw-documents
Partitions: 6          # one per user_id bucket, allows parallelism
Replication factor: 3  # production; use 1 locally
Retention: 7 days      # keep events for replay / debugging
cleanup.policy: delete
```

---

## 10. Architecture Diagram — Full Stack (Phase 3 Target)

```
                          ┌─────────────────────────────────────────────┐
                          │             External Sources                 │
                          │  Google Drive · Email · Manual Upload · API  │
                          └──────────────┬──────────────────────────────┘
                                         │
                          ┌──────────────▼──────────────┐
                          │  Connectors / Producers      │
                          │  (Drive watcher, FastAPI      │
                          │   /upload endpoint)          │
                          └──────────────┬──────────────┘
                                         │ raw file event
                          ┌──────────────▼──────────────┐
                          │  Raw File Storage            │
                          │  (MinIO local / S3 prod)     │
                          └──────────────┬──────────────┘
                                         │ file_path + metadata
                          ┌──────────────▼──────────────┐
                          │  Apache Kafka                │
                          │  Topic: raw-documents        │◄── audit / monitoring
                          │  Partition by user_id        │
                          └──────────────┬──────────────┘
                                         │ consume (manual commit)
                          ┌──────────────▼──────────────┐
                          │  Kafka Consumer              │
                          │  (Python / AIOKafka)         │
                          └──────────────┬──────────────┘
                                         │ publish (with confirms)
                          ┌──────────────▼──────────────┐
                          │  RabbitMQ                    │
                          │  Queue: ingest_q (durable)   │
                          │  DLQ: ingest_dlq             │
                          └──────────────┬──────────────┘
                                         │ consume (acks_late)
                          ┌──────────────▼──────────────┐
                          │  Celery Workers              │
                          │  ingest_document()           │
                          │  · Load from storage         │
                          │  · Chunk text                │
                          │  · Generate embeddings       │
                          │  · index() via RecordManager │
                          └──────┬──────────────┬────────┘
                                 │              │
                    ┌────────────▼──┐     ┌─────▼──────────┐
                    │  ChromaDB     │     │  Postgres        │
                    │  (vectors)    │     │  ingestion_jobs  │
                    │               │     │  record_manager  │
                    └───────────────┘     └─────────────────┘
```

---

## 11. Comparison: Your Options Side by Side

| Approach | Complexity | Exactly-Once | Replay | Suitable For |
|---|---|---|---|---|
| **Direct API → Celery** | Low | ❌ Without care | ❌ | Prototypes only |
| **RabbitMQ + Celery (acks_late + RecordManager)** | Medium | ✅ Yes | ❌ | Single files, small batches (Phase 2) |
| **RabbitMQ + Celery + Coordinator** | Medium | ✅ Yes | ❌ | Large batch uploads (Phase 2) |
| **Kafka → RabbitMQ → Celery** | High | ✅ Yes | ✅ Yes | Continuous streams, Drive monitor (Phase 3) |
| **Kafka → Spark → Celery** | Very High | ✅ Yes | ✅ Yes | Millions of docs/hour, data transformations |

> **Recommendation for your project:** Start with RabbitMQ + Celery properly configured.
> Move to Kafka in Phase 3 when you implement the Drive connector.
> Skip Spark unless document volume reaches millions per hour — a Python Kafka consumer is enough.

---

## 12. Follow-up Q&A

---

### Q1 — If I have Postgres (state) + object storage (files), does Redis still make sense?

**Short answer: yes, but for a completely different role.** The three stores serve orthogonal purposes and don't replace each other.

| Store | What it holds | Why it's needed |
|---|---|---|
| **Postgres** | Document lifecycle state (`ingestion_jobs`), `RecordManager` chunk hashes | Durable, queryable, relational. Truth about *what* happened. |
| **Object storage** (MinIO / S3) | Raw binary files (PDFs, DOCs, ZIPs) | Postgres is not a file store. Workers need to re-read the raw file on retry. |
| **Redis** | Celery task result backend · response cache · rate-limit counters | Low-latency ephemeral data. Not a truth store. |

Redis specifically is needed because:

1. **Celery result backend** — Celery needs somewhere to write task results and status so that `AsyncResult(task_id).status` works from the API. Postgres *can* be used for this, but Redis is orders of magnitude faster and Celery is optimised for it.
2. **Response cache** — When a user asks the same question twice, you return the cached embedding search result from Redis without hitting ChromaDB again (you already do this with `redis_cache.py`).
3. **Rate limiting** — You can use Redis atomic counters to throttle how many embedding API calls happen per second, avoiding OpenAI/Gemini rate-limit errors.

**What you can drop from Redis:** the long-term source of truth for task status. Don't rely on `AsyncResult` for durable state — always write the canonical status to `ingestion_jobs` in Postgres. Redis task results can expire; Postgres does not.

```
Celery task finishes
      │
      ├─► Redis   ← fast, ephemeral. Used by `AsyncResult().status`
      │             expires in 24h, that's fine
      │
      └─► Postgres ← durable. Used by /status endpoint and monitoring
                      never expires, queryable
```

**Is object storage necessary?**

For local dev: not strictly — you can write uploaded files to a Docker volume and read them from there.
For production or for reliability on retries: **yes, it is necessary.** Here's why:

- A worker that reads the file directly from the FastAPI container's memory (`UploadFile` bytes) cannot be retried — the bytes are gone once the HTTP request ends.
- If the file is only on the API container's local disk, a worker running on a different replica (or pod in Kubernetes) cannot read it.
- Object storage (MinIO locally, S3 in prod) is the **single shared persistent location** all workers can reach regardless of which host they run on.

**Minimum viable setup (Phase 2):**
- Use a **Docker named volume** (`uploads-data`) mounted to both the API and worker containers. This avoids MinIO complexity while keeping restarts safe. Upgrade to MinIO/S3 in Phase 5.

---

### Q2 — How should retries for failed tasks work?

There are two distinct failure types and they need different retry strategies:

#### Type 1 — Transient failures (network blip, ChromaDB momentarily unavailable)
Use **exponential backoff** so the worker doesn't hammer a recovering service:

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

#### Monitor tasks that land in the DLQ

```python
# A simple periodic task that alerts on DLQ size
@app.task
def check_dlq_health():
    with app.connection() as conn:
        queue = conn.SimpleQueue("ingest_dlq")
        size = queue.qsize()
        if size > 10:
            logger.critical(f"DLQ has {size} unprocessed messages — manual review needed")
```

---

### Q3 — Kafka: partition space, replication, error handling, DLTs, and monitoring

#### Partition sizing and disk space

Kafka stores messages on disk per-partition. The risk is running out of disk space. Control it with:

```properties
# broker config (server.properties or via Confluent)
log.retention.hours=168          # keep messages for 7 days
log.retention.bytes=10737418240  # OR cap per-partition at 10 GB (whichever first)
log.segment.bytes=1073741824     # roll to a new segment file every 1 GB
log.cleanup.policy=delete        # delete old segments (use 'compact' only for changelog topics)
```

**Choosing partition count:**
- Start with `partitions = max_consumers_you_will_ever_run`.
- You can increase partitions later but never decrease.
- For this project: **6 partitions** is a safe starting point (allows up to 6 parallel consumers).
- Partition key = `user_id` → documents from the same user always go to the same partition → ordered processing per user.

**Replication factor:**
```
Local dev:        replication_factor=1   (one broker, no replication)
Staging/prod:     replication_factor=3   (survives 1 broker failure)
```

#### Proper error handling in the Kafka consumer

```python
# workers/kafka_consumer.py
from confluent_kafka import Consumer, KafkaException, KafkaError
from confluent_kafka.admin import AdminClient, NewTopic

MAIN_TOPIC = "raw-documents"
DLT_TOPIC  = "raw-documents-dlt"   # Dead Letter Topic

consumer = Consumer({
    "bootstrap.servers": settings.KAFKA_BROKERS,
    "group.id": "document-ingestor",
    "enable.auto.commit": False,
    "auto.offset.reset": "earliest",
    "max.poll.interval.ms": 300000,  # 5 min — allow slow tasks
    "session.timeout.ms": 30000,
})

producer = Producer({"bootstrap.servers": settings.KAFKA_BROKERS})

consumer.subscribe([MAIN_TOPIC])

MAX_CONSUMER_RETRIES = 3

while True:
    msg = consumer.poll(timeout=1.0)
    if msg is None:
        continue
    if msg.error():
        if msg.error().code() == KafkaError.PARTITION_EOF:
            continue  # end of partition, not an error
        raise KafkaException(msg.error())

    headers = dict(msg.headers() or [])
    retry_count = int(headers.get("retry-count", b"0"))

    try:
        payload = json.loads(msg.value())
        publish_to_rabbitmq_with_confirms(payload)
        consumer.commit(message=msg)           # success: commit offset

    except Exception as exc:
        if retry_count < MAX_CONSUMER_RETRIES:
            # Re-publish to main topic with incremented retry header
            producer.produce(
                MAIN_TOPIC,
                key=msg.key(),
                value=msg.value(),
                headers={"retry-count": str(retry_count + 1).encode()},
            )
            producer.flush()
        else:
            # Exhausted retries → send to Dead Letter Topic
            producer.produce(
                DLT_TOPIC,
                key=msg.key(),
                value=msg.value(),
                headers={
                    "original-topic": MAIN_TOPIC.encode(),
                    "error": str(exc).encode(),
                    "failed-at": datetime.utcnow().isoformat().encode(),
                },
            )
            producer.flush()
            logger.error(f"Sent to DLT after {retry_count} retries: {exc}")

        consumer.commit(message=msg)   # always commit to move past the message
```

#### Dead Letter Topic (DLT)

| Term | RabbitMQ | Kafka |
|---|---|---|
| Name | Dead-Letter Queue (DLQ) | Dead Letter Topic (DLT) |
| Where failed messages go | Separate queue | Separate topic |
| Can you replay? | ❌ Manual | ✅ Re-consume from offset |

The DLT (`raw-documents-dlt`) is a regular Kafka topic. To replay failed messages:

```bash
# Re-process all DLT messages by resetting the consumer group offset
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group document-ingestor-dlt-replay \
  --topic raw-documents-dlt \
  --reset-offsets --to-earliest --execute
```

Or write a dedicated replay consumer that reads from the DLT and re-publishes to `raw-documents`.

#### Monitoring Kafka

```
What to watch                  Tool / Metric
─────────────────────────────────────────────────────────────
Consumer lag                   kafka-consumer-groups.sh --describe
                               OR Grafana + JMX exporter
                               OR Confluent Control Center

Partition disk usage           kafka.log:type=Log,name=Size
Broker CPU / network           JMX + Prometheus Kafka exporter
DLT message count              Consumer group offset on DLT topic
Offset commit rate             kafka.consumer:type=ConsumerFetchManagerMetrics
```

**Local setup (docker-compose):**
```yaml
# Add to docker-compose.yml
  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    ports:
      - "8080:8080"
    environment:
      KAFKA_CLUSTERS_0_NAME: local
      KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9092
```
This gives you a web UI to see topics, consumer lag, offsets, and DLT messages without any CLI.

---

### Q4 — Scaling: consumers can't keep pace with Kafka / Celery workers are overwhelmed

The scaling unit in Kafka is the **partition**. You cannot have more active consumers in a group than partitions. Here's the full scaling playbook:

#### Step 1 — Measure consumer lag first

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group document-ingestor

# Output:
# TOPIC            PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
# raw-documents    0          1000            1500            500   ← lag growing
```

Lag growing = consumers can't keep up. Lag shrinking = you're catching up. Lag stable near 0 = healthy.

#### Step 2 — Scale Kafka consumers horizontally

```
Partitions: 6
Consumer instances: 1  →  6       (each instance owns 1 partition)
```

```yaml
# docker-compose.yml
  kafka-consumer:
    image: your-app
    command: python -m workers.kafka_consumer
    deploy:
      replicas: 6   # must not exceed partition count
    environment:
      - KAFKA_GROUP_ID=document-ingestor
```

In Kubernetes (Phase 5), use KEDA to auto-scale based on consumer lag:
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: kafka-consumer-scaler
spec:
  scaleTargetRef:
    name: kafka-consumer-deployment
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: kafka:9092
        consumerGroup: document-ingestor
        topic: raw-documents
        lagThreshold: "100"      # scale up if lag > 100 messages
  minReplicaCount: 1
  maxReplicaCount: 6             # never exceed partition count
```

#### Step 3 — Scale Celery workers independently

Kafka consumers and Celery workers scale independently. Consumers dispatch fast; workers process slow (embedding is the bottleneck).

**In docker-compose (manual):**
```yaml
  worker:
    deploy:
      replicas: 4   # increase this
```

**With Celery autoscale (dynamic per container):**
```python
# celery worker --autoscale=8,2
# min 2, max 8 concurrent threads per container
app.conf.worker_autoscaler = "celery.worker.autoscale:Autoscaler"
app.conf.worker_max_tasks_per_child = 50   # restart worker process every 50 tasks
                                           # prevents memory leaks from large PDFs
```

**In Kubernetes with KEDA (on RabbitMQ queue depth):**
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: celery-worker-scaler
spec:
  scaleTargetRef:
    name: celery-worker-deployment
  triggers:
    - type: rabbitmq
      metadata:
        host: amqp://guest:guest@rabbitmq:5672/
        queueName: ingest_q
        queueLength: "20"    # scale up if > 20 messages waiting
  minReplicaCount: 2
  maxReplicaCount: 20
```

#### Step 4 — If you still can't keep up: increase Kafka partitions

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic raw-documents \
  --partitions 12    # double from 6 to 12
```

> ⚠️ Warning: increasing partitions changes the routing of messages by key. Only do this during a maintenance window or when you can tolerate brief out-of-order delivery for the same `user_id`.

#### Scaling summary

```
Bottleneck                     Solution
──────────────────────────────────────────────────────────────────
Kafka consumers slow           Add consumer replicas (max = partitions)
Too few partitions             Increase partitions, then add consumers
Celery workers slow            Increase worker replicas or --autoscale
Embedding API rate limit       Add delay/jitter in worker, use Redis rate limiter
ChromaDB write throughput      Batch upserts (index() accepts a list)
Memory leak in workers         Set worker_max_tasks_per_child = 50
```

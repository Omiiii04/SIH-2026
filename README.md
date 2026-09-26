# SIH-2026 — Distributed AI Inference Orchestrator

A distributed LLM inference system for Smart India Hackathon 2026.
Physical laptops run a **Worker Agent** alongside LM Studio.
The central **Orchestrator** accepts queries, classifies them, routes them to
the best available worker, and returns structured responses with full observability.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR (central)                   │
│                                                                 │
│  FastAPI  ─── classifier ─── dynamic worker registry           │
│     │                              │                            │
│     │                    PostgreSQL + ChromaDB                  │
│     │                    (workers, models, caps, interactions)  │
│  /api/v1/query           ┌──────────────────────────────┐       │
│  /api/v1/workers         │  Stale-worker sweeper        │       │
│  /health/cluster         │  Node health monitor         │       │
└─────────┬───────────────┴──────────────────────────────┘       │
          │ HTTP                                                   │
          │                                                        │
  ┌───────▼──────────┐   ┌──────────────────┐   ┌───────────────┐
  │  Worker Laptop A │   │  Worker Laptop B  │   │ Worker Laptop C│
  │                  │   │                  │   │               │
  │  worker/main.py  │   │  worker/main.py  │   │ worker/main.py│
  │  ─ discovers LM  │   │  ─ discovers LM  │   │ ─ discovers LM│
  │  ─ registers     │   │  ─ registers     │   │ ─ registers   │
  │  ─ heartbeats    │   │  ─ heartbeats    │   │ ─ heartbeats  │
  │  ─ runs infer    │   │  ─ runs infer    │   │ ─ runs infer  │
  │                  │   │                  │   │               │
  │  LM Studio :1234 │   │  LM Studio :1234 │   │ LM Studio:1234│
  └──────────────────┘   └──────────────────┘   └───────────────┘
```

**Key design principle:** No node capabilities are hardcoded.
Each worker discovers its local LM Studio models and advertises real capabilities.
The orchestrator routes based on what workers actually report.

---

## Registration Flow

```
Worker starts
     │
     ▼
GET {lm_studio_url}/v1/models          ← discover real models
     │
     ▼
Build WorkerRegistrationPayload        ← node_id, hostname, endpoint,
     │                                    models[], capabilities[], hardware{}
     ▼
POST {orchestrator_url}/api/v1/workers/register
     │
     ▼
Orchestrator stores worker record      ← in-memory + PostgreSQL
     │
     ▼
Worker enters heartbeat loop
     │
     ├── every HEARTBEAT_INTERVAL seconds ──►
     │       POST /api/v1/workers/heartbeat
     │       (updates last_heartbeat, keeps lease alive)
     │
     └── if heartbeat returns 404 ──► re-register
```

---

## Heartbeat & Lease

| Setting                | Default                  | Description                                          |
| ---------------------- | ------------------------ | ---------------------------------------------------- |
| `HEARTBEAT_INTERVAL` | 20 s                     | How often a worker sends a heartbeat                 |
| Lease                  | `interval × 3` = 60 s | Orchestrator marks worker OFFLINE after this silence |

- Worker sends heartbeat every 20 s.
- Orchestrator sweeper runs every 30 s (configurable via `HEALTH_CHECK_INTERVAL`).
- If a worker misses 3 heartbeats (60 s), it is marked **offline**.
- When the worker restarts and re-registers, it becomes **online** again immediately.

---

## Quick Start

### 1. Start the Orchestrator

```bash
# Clone and configure
git clone https://github.com/Omiiii04/SIH-2026
cd SIH-2026
cp .env.example .env
# Edit .env — set POSTGRES_* and CHROMA_* if you have them; otherwise they're skipped gracefully

# Install dependencies
pip install -r orchestrator/requirements.txt

# Start the orchestrator
python -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Join a New Laptop (Worker Setup)

On each worker laptop that has LM Studio running:

```bash
# 1. Clone the repo (or copy the worker/ directory)
git clone https://github.com/Omiiii04/SIH-2026
cd SIH-2026

# 2. Configure the worker
cp .env.worker.example .env.worker
# Edit .env.worker:
#   ORCHESTRATOR_URL=http://<orchestrator-ip>:8000
#   LM_STUDIO_URL=http://localhost:1234   (default for LM Studio)
#   WORKER_PORT=8100

# 3. Install dependencies
pip install fastapi uvicorn httpx pydantic pydantic-settings

# 4. Start the worker agent
python -m worker.main
# Or:
python -m uvicorn worker.main:app --port 8100
```

The worker will:

1. Discover models from local LM Studio (`GET localhost:1234/v1/models`)
2. Register with the orchestrator (`POST orchestrator:8000/api/v1/workers/register`)
3. Begin sending heartbeats every 20 seconds

### 3. Verify

```bash
# List all registered workers
curl http://localhost:8000/api/v1/workers

# Check a specific worker
curl http://localhost:8000/api/v1/workers/<node_id>

# Send a query (orchestrator picks the best available worker)
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo","query":"Write a Python hello world","input_type":"code"}'
```

---

## Configuration

### Orchestrator (`.env`)

| Variable                         | Default   | Description                               |
| -------------------------------- | --------- | ----------------------------------------- |
| `PORT`                         | 8000      | Orchestrator listening port               |
| `POSTGRES_HOST`                | localhost | PostgreSQL host                           |
| `POSTGRES_PORT`                | 5432      | PostgreSQL port                           |
| `POSTGRES_DB`                  | sih2026   | Database name                             |
| `POSTGRES_USER`                | sih_user  | DB user                                   |
| `POSTGRES_PASSWORD`            | change_me | DB password                               |
| `CHROMA_HOST`                  | localhost | ChromaDB host                             |
| `CHROMA_PORT`                  | 8001      | ChromaDB port                             |
| `HTTP_TIMEOUT`                 | 30.0      | Per-inference timeout (seconds)           |
| `HTTP_MAX_RETRIES`             | 3         | Max retry attempts on node failure        |
| `HEALTH_CHECK_INTERVAL`        | 30        | Seconds between health probes             |
| `NODE_1_URL` … `NODE_5_URL` | —        | Legacy static node URLs (still supported) |

### Worker (`.env.worker`)

| Variable               | Default                   | Description                      |
| ---------------------- | ------------------------- | -------------------------------- |
| `WORKER_ID`          | `hostname:port`         | Unique worker identifier         |
| `ORCHESTRATOR_URL`   | `http://localhost:8000` | Central orchestrator URL         |
| `LM_STUDIO_URL`      | `http://localhost:1234` | Local LM Studio URL              |
| `WORKER_PORT`        | 8100                      | Port the worker agent listens on |
| `HEARTBEAT_INTERVAL` | 20                        | Seconds between heartbeats       |
| `HTTP_TIMEOUT`       | 10.0                      | Timeout for orchestrator calls   |

---

## Worker API

The worker agent exposes its own small API:

| Method   | Path                       | Description                                  |
| -------- | -------------------------- | -------------------------------------------- |
| `GET`  | `/health`                | Liveness probe (also probes LM Studio)       |
| `GET`  | `/api/v1/workers/status` | Full status: models, capabilities, telemetry |
| `POST` | `/api/v1/workers/infer`  | Receive inference job from orchestrator      |

---

## Orchestrator Worker API

| Method   | Path                          | Description                                      |
| -------- | ----------------------------- | ------------------------------------------------ |
| `POST` | `/api/v1/workers/register`  | Worker self-registration                         |
| `POST` | `/api/v1/workers/heartbeat` | Worker heartbeat                                 |
| `GET`  | `/api/v1/workers`           | List all workers (filter with`?status=online`) |
| `GET`  | `/api/v1/workers/{node_id}` | Get single worker record                         |

### Registration Payload

```json
{
  "node_id": "my-laptop:8100",
  "hostname": "my-laptop",
  "endpoint": "http://192.168.1.50:8100",
  "lm_studio_url": "http://localhost:1234",
  "models": [
    {
      "model_id": "llama-3-8b-instruct-q4_k_m",
      "architecture": "llama",
      "quantization": "Q4_K_M",
      "context_length": 8192,
      "is_loaded": true,
      "modalities": ["text"],
      "capabilities": ["chat"]
    }
  ],
  "capabilities": ["chat"],
  "modalities": ["text"],
  "hardware": {
    "cpu_count": 8,
    "ram_total_gb": 16.0,
    "gpu_name": "NVIDIA RTX 3060",
    "gpu_vram_total_gb": 12.0
  },
  "runtime": {
    "lm_studio_url": "http://localhost:1234",
    "lm_studio_reachable": true,
    "model_count": 1,
    "worker_version": "0.1.0"
  },
  "heartbeat_interval": 20
}
```

Model capabilities are **derived from real model metadata**, not assumed.
A node running `llava-v1.5-7b` will advertise `["chat", "vision"]`.
A node running `nomic-embed-text` will advertise `["embedding"]`.

---

## Database Schema (new tables)

```sql
-- One row per registered worker
CREATE TABLE worker_nodes (
    id               UUID PRIMARY KEY,
    node_id          VARCHAR(128) UNIQUE NOT NULL,
    hostname         VARCHAR(256) NOT NULL,
    endpoint         VARCHAR(512) NOT NULL,
    lm_studio_url    VARCHAR(512) NOT NULL,
    status           VARCHAR(16)  NOT NULL DEFAULT 'offline',
    heartbeat_interval INTEGER    NOT NULL DEFAULT 20,
    -- hardware
    cpu_count        INTEGER,
    cpu_model        VARCHAR(256),
    ram_total_gb     FLOAT,
    gpu_name         VARCHAR(256),
    gpu_vram_total_gb FLOAT,
    platform_info    VARCHAR(512),
    -- timestamps
    registered_at    TIMESTAMP NOT NULL,
    last_heartbeat   TIMESTAMP,
    last_seen        TIMESTAMP
);

-- Models reported by each worker (replaced on each registration)
CREATE TABLE worker_models (
    id             UUID PRIMARY KEY,
    worker_node_id VARCHAR(128) REFERENCES worker_nodes(node_id) ON DELETE CASCADE,
    model_id       VARCHAR(512) NOT NULL,
    architecture   VARCHAR(256),
    model_type     VARCHAR(128),
    quantization   VARCHAR(128),
    context_length INTEGER,
    is_loaded      BOOLEAN NOT NULL DEFAULT TRUE,
    modalities     TEXT,   -- JSON array
    capabilities_str TEXT, -- JSON array
    discovered_at  TIMESTAMP NOT NULL
);

-- Capability tags per worker
CREATE TABLE worker_capabilities (
    id             UUID PRIMARY KEY,
    worker_node_id VARCHAR(128) REFERENCES worker_nodes(node_id) ON DELETE CASCADE,
    capability     VARCHAR(128) NOT NULL
);
```

---

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run only the worker registry tests
python -m pytest tests/test_worker_registry.py -v

# Run the original baseline tests
python -m pytest tests/test_health.py tests/test_nodes.py tests/test_router.py tests/test_routing_broadcast.py -v
```

Test categories:

- `test_health.py` — orchestrator health endpoints
- `test_nodes.py` — static node registry + stub clients
- `test_router.py` — query classification routing
- `test_routing_broadcast.py` — broadcast routing
- `test_worker_registry.py` — dynamic worker registry (new)
  - Worker registration (happy path)
  - Duplicate / re-registration (idempotent)
  - Malformed registration (missing required fields)
  - Model discovery from mock LM Studio
  - Stale heartbeat → worker marked offline
  - Worker recovery (re-registers → back online)
  - Capability persistence
  - All worker status API endpoints

---

## Backward Compatibility

The existing five-node static registry (`orchestrator/node_registry.py`) is **fully preserved**.
Existing APIs (`/api/v1/nodes`, `/health/cluster`, `/api/v1/query`, etc.) continue to work
exactly as before for the static nodes.

The new dynamic worker registry is **additive**:

- New routes: `POST /api/v1/workers/register`, `POST /api/v1/workers/heartbeat`, `GET /api/v1/workers`
- New database tables: `worker_nodes`, `worker_models`, `worker_capabilities`
- Workers that do not self-register are simply not in the dynamic registry

---

## Limitations

1. **Worker-side dispatch not yet wired to the main router**: The orchestrator's
   `/api/v1/query` still routes via the legacy static registry. Extending
   `handle_query()` to prefer dynamic workers over static ones is a natural next step.
2. **No authentication**: Worker registration and heartbeat endpoints are unauthenticated.
   A shared secret or mTLS should be added before production deployment.
3. **Worker agent hardware telemetry**: Requires `psutil` and optionally `GPUtil` /
   `py-cpuinfo` on the worker laptop. Install with:

   ```bash
   pip install psutil GPUtil py-cpuinfo
   ```
4. **LM Studio model metadata**: LM Studio's `/v1/models` response varies by version.
   Context length and architecture fields may not always be populated.
   The worker falls back gracefully to `None` for missing fields.

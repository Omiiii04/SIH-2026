# SIH-2026 — Distributed AI Inference System

> **Smart India Hackathon 2026 · Problem Statement SIH26117**

A distributed AI inference platform that routes user requests across five specialised laptop-hosted worker nodes, each running a different AI model via [LM Studio](https://lmstudio.ai/), coordinated by a central FastAPI orchestrator.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     Laptop 6 — Orchestrator                  │
│                                                              │
│   ┌─────────────┐   ┌───────────────┐   ┌────────────────┐  │
│   │  Next.js UI │──▶│  FastAPI      │──▶│  PostgreSQL    │  │
│   │  (frontend) │   │  Orchestrator │   │  (request logs │  │
│   └─────────────┘   │  + Router     │   │   node health) │  │
│                     └──────┬────────┘   └────────────────┘  │
│                            │            ┌────────────────┐  │
│                            │───────────▶│  ChromaDB      │  │
│                            │            │  (conv memory) │  │
└────────────────────────────┼────────────────────────────────┘
                             │ LM Link (LAN)
          ┌──────────────────┼──────────────────────┐
          ▼                  ▼                       ▼
   ┌─────────────┐   ┌─────────────┐   ┌───────────────────┐
   │  Laptop 1   │   │  Laptop 2   │   │  Laptops 3, 4, 5  │
   │  Text Node  │   │ Vision Node │   │  Reasoning / Code │
   │  LM Studio  │   │  LM Studio  │   │  / RAG  LM Studio │
   └─────────────┘   └─────────────┘   └───────────────────┘
```

### Components

| Component | Technology | Purpose |
|---|---|---|
| **Orchestrator** | FastAPI + Python 3.10+ | Receives requests, routes to the right node, logs results |
| **Router** | Custom heuristic engine | Keyword-based + explicit node-type routing |
| **Node: Text** | LM Studio (Laptop 1) | General-purpose chat / summarisation |
| **Node: Vision** | LM Studio (Laptop 2) | Multimodal image understanding |
| **Node: Reasoning** | LM Studio (Laptop 3) | Chain-of-thought / advanced analysis |
| **Node: Code** | LM Studio (Laptop 4) | Code generation, debugging, review |
| **Node: RAG** | LM Studio (Laptop 5) | Retrieval-augmented generation over documents |
| **PostgreSQL** | Docker | Request logs, node health, session metadata |
| **ChromaDB** | Docker | Semantic conversation memory (embeddings) |
| **Frontend** | Next.js + TypeScript | User interface (Phase 3) |

---

## Repository Structure

```
SIH-2026/
├── orchestrator/          # FastAPI app — main entry point
│   ├── main.py            #   App + API routes
│   ├── config.py          #   Settings (pydantic-settings, .env)
│   ├── models.py          #   SQLAlchemy ORM models
│   ├── schemas.py         #   Pydantic request/response DTOs
│   ├── router.py          #   Request routing logic
│   ├── health.py          #   Node health-check probes
│   └── requirements.txt   #   Python dependencies
├── nodes/                 # Worker node client stubs
│   ├── registry.py        #   Node registry (URL map + capabilities)
│   ├── text.py            #   Text node client
│   ├── vision.py          #   Vision node client
│   ├── reasoning.py       #   Reasoning node client
│   ├── code.py            #   Code node client
│   └── rag.py             #   RAG node client
├── database/              # Database layer
│   ├── postgres.py        #   Async SQLAlchemy engine + session factory
│   ├── chroma.py          #   ChromaDB client + memory helpers
│   └── models.py          #   Re-exports ORM models
├── tests/                 # Pytest test suite
│   ├── conftest.py        #   Shared fixtures (ASGI test client)
│   ├── test_health.py     #   Health endpoint tests
│   ├── test_router.py     #   Routing logic unit tests
│   └── test_nodes.py      #   Node registry + stub client tests
├── frontend/              # Next.js UI (Phase 3 — placeholder)
├── .env.example           # Environment variable template
├── .gitignore             # Git ignore rules
├── pytest.ini             # Pytest configuration
├── docker-compose.yml     # PostgreSQL + ChromaDB services
└── README.md              # This file
```

---

## Quick Start

### Prerequisites
- Python 3.10+
- Docker + Docker Compose (for PostgreSQL and ChromaDB)
- Git

### 1. Clone & navigate

```bash
git clone https://github.com/Omiiii04/SIH-2026.git
cd SIH-2026
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r orchestrator/requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual node IPs and DB credentials
```

### 5. Start infrastructure services

```bash
docker compose up -d
```

### 6. Start the orchestrator

```bash
uvicorn orchestrator.main:app --reload --host 0.0.0.0 --port 8000
```

### 7. Verify

```
GET http://localhost:8000/health        → 200 OK
GET http://localhost:8000/health/cluster → 200 OK (nodes offline until Phase 2)
GET http://localhost:8000/docs          → Swagger UI
```

---

## Running Tests

```bash
pytest
```

Expected output (Phase 1, no live nodes):
- `test_health.py` — all pass ✅
- `test_router.py` — all pass ✅
- `test_nodes.py`  — all pass ✅

---

## Development Phases

| Phase | Status | Description |
|---|---|---|
| **Phase 1** | ✅ Complete | Project initialisation, architecture, routing stubs, tests |
| **Phase 2** | 🔲 Planned | Live node communication via httpx, DB integration |
| **Phase 3** | 🔲 Planned | Next.js frontend, session management, RAG pipeline |
| **Phase 4** | 🔲 Planned | Load balancing, failover, monitoring dashboard |

---

## Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Default | Description |
|---|---|---|
| `NODE_TEXT_URL` | `http://192.168.1.101:1234` | LM Studio URL for text node |
| `NODE_VISION_URL` | `http://192.168.1.102:1234` | LM Studio URL for vision node |
| `NODE_REASONING_URL` | `http://192.168.1.103:1234` | LM Studio URL for reasoning node |
| `NODE_CODE_URL` | `http://192.168.1.104:1234` | LM Studio URL for code node |
| `NODE_RAG_URL` | `http://192.168.1.105:1234` | LM Studio URL for RAG node |
| `POSTGRES_PASSWORD` | *(required)* | PostgreSQL password |
| `DEBUG` | `false` | Enable uvicorn reload + SQLAlchemy echo |

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Orchestrator liveness probe |
| `GET` | `/health/cluster` | Full cluster node health |
| `POST` | `/infer` | Route an inference request |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc UI |

### POST /infer — Request Body

```json
{
  "session_id": "optional-session-uuid",
  "node_type": "code",
  "prompt": "Write a Python function to reverse a linked list",
  "parameters": { "temperature": 0.2 }
}
```

---

## Contributing

1. Branch from `main`
2. Follow the existing module structure
3. Add tests for any new logic
4. Run `pytest` before opening a PR

---

*Smart India Hackathon 2026 — Problem Statement SIH26117*

# Async Security Processor

> A production-grade asynchronous task processing API built with a **DevSecOps-first** mindset.

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Celery](https://img.shields.io/badge/Celery-5.3-37814A?logo=celery)](https://docs.celeryq.dev/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-FF6600?logo=rabbitmq)](https://www.rabbitmq.com/)
[![Redis](https://img.shields.io/badge/Redis-7.2-DC382D?logo=redis)](https://redis.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docs.docker.com/compose/)

---

## Overview

This project implements an **asynchronous security scanning pipeline** where a FastAPI gateway accepts requests and immediately delegates compute-intensive Nmap scans to a distributed Celery worker cluster. Results are persisted in PostgreSQL and the task state is tracked via Redis.

The architecture is designed to be **non-blocking**, **auditable**, and **resilient** — key attributes in security tooling.

```
Client → FastAPI (Gateway) → RabbitMQ (Broker) → Celery Worker (Nmap)
                ↑                                        ↓
           Redis (State)                       PostgreSQL (Audit Log)
```

---

## Architecture

### Component Responsibilities

| Service | Technology | Role |
|---|---|---|
| `api_gateway` | FastAPI + Uvicorn | HTTP API, input validation, task delegation |
| `celery_worker` | Celery 5 | Async task executor, Nmap orchestration |
| `rabbitmq` | RabbitMQ 3.13 | Message broker (AMQP) — task queue |
| `redis` | Redis 7.2 | Result backend — task state storage |
| `postgres` | PostgreSQL 15 | Persistent audit log for all scans |

### Key Design Decisions

- **Fire-and-forget pattern**: The API returns `202 Accepted` immediately, preventing HTTP timeouts on long scans.
- **UUID primary keys**: Prevents IDOR (Insecure Direct Object Reference) enumeration attacks.
- **Non-root Docker container**: The app runs as `secuser`, following the principle of least privilege.
- **JSON-only serialization**: Celery is configured to reject all non-JSON content, preventing deserialization attacks.
- **UTC timestamps strictly enforced**: All database records use timezone-aware UTC datetimes.
- **Connection pool tuning**: SQLAlchemy pool configured for concurrent worker load (`pool_size=10`, `max_overflow=20`).
- **Retry with backoff**: Celery tasks retry up to 3 times with exponential countdown on transient failures.
- **Hard + soft time limits**: Workers are killed after 1 hour (hard) with a 50-minute soft warning for graceful cleanup.
- **Migrations-as-Code:** Gestión evolutiva y segura del esquema de PostgreSQL mediante `Alembic`, inyectando credenciales en *runtime* y ejecutando migraciones automáticamente en el Entrypoint de Docker (`bash -c "alembic upgrade head && uvicorn..."`).
- **Mitigación DoS (Rate Limiting):** API protegida en capa L7 mediante `slowapi`, restringiendo la inyección de colas pesadas a 5 requests/minuto por IP devolviendo HTTP 429, protegiendo al broker de saturación o abusos de clientes autenticados.

---

## Project Structure

```
proyecto_async_sec/
├── api/
│   ├── main.py          # FastAPI app: route definitions and task delegation
│   └── schemas.py       # Pydantic models: ScanRequest, TaskResponse
├── core/
│   ├── config.py        # Pydantic Settings: env-driven configuration
│   └── db/
│       ├── init_db.py   # Table creation script (run once on bootstrap)
│       ├── models.py    # SQLAlchemy ORM model: SecurityScan
│       └── session.py   # Engine + SessionLocal factory with connection pool
├── worker/
│   ├── celery_app.py    # Celery application: broker, backend, security config
│   └── tasks/
│       └── network_scans.py  # scan_ip task: Nmap execution + DB persistence
├── Dockerfile           # Multi-stage build, non-root user, nmap installed
├── docker-compose.yml   # Full 5-service stack with healthchecks and volumes
├── requirements.txt     # Pinned Python dependencies
└── .env.example         # Environment variable template (copy to .env)
```

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) v2+
- (Optional, for local dev) Python 3.11+ with `venv`

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/your-username/async-security-processor.git
cd async-security-processor

# Create your environment file from the template
cp .env.example .env
```

Edit `.env` with your credentials before proceeding.

### 2. Start the full stack

```bash
docker compose up --build -d
```

This starts all 5 services. Wait for the healthchecks to pass (~30 seconds):

```bash
docker compose ps
```

### 3. Initialize the database

Run this **once** to create the PostgreSQL schema:

```bash
docker compose exec api_gateway python -m core.db.init_db
```

### 4. Verify everything is running

```bash
# API health (should return 200)
curl http://localhost:8000/docs

# RabbitMQ Management UI
open http://localhost:15672  # user/pass from your .env
```

---

## API Reference

### Submit a Scan

```http
POST /api/v1/scans
Content-Type: application/json

{
  "target_ip": "8.8.8.8"
}
```

**Response `202 Accepted`:**
```json
{
  "task_id": "3b2f1c4a-8e9d-4f2a-b1c3-d4e5f6a7b8c9",
  "status": "PENDING",
  "message": "Tarea encolada exitosamente en el broker."
}
```

Accepts both IPv4 and IPv6 addresses. Invalid IPs are rejected at the validation layer with `422 Unprocessable Entity`.

---

### Get Scan Status

```http
GET /api/v1/scans/{task_id}
```

**Response — Task pending:**
```json
{
  "task_id": "3b2f1c4a-8e9d-4f2a-b1c3-d4e5f6a7b8c9",
  "status": "PENDING"
}
```

**Response — Task completed:**
```json
{
  "task_id": "3b2f1c4a-8e9d-4f2a-b1c3-d4e5f6a7b8c9",
  "status": "SUCCESS",
  "result": {
    "ip": "8.8.8.8",
    "status": "completed",
    "open_ports_detected": 2,
    "db_persisted": true
  }
}
```

**Possible `status` values:** `PENDING` · `STARTED` · `SUCCESS` · `FAILURE` · `RETRY`

---

### Interactive API Docs

FastAPI auto-generates full interactive documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

| Variable | Description | Example |
|---|---|---|
| `RABBITMQ_USER` | RabbitMQ admin user | `sec_admin` |
| `RABBITMQ_PASS` | RabbitMQ password | `StrongPassw0rd!` |
| `RABBITMQ_HOST` | RabbitMQ hostname | `rabbitmq` (Docker) / `localhost` (local) |
| `RABBITMQ_PORT` | RabbitMQ AMQP port | `5672` |
| `REDIS_PASS` | Redis password | `AnotherStrongPassw0rd!` |
| `REDIS_HOST` | Redis hostname | `redis` (Docker) / `localhost` (local) |
| `REDIS_PORT` | Redis port | `6379` |
| `POSTGRES_USER` | PostgreSQL user | `sec_db_admin` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `SuperSecureDBPassword!` |
| `POSTGRES_DB` | PostgreSQL database name | `security_scans_db` |
| `POSTGRES_HOST` | PostgreSQL hostname | `postgres` (Docker) / `localhost` (local) |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |

> **Security note**: Never commit your `.env` file. It is listed in `.gitignore`.

---

## Task Lifecycle

```
POST /api/v1/scans
        │
        ▼
  [FastAPI validates IP]
        │
        ▼
  scan_ip.delay() ──── AMQP ────▶ [RabbitMQ Queue]
        │                                │
        │                                ▼
  202 Accepted ◀──────────     [Celery Worker picks up]
  { task_id }                           │
                                        ▼
                               [Nmap -Pn -F -T4 <ip>]
                                        │
                               ┌────────┴────────┐
                               ▼                 ▼
                         [PostgreSQL]         [Redis]
                         Audit record         Task result
                         persisted            stored
```

On failure (network timeout, Nmap error), the task retries up to **3 times** with a 30-second countdown before marking as `FAILURE`.

---

## Database Schema

**Table: `security_scans`**

| Column | Type | Description |
|---|---|---|
| `id` | `VARCHAR` (UUID) | Primary key — UUID prevents enumeration |
| `celery_task_id` | `VARCHAR` (indexed) | Links DB record to Celery task |
| `target_ip` | `VARCHAR(45)` (indexed) | Target IP (v4 or v6) |
| `open_ports_count` | `INTEGER` | Number of open ports detected |
| `raw_output` | `TEXT` | Full Nmap output for forensic analysis |
| `created_at` | `TIMESTAMPTZ` | Scan timestamp in UTC |

---

## Development Setup (without Docker)

```bash
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
# source venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Run the API (requires RabbitMQ and Redis running locally)
uvicorn api.main:app --reload

# Run the Celery worker (in a separate terminal)
celery -A worker.celery_app worker --loglevel=info --pool=solo
```

> On Windows, use `--pool=solo` for the Celery worker due to fork limitations.

---

## Stopping and Cleanup

```bash
# Stop all services
docker compose down

# Stop and remove all data volumes (full reset)
docker compose down -v
```

---

## Roadmap

- [ ] API Key authentication middleware
- [ ] `GET /api/v1/scans` — paginated scan history endpoint
- [ ] Structured logging with `structlog`
- [x] Alembic database migrations
- [ ] Celery Flower monitoring service in Docker Compose
- [x] Rate limiting with `slowapi`
- [ ] Unit and integration test suite (`pytest`)
- [ ] GitHub Actions CI/CD pipeline

---

## Security Considerations

This tool is intended for **authorized security assessments only**. Scanning IP addresses or networks without explicit permission is illegal in most jurisdictions. The authors assume no liability for misuse.

- Always run scans only against systems you own or have written authorization to test.
- Store your `.env` credentials securely and rotate them regularly.
- Do not expose port `8000` to the public internet without authentication in front of it.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI 0.110 |
| ASGI Server | Uvicorn |
| Task Queue | Celery 5.3 |
| Message Broker | RabbitMQ 3.13 (AMQP) |
| Result Backend | Redis 7.2 |
| Database | PostgreSQL 15 |
| ORM | SQLAlchemy 2.0 |
| Data Validation | Pydantic v2 |
| Containerization | Docker + Compose |
| Security Scanner | Nmap |
| Rate Limiting | slowapi 0.1.9 |
| DB Migrations | Alembic 1.13 |

# NL2SQL System

Natural Language to SQL system with LangGraph, Strawberry GraphQL, Qdrant hybrid RAG, and Next.js frontend.

## 文档

详细文档见 [`doc/`](doc/README.md) 目录：

- [NL2SQL 系统设计](doc/plan/NL2SQL%20系统设计.md) — 架构设计方案
- [项目结构](doc/structure/项目结构.md) — 目录与模块说明
- [项目启动](doc/startup/项目启动.md) — 环境配置与启动指南

## Quick Start

### 1. Start infrastructure

```bash
docker compose up -d
```

### 2. Install backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

### 3. Run migrations & seed

```bash
alembic upgrade head
python -m backend.scripts.seed
```

### 4. Start backend

```bash
uvicorn backend.api.main:app --reload --port 8000
```

### 5. Start Celery worker

```bash
celery -A backend.workers.tasks worker --loglevel=info
```

### 6. Start frontend

```bash
cd apps/web && npm install && npm run dev
cd apps/admin && npm install && npm run dev
```

## Architecture

- **Backend**: FastAPI + Strawberry GraphQL + LangGraph
- **Vector DB**: Qdrant (BM25 + dense + RRF)
- **Relational DB**: MySQL 8.0
- **Cache/Queue**: Redis + Celery
- **Frontend**: Next.js + Apollo Client

## GraphQL Endpoints

- HTTP: `http://localhost:8000/graphql`
- Subscription: `ws://localhost:8000/graphql`

## User Apps

- User UI: http://localhost:4000
- Admin UI: http://localhost:4001

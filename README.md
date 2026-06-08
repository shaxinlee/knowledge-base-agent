# Knowledge Base Agent Assistant

This repository contains the v0.1 internal Knowledge Base Agent Assistant.

The project is currently at a first-version Web Demo stage. Core backend and frontend flows such as auth, user management, knowledge bases, file upload, MinIO storage, document blocks/chunks, retrieval APIs, reranker client wiring, conversations, SSE demo chat, citations, traces, feedback, audit logs, and the main admin/user pages have been implemented in staged SDD-driven steps. Step 036 has completed a delivery audit for this first-version Demo boundary.

The current Demo is not yet a fully verified SDD v0.1 MVP. Real MinerU online parsing, a real embedding-service, a real reranker-service, and real LLM answer generation still require external service configuration. A clearly marked development-only Demo fixture route is available for demonstrating citation UI without claiming real production RAG quality.

## Primary References

- `AGENTS.md`: AI Coding rules for this repository.
- `docs/specs/SDD.v0.1.md`: source of truth for product scope, architecture, database design, API boundaries, milestones, and acceptance criteria.
- `docs/tests/TDD.v0.1.md`: source of truth for test scope, fixtures, cases, acceptance gates, and release blockers.
- `docs/demo/first-version-demo.md`: current first-version Demo startup, operation flow, acceptance boundary, and external dependency notes.
- `docs/demo/first-version-demo-acceptance-report.md`: Step 036 delivery audit report and first-version Demo acceptance conclusion.
- `docs/demo/frontend-acceptance-checklist.md`: first-version Demo frontend acceptance checklist for the fixture citation flow.
- `docs/progress/README.md`: staged development progress index.
- `docs/api/frontend-backend-api-contract.md`: readable frontend-backend API contract.
- `docs/api/openapi.v0.1.yaml`: machine-readable OpenAPI contract.
- `frontend/src/api/types.ts`: frontend TypeScript API types.

## Current Demo Contents

```text
backend/                  FastAPI backend, SQLAlchemy models, Alembic migrations, service clients, tests
frontend/                 Vue frontend with real API-backed demo pages
docs/demo/                Demo startup and acceptance boundary
docs/progress/            Step-by-step SDD development progress records
docs/specs/               SDD source of truth
docs/tests/               TDD source of truth
docs/api/                 API contract and OpenAPI

docker-compose.yml         local foundation services
.env.example               required environment variables
```

## First-Version Demo Startup

Create a local environment file first:

```bash
cp .env.example .env
```

Start the Demo stack:

```bash
docker compose up --build
```

Default local endpoints:

| Service | URL |
| --- | --- |
| Frontend | `http://localhost:5173` |
| Backend health | `http://localhost:8000/api/v1/health` |
| Qdrant | `http://localhost:6333` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

Expected backend health response:

```json
{
  "status": "ok",
  "service": "backend-api",
  "version": "0.1.0"
}
```

Default local Admin:

| Field | Value |
| --- | --- |
| Username | `admin` |
| Password | `AdminPassword123` |

For the current Demo operation flow and exact acceptance boundary, read `docs/demo/first-version-demo.md`.

Optional citation fixture for the local first-version Demo:

```bash
# Set DEMO_FIXTURE_ENABLED=true in .env first, then recreate backend-api.
docker compose up -d --force-recreate backend-api
docker compose exec backend-api python -m app.dev.seed_demo_fixture
```

The fixture creates `Demo Fixture 知识库`, `demo-rag-fixture.txt`, and `demo_user` / `DemoUserPassword123`. Use the recommended question printed by the command to exercise Chat citations. This is a development/demo path only; it does not replace real MinerU, embedding, reranker, or LLM validation.

## Backend Development

From the backend directory:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Run backend checks:

```bash
cd backend
black --check app tests migrations
ruff check app tests migrations
mypy app tests
pytest
```

## Frontend Development

From the frontend directory:

```bash
cd frontend
npm install
npm run dev
```

Useful frontend checks:

```bash
npm run typecheck
npm run build
```

## Current Demo Boundary

Current verified scope:

1. Auth, default Admin, access/refresh token, logout/revoke, RBAC.
2. Admin user management.
3. Knowledge base CRUD, soft delete, audit logs.
4. File upload validation, MinIO raw-files storage, file status, retry-parse entry, chunks view.
5. MinerU API client wiring in API mode, with fake-client tests.
6. Document block normalization and basic one-block-one-chunk metadata.
7. Embedding client abstraction, Qdrant client abstraction, indexing orchestration tests.
8. Retrieval API with Qdrant vector search, OpenSearch BM25 keyword retrieval with PostgreSQL full-text fallback, RRF merge, and reranker client wiring.
9. Conversations, messages, citations, traces, SSE demo chat, refusal path.
10. Helpful / unhelpful feedback and telemetry.
11. Real API-backed frontend pages for login, chat, files, chunks, knowledge bases, users, audit logs, profile, and logout.

Not yet fully verified:

1. Real MinerU online parsing requires `MINERU_API_TOKEN`.
2. Real bge-m3 embedding requires an embedding-service implementation.
3. Real BGE reranker requires a reranker-service implementation.
4. Real LLM answer generation is not implemented; current chat answer is template-based.
5. Full upload-to-cited-answer end-to-end verification is still pending.
6. The Demo fixture can show citation UI, but it is not a real external-service RAG acceptance result.

Any API change must update the readable API contract, OpenAPI file, frontend types, and related TDD cases together.

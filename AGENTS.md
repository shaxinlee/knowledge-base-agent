# Knowledge Base Agent Development Guide

This project implements the Knowledge Base Agent Assistant described in:

- `docs/specs/SDD.v0.1.md`

The v0.1 testing baseline is described in:

- `docs/tests/TDD.v0.1.md`

Before making product, architecture, database, backend, frontend, retrieval, or deployment changes, read and follow that specification first.

Development rules:

- Treat the v0.1 SDD as the source of truth for scope, boundaries, and acceptance criteria.
- Treat the v0.1 TDD as the source of truth for test scope, test data, acceptance gates, and regression coverage.
- Do not add features that the SDD explicitly excludes from v0.1 unless the user asks for a scope change.
- Preserve the required MVP flow: upload, parse, normalize, chunk, embed, hybrid retrieve, rerank, answer with citations, save trace and feedback.
- Keep implementation choices compatible with the specified stack: independent Web app, MinIO, mineru-service, Celery, PostgreSQL full-text search, Qdrant, local bge-m3 embedding, local BGE Reranker, SSE responses, and Docker Compose startup.
- Prefer small, verifiable increments that map back to numbered sections in the white paper.

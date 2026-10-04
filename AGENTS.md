# Engineering contract

Rivaline is a fictional UK batch manufacturer of industrial coatings. This repository
demonstrates integration of fragmented sales, stock, procurement, production, quality
and logistics records. All organisations, people, formulations and business data must
remain synthetic. Never infer or reproduce a real manufacturer's proprietary data.

## Architecture and ownership

Legacy CSV/Excel/SQLite → Python ETL with validation → PostgreSQL → FastAPI REST
and analytics views → decision support and Power BI. Python 3.12, SQLAlchemy 2,
Pydantic 2, pandas, scikit-learn, pytest and Docker Compose are the chosen stack.
Keep a modular monolith; no frontend, brokers, microservices or cloud infrastructure.

- `database/`: authoritative SQLAlchemy schema, configuration and session factory.
- `api/`: HTTP routers, response schemas and dependency wiring; future services own use cases.
- `data/legacy/`: documented synthetic input fixtures only.
- `etl/`: future ingestion, mapping, provenance and data-quality reporting.
- `analytics/`: future stable SQL reporting views; Power BI consumes these.
- `planning/`: future explainable forecasting, reorder and planning logic.
- `powerbi/`: future reporting assets and connection guidance.
- `scripts/`: explicit schema creation, deterministic seed and local API commands.
- `tests/` and `docs/`: executable evidence and architecture/business documentation.

## Mandatory rules

1. Inspect AGENTS.md and existing interfaces before architectural changes.
2. Extend the existing architecture rather than replacing it.
3. Never silently change database contracts used by other modules. Document changes,
   update affected tests and consumers, and introduce migrations before evolving deployed data.
4. Never commit secrets or credentials; use environment variables and ignored `.env` files.
5. Never claim tests passed unless actually executed. Record service limitations explicitly.
6. All business data must remain synthetic, labelled and reproducible.
7. Prefer explainable business logic over unnecessary complexity.
8. Phase 1 is foundation only. Further phases require explicit user approval.

## Standards

Use typed Python, snake_case functions/modules, small explicit interfaces, Decimal for
quantities and money, timezone-aware UTC timestamps and Ruff formatting/linting.
Do not connect to the database during module import or create tables at API startup.
Keep configuration in `database/config.py`; avoid hard-coded paths and runtime secrets in logs.
Use SQLAlchemy bound expressions, transactions, snake_case plural tables, named constraints,
business-code uniqueness, foreign keys and useful indexes. Do not cascade-delete traceability
records. `updated_at` is maintained by SQLAlchemy writes; external SQL writers must set it.
One inventory row identifies one item/warehouse/lot; units must match the item's canonical unit.
Quantities are numeric, never binary floats. Status values and database checks are contracts.

Run pytest and Ruff after changes. Keep unit tests independent of services; PostgreSQL
integration checks must be reported separately from SQLite portability checks. Verify README
commands. Document assumptions, unresolved risks and implemented versus planned capabilities.
Reject or quarantine invalid source rows in future ETL, preserve source keys and run lineage,
and never silently impute operational quantities. Units, dates, duplicates and references need
explicit validation. Update docs and ADRs when architecture changes.

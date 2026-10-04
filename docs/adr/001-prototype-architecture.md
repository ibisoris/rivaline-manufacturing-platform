# ADR 001 — Modular Python and PostgreSQL prototype

Status: accepted for Phase 1.

Context: a two-day fictional manufacturing case study needs traceable data integration,
explainable decisions and demonstrable evidence without infrastructure overhead.

- PostgreSQL provides relational integrity, transactions and an accessible reporting source.
- Python connects data processing, API services and later analytical work in one language.
- SQLAlchemy keeps schema and database access explicit; Pydantic validates configuration/HTTP contracts.
- FastAPI and REST provide small, documented HTTP interfaces without a custom frontend.
- Batch ETL matches legacy file exports and allows explicit validation, provenance and replay.
- Power BI is the planned reporting consumer, with stable SQL views separating reporting contracts.
- scikit-learn supports later reproducible baselines; no forecasting is implemented in Phase 1.

Excluded: React, Kubernetes, Kafka, microservices, brokers and cloud deployment. The prototype
has no demonstrated need for their operational cost. A modular monolith is easier to test,
explain and extend within the time budget.

Consequences: start with explicit schema creation, introduce migrations before schema evolution,
keep business rules in services, and validate PostgreSQL separately from fast SQLite tests.
Power BI, ETL and analytical choices are architectural commitments, not completed features.

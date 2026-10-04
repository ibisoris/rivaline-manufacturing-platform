# ADR 002: auditable snapshot ETL and a non-destructive baseline

Status: accepted for approved Phase 2.

Use explicit row contracts and small Python readers, openpyxl for Excel, existing SQLAlchemy
models for targets, and existing ETL run/issue tables for governance. No operational schema
change is necessary. An execution UUID makes run provenance unique while source business
identities remain stable across replay. The pipeline serializes local PostgreSQL runs, validates
references, uses row savepoints and commits the business transaction only after complete extraction.

Choose insert-or-compare over general upsert: identical rows replay safely; rejected rows can be
corrected; changes to trusted history require review. Preserve every run's issues. Files provide
transparent quarantine and receipts, with the database retaining rejection evidence for recovery.
This deliberately favours explainability over streaming, CDC and distributed infrastructure.

Alembic is appropriate now because verified persisted data must survive future changes. Freeze
the existing PostgreSQL DDL in baseline 0001_phase1. For an existing DB compare reflected schema
before stamping; for an empty DB execute the baseline. Do not rebuild or discard master data.
The migration adds only Alembic's version table to an adopted database. Business models are unchanged.

Limitations: small snapshots, one line per order, completed batches, no stock-ledger posting,
no automatic corrections to accepted history, and no atomic transaction across database and file
exports. Export failures are explicitly audited and recoverable by exporting rejects/replaying.

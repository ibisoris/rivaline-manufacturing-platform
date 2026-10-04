# ADR 003: versioned operational reads and shared reporting definitions

Status: accepted for Phase 3.

Extend FastAPI with /api/v1 GET resources and explicit Pydantic response/filter contracts. Preserve
the operational schema and the health endpoint. Read-only repeatable-read transactions protect
request consistency and accidental writes while authentication remains a later scoped concern.

Create six domain views and two reusable KPI views using Alembic revision 0002_reporting. Keep
quantity groups separated by unit/item type, avoid join fanout by aggregating children first,
and expose only measured dates/quantities. KPI APIs and future Power BI consume the same views.
Use bulk traceability queries rather than expanding the existing CLI's per-record lookups.

No new indexes are justified for the present small dataset: existing foreign-key indexes cover
the trace/detail joins and list ordering uses primary keys. Add indexes after measured workload
evidence, through migrations. No materialized views, cache tier, UI, ML, scheduling or cloud
infrastructure is introduced. Reporting downgrade removes views only, preserving business data.

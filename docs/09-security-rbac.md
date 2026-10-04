# Security boundary and future RBAC

This is a local portfolio prototype with entirely synthetic data. Authentication and authorization
are not implemented. Keep the API bound to localhost; do not treat it as a production public API.

Implemented: environment-based credentials, ignored `.env`, sanitized health/operational failures,
validated IDs/status/date/pagination inputs, bound ORM queries, explicit response schemas and
GET-only resources. Operational requests use PostgreSQL READ ONLY / REPEATABLE READ transactions.
Raw quarantine JSON is omitted from API responses; no unrestricted SQL endpoint exists.
API transaction restrictions do not change the configured database user's privileges.

Future production work: dedicated least-privilege API/reporting roles, authentication, role-permission
matrix for sales/stores/production/quality/planning, audit access policies, TLS, request limits and
authorization tests. No such deployment or RBAC enforcement is claimed in Phase 3.

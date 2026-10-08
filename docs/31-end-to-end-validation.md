# Phase 9 - final end-to-end validation

Completed across 2026-10-08/09 (Europe/London). Independent fictional manufacturing case study;
all business data is synthetic. Starting checkpoint: `4d389f3f41f6d3d7e05693753d23dc820550172d`,
branch main. Phase 9 makes no operational schema, business-calculation or Power BI definition changes.
No staging, commit or push is performed in this phase.

## Scope and audit

Reviewed README/AGENTS, architecture and ADRs, Phase 1-8 reports/runbooks, configuration/session
factory, all feature module interfaces, model relationships, migration chain, source generators,
ETL extraction/validation/loading/reconciliation, routers/services/schemas, inventory rules,
forecast evaluation, production allocation, Power BI contracts and tests. Actual code and fresh
outputs take precedence over historical phase descriptions.

| Layer | Implemented and evidenced | Important boundary |
|---|---|---|
| Database | 35 application tables, named constraints, revision 0006_production, 20 views | Alembic bookkeeping is not counted among application rows |
| Sources / ETL | Six deterministic sources, 464 rows, validation, savepoints, quarantine, source-key replay | No real ERP connectors or silent quantity imputation |
| API | Read-only operational/trace/KPI/planning routes; computational what-if POST | No production authentication/authorisation |
| Inventory | Pooled availability, BOM requirements, explained stored proposals | Assumed outstanding confirmed supply; no PO creation |
| Forecasts | 24-month separate archive, three Decimal baselines, chronological validation/holdout | Historical synthetic errors are not future accuracy guarantees |
| Production | Netting, whole-batch priority, shared materials/capacity and saved proposals | No automatic release, routing/shift optimizer or real execution |
| Power BI | Six pages, 62 visuals, 21 tables, 25 relationships, 39 measures | Import refresh is separate from plan generation; no scheduled cloud refresh |
| Portfolio | Four user screenshots, source provenance and technical walkthrough | No real deployment or measured 20% efficiency improvement |

## Reproducible read-only verification

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_phase9
.\.venv\Scripts\python.exe -m scripts.verify_db
```

`verify_phase9` requires the preserved prepared demo database and local quarantine summaries.
It uses READ ONLY / REPEATABLE READ sessions, compares the saved Phase 7 baseline, reconciles
both existing ETL runs, creates source fixtures only inside TemporaryDirectory, launches its own
hidden loopback API process on an available port, performs requests and terminates only that
owned process. It writes `docs/evidence/phase9-live.json`; it never reruns ingestion, saves a
forecast/plan or rebuilds Power BI. The temporary source directory is cleaned up automatically.

The fixed baseline is deliberately strict. A fresh legitimate installation has new audit IDs and
timestamps and may not match it; use normal tests and semantic reconciliation for that installation.
Failure to match should be investigated, not “fixed” by overwriting the demonstration database.

Evidence: [Phase 9 live results](evidence/phase9-live.json),
[baseline](evidence/phase7-before.json), [schema verifier](../scripts/verify_db.py),
[end-to-end verifier](../scripts/verify_phase9.py).

## Fresh database integrity and preservation

Native server: PostgreSQL 17.11. Schema verifier checked all model columns, nullability, primary,
foreign, unique and check constraints, master values, BOM/supplier relationships and absence of
remaining `phase1_test_*` schemas. All passed. Revision is `0006_production`; reporting views: 20.

- Application tables: **35**.
- Application records: **1,497**.
- Canonical Phase 7/9 all-table hash before and after:
  `328225ecb90dcbe82555c132c7a366068d424be834a2cc8691a168ebc6c0367c`.
- The older `verify_db` serializer reports
  `f41726ecc716747f642fd0e0a091e71f3778255a2f9308e326e5987d8b9fc38f`.
  Different serializers produce different hashes; compare like-for-like, not these two strings.

No migrations, master/policy seeding, ingestion, saved forecast generation or saved production
planning were run against public business data. PostgreSQL test writes use reviewed temporary
schemas and outer rollback. Before/after verification surrounds the final checks.

## Sources, ETL and traceability

Fresh isolated generation reproduced the six saved source files byte-for-byte. No tracked source
was overwritten. Existing sources contain 464 rows; the accepted/rejected split is 416/48.
Both local summaries and rejected exports reconcile with committed run/issue records, source
hashes, target identities, stored values and independent quantity totals.

| Preserved run | Extracted | Accepted | Rejected | Target receipts | Operational target inserts |
|---|---:|---:|---:|---:|---:|
| First | 464 | 416 | 48 | 944 | 944 |
| Replay | 464 | 416 | 48 | 944 | 0 |

Replay evidence is inspected, not recreated against public data. Fresh idempotency and failure
behavior are separately executed by isolated ETL tests. Audit runs/issues correctly grow on replay.
There are 96 issue events across two runs, not 96 unique bad business records.

Verified accepted example: SALE-0001 / SO-0001, SYN-CUS-001, SYN-FG-001, 100kg, price 12.50,
2026-01-02 order / 2026-01-09 due. Raw ` KG ` and ` Confirmed ` normalize explicitly.
The repeated SALE-0001 is rejected as `DUPLICATE_RECORD`. Full synthetic examples are in evidence.

A row rejection is not a fatal run failure. Fatal extraction/load failures roll back operational
writes and preserve failure audit. Local export failure after commit is separately classified.
Traceability was read via the actual returned order ID, with nested customer, product, production,
batch, QC, consumption/purchase/supplier and dispatch relationships. Tests additionally verify
mismatched-item links are rejected.

## Live HTTP and KPI verification

A fresh temporary API process served real loopback HTTP, not a mocked client. **18 checks passed**:
health, Swagger HTML, OpenAPI, sales, KPIs, inventory positions, reorder proposals, forecasts,
overall candidate evaluation, ETL runs, issues, order trace, production plan, capacity, constraints,
computational POST what-if, invalid limit and missing trace resource.

Healthy routes returned 200; `limit=0` returned 422; a missing positive order ID returned 404.
The full URLs/responses are in the JSON evidence. The temporary port is selected dynamically;
the public runbook uses the configured default 8000. GUI interaction with Swagger was not automated;
HTML/OpenAPI/HTTP behavior was exercised.

| Verified value | Result |
|---|---:|
| Orders / production batches | 48 / 48 |
| Inspected / passed batches | 48 / 48 |
| Batch QC | 100% |
| ETL acceptance / rejection | 89.66% / 10.34% |
| Data-quality issue events | 96 |
| RM-002 / RM-003 proposed reorder | 1,000 / 1,500 kg |
| Forecast rows / total demand | 12 / 8,535 kg |
| Selected-policy holdout observations | 12 |
| Selected-policy MAE / RMSE | 18.416667 / 23.973944 kg |
| Horizon net production | 1,175.999999 kg |
| December SYN-MIX required / available / shortfall | 11.76 / 10 / 1.76 hours |
| FG-002 December gross / stock offset / net / unmet | 948 / 104 / 844 / 844 kg |

The selected-policy metrics come from the same distinct selected-product/model holdout contract
as Power Query. `/forecasts/evaluation?scope=overall` returns three candidate aggregates, not this
mixed-policy measure. FG-002 itself requires 8.44h; 11.76h is the shared mixing total including
FG-001. Remaining time at FG-002's turn is 6.68h, so its entire batch remains unallocated.

The manual 5,000kg FG-001 computational scenario also passed: stock offset 2,000kg, net 3,000kg,
30h proposed, 10h available, 1,000kg allocated and 2,000kg unmet. It did not persist any records.

## Tests and engineering checks

Commands executed against the reviewed test isolation design:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m pytest -q --postgres --tb=short
.\.venv\Scripts\python.exe -m scripts.validate_powerbi
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

| Suite | Fresh result |
|---|---|
| Default | **99 passed, 6 skipped**, one existing warning, 27.99s |
| PostgreSQL-enabled | **161 passed**, one existing warning, 106.32s |
| End-to-end verifier | Passed: 18 HTTP checks, 464 isolated source rows, two reconciliations, preserved baseline |
| Native schema verifier | Passed: 35 tables, 1,497 rows, constraint/master checks, zero test schemas |

The six default skips require native PostgreSQL. Native tests use temporary rollback-isolated
schemas; BI reconciliation reads the preserved public schema. The warning is the existing
Starlette/httpx TestClient deprecation. Tests cover relational integrity, source determinism,
quarantine/replay, failure recovery, API validation, forecast chronology, planning constraints
and report-binding regression. No failed test was hidden or weakened for documentation.

## Power BI automated versus manual evidence

Automated schema/binding checks cover 76 documents, 62 visuals, 21 tables, 25 relationships and
39 measures. Fourteen documents use exact pinned schemas; 62 Desktop-saved visual containers use
explicit 2.12 structural compatibility checks because the declared 2.13 schema URL was unavailable.
This is not a claim of exact 2.13 conformance or native DAX/Power Query execution by Python.

The user previously confirmed Desktop open, PostgreSQL authentication, refresh and successful
rendering of all six pages after the Supplier.code / Material.code native-reference repair.
No visual-level fetch errors remained. That evidence and the rendered KPI values are recorded in
[Phase 7 validation](29-phase-7-validation.md). Phase 9 retains those reports/screenshots unchanged
and does not claim a new manual GUI inspection by the agent.

## Documentation, privacy and remaining checks

Public README retains four screenshots and detailed phase commands, adds linked navigation,
full technical explanations, accurate worked examples and a dynamic-run setup sequence.
The [public demonstration runbook](32-demo-runbook.md) contains technical steps, not personal
questions/answers or speaking notes. Personal learning material stays in an ignored local directory,
with no README link, tracked file or staged file. Candidate review excludes secrets, `.env`, PBIX,
`.pbi`, raw screenshots, quarantine exports and local caches.

Fresh-install instructions were inspected against actual entry points; no clean installation or
Docker deployment was performed in Phase 9. Isolated tests exercise provisioning behaviors but do
not replace a separate machine setup rehearsal. Screenshot hashes and report/model definitions
must remain unchanged. GitHub Markdown/Mermaid rendering and a timed human demonstration remain
manual review items. No cloud deployment, GUI website or additional architecture is introduced.

### Final documentation and privacy review

Final review on 2026-10-09 verified local Markdown destinations and heading anchors across public
project documentation. All 11 referenced script modules resolved, five CLI help commands passed,
and all 30 PowerShell blocks across the README, validation report, technical runbook and local
learning guide parsed successfully. Ruff lint, Ruff formatting and `pip check` passed.

All tracked and non-ignored candidate content was scanned for named prospective organisation
references, private-key/token patterns and actual local credential values without printing those
values. No matches were found. Ignore checks passed for `.env`, private learning material,
raw screenshots, PBIX files and Power BI local caches. No files are staged.

Byte comparison with HEAD confirmed that the legacy fixtures, curated screenshots and Power BI
project/report/model files are unchanged (allowing only Git line-ending normalization). The
20% efficiency objective remains explicitly fictional and proposed, not a measured achievement.
The final Git whitespace check passed after removing one trailing space in the README.

# Rivaline Power BI management intelligence

Open **RivalineOperations.pbip** in Power BI Desktop for the Phase 7 report. The original
RivalineOperations.pbix is retained unchanged locally and ignored; it does not contain the
newly authored Phase 7 definitions.

Status: **verified by code and against PostgreSQL; manual Desktop refresh/render validation passed**.
There are six PBIR report pages, 62 generated visuals, 21 model tables, 25 single-direction
relationships and 39 measures. No new PostgreSQL views or migrations were needed.

- [Connection, architecture, refresh and interview walkthrough](../docs/28-powerbi-management-intelligence.md)
- [Phase 7 validation report](../docs/29-phase-7-validation.md)
- [Entity grains, relationships and full DAX catalogue](model-and-measures.md)
- [Exact page/visual bindings and manual build/acceptance checklist](page-build-specification.md)

## First manual refresh

1. Open the PBIP, not the original PBIX. Verify the six nonsecret parameters in Power Query.
2. Connect to localhost:5432 / rivaline. Enter credentials only in Desktop's database
   authentication dialog. Python's .env is ignored and is not copied into Power BI.
3. Refresh all, check model relationships/measure evaluation, and inspect every page.
4. Confirm the reference values in the validation report before treating visuals as verified.
5. Save the project and review changes. Do not commit/push until explicitly authorised.

## Source control

Keep the PBIP, Report/SemanticModel textual definitions, .platform identities and required theme.
Ignore all .pbi local folders, binary PBIX exports and .phase7-backup. The original textual
project was backed up locally; the original PBIX hash is recorded in preservation evidence.
The schemas folder contains pinned Microsoft JSON schemas for offline validation.

## Reproduction and checks

```powershell
.venv\Scripts\python.exe -m scripts.build_powerbi
.venv\Scripts\python.exe -m scripts.validate_powerbi
.venv\Scripts\python.exe -m scripts.verify_phase7
.venv\Scripts\python.exe -m pytest -q tests/test_powerbi.py --postgres
```

Run from the repository root. Build is deterministic/offline but overwrites generated report/model
files; preserve or port Desktop edits before rebuilding. Validation uses the jsonschema dev
dependency. The live verifier is READ ONLY and does not create forecasts/plans, reload ETL,
change data or start Power BI. JSON validation does not prove TMDL parsing, DAX execution,
connector refresh, native visual-role behavior, tooltip rendering or page navigation in Desktop.

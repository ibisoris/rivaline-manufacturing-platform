# Data quality and quarantine

Every fixture is synthetic. `data/legacy/manifest.json` is the exact intentional-defect catalogue:
48 rows, each with department, 1-based record position, keys, mutated field/value and expected rule.
Valid normalization examples are retained alongside rejects; 416 rows remain acceptable.

Rules include MISSING_FIELD, INVALID_IDENTIFIER, INVALID_DATE, DATE_ORDER, INVALID_QUANTITY,
INVALID_UNIT, INVALID_REFERENCE, INVALID_STATUS, DUPLICATE_RECORD and DUPLICATE_BUSINESS_KEY.
Validation also guards product/BOM agreement, explicit consumption mass balance, purchase coverage,
per-row quantity limits and dispatch quality holds. Only kg/g conversion is allowed; litres are
rejected without a density assumption. Nonfinite and overprecision quantities are rejected.

Rejected rows create `data_quality_issues` with execution association, source/file, physical
position, original source/business key, category, human reason, severity, detection timestamp and
contract-column raw values. Database exceptions are reduced to a safe category; credentials and
arbitrary exception strings are not audit payloads. No real business data should enter this demo.

`data/quarantine/<run-code>/rejected.json` is an inspectable export of database issues;
`summary.json` stores counters, hashes and accepted receipts. Run directories are Git-ignored.
Exports use a temporary file then replace. If file export fails after DB commit, the audit run
becomes failed with EXPORT_FAILURE. Regenerate rejects using `scripts.run_etl export`; rerun
unchanged sources to recreate a complete summary safely. Database and filesystem commits cannot
be atomic; the explicit failure status avoids claiming otherwise. Preserve old run evidence.

Correct rejected source values, keep stable unique keys, and replay. Historical issues remain
open as observations of their original execution; they are not silently deleted or marked resolved.
Compare successive run codes to demonstrate correction. Conflicting edits to accepted history
need reviewed reconciliation/migration work, not automatic overwrite.

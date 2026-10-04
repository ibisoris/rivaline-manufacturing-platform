# Deterministic synthetic legacy environment

Run `python -m scripts.generate_legacy` to generate/reset the six owned files and manifest.
All companies, master references, records and formulations are fictional. No proprietary data.

- legacy_sales.db: SQLite records table.
- inventory_export.csv: stores snapshot.
- purchasing_register.xlsx: procurement records sheet.
- production_log.csv: completed batches with explicit material consumption and supplier lots.
- quality_inspections.xlsx: synthetic score inspection records sheet.
- dispatch_history.csv: order/batch fulfilment.

416 valid and 48 deliberately defective source rows. `manifest.json` gives exact defects,
positions, expected rules and file hashes. These small synthetic fixtures can be version controlled.
Generation replaces only owned fixtures/manifest; it never resets database records or quarantine.
See docs/07-integration-design.md for mappings and docs/18-etl-runbook.md for execution/recovery.

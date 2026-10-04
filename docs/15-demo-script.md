# Phase 2 demo

1. State that the organisation, sources, formulations and records are entirely synthetic.
2. Follow README configuration. Adopt the existing schema with `scripts.migrate_db`; seed masters.
3. Generate sources with `scripts.generate_legacy`; inspect the six files and defect manifest.
4. Run `scripts.run_etl run`. Show extracted/accepted/rejected and source breakdown.
5. Open that run's quarantine files; inspect unknown-reference, duplicate and invalid-date rejects.
6. Run `scripts.run_etl reconcile`; show matching accepted target values and mass totals.
7. Capture `scripts.run_etl snapshot`, repeat the ETL and capture it again. Business counts/hash
   should match while a new audit run and new issues show that execution occurred.
8. Run `scripts.run_etl trace --order SO-0001`; follow customer, product, batch, QC, actual
   material consumption, purchase orders and synthetic suppliers.
9. Run tests and show actual validation evidence. Explain that no forecasts or dashboard exist.

For a correction demo use a copied fixture directory and the runbook; do not overwrite trusted
history. Fixture regeneration resets only the owned input files, not the database or quarantine.

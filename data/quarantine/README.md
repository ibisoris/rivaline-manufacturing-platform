# Local quarantine

Each ETL run exports `rejected.json` and `summary.json` into its run-code directory.
Run directories are Git-ignored. Rejections also persist in `data_quality_issues` and can
be exported again with `python -m scripts.run_etl export --run ETL-...`.
Only synthetic inputs are supported. Keep audit evidence; fixture reset does not delete it.

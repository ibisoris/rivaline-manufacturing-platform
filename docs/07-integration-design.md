# Integration design and mappings

`etl/contracts.py` specifies exact ordered columns for each file. SQLite uses table `records`;
Excel uses sheet `records`. CSV is UTF-8. IDs/text are strings, dates are ISO YYYY-MM-DD,
prices are GBP per canonical kg, quantities use Decimal, and local date-only events map to
midnight UTC. Excel formulas are not evaluated. No operational quantity is imputed.

## Extract / transform / load

`extract.py` handles read-only SQLite, CSV and Excel; file-schema errors fail the execution.
`transform.py` validates/normalizes row fields and queries master/reference data.
`load.py` writes related target rows inside one savepoint. `pipeline.py` owns execution audit,
run transaction, row issues and quarantine. `reconcile.py` checks persisted receipts and lineage.
Pandas remains available but these small strict row contracts use standard readers/openpyxl.

| Source | Target mapping | Source/business identity |
|---|---|---|
| sales | sales_orders + sales_order_lines (line 1) | record_id; business_key -> order.code |
| purchasing | purchase_orders + purchase_order_lines (line 1) | record_id; business_key -> PO.code |
| inventory | inventory snapshot; no ledger posting | record_id; warehouse/item/business_key lot |
| production | production_orders + production_batches + four batch_material_consumption rows | record_id; business_key -> order/batch.code |
| quality | quality_inspections | record_id; batch/business_key -> test_code |
| dispatch | shipments + shipment_lines | record_id; business_key -> shipment.code |

All targets store `source_system=legacy_<department>` and `source_record_id`. Child line IDs use
`/1`; consumption IDs append the material ID. Source master aliases resolve to existing seed
records; ETL does not invent missing customers, suppliers or products. Production purchase_keys,
consumption_kg and supplier_lots are aligned pipe-separated source lists. Their values are
explicit synthetic observations. The BOM checks material coverage; it does not supply missing
actual consumption. Completed production maps to completed orders with released/quarantined/
rejected batches. Synthetic zero-loss inputs must equal output.

## Transaction and replay policy

One run record commits before extraction. PostgreSQL takes an advisory transaction lock to
serialize this loader. Per-row savepoints prevent partial headers/lines/consumption. Expected
validation or DB constraint failures become row rejects; successful operational records and
issues commit together after all selected sources. Unexpected failures roll back that transaction
and persist a failed run with a sanitized failure category. A database outage can prevent audit
persistence; a killed process may leave a running audit record requiring operator review.

In-file duplicates reserve the first normalized source/business key. Later occurrences reject,
even if the first occurrence was invalid. Across executions, source identity selects the target:
identical normalized fields are accepted unchanged, changed fields reject as REPLAY_CONFLICT,
and a business key owned by another source ID rejects. There is no destructive upsert or delete
propagation. Correct a rejected row while retaining its unique keys, then replay it; correct all
fields first because one deterministic first-failure rule is recorded per rejected row.

## Audit and reconciliation

`etl_runs.rows_read/rows_loaded/rows_rejected` count source rows, not target inserts; rows_loaded
includes unchanged replay. Successful runs satisfy read=loaded+rejected. A single source row can
create multiple targets. Report `inserted_targets` distinguishes actual writes from accepted replay.
A failed transaction reports loaded/rejected=0 and its extracted-so-far count; it has unprocessed
rows, so successful-run equality is not claimed. Export failure is separately classified after
business commit and preserves the committed counts.

Run summary JSON stores file basenames/hashes, source counters and accepted target receipts.
Reconciliation independently compares persisted fields and quantity totals against receipts,
checks audit arithmetic and quarantine identities, and detects later target tampering.
The CLI also re-reads source files, verifies their execution hashes and independently totals
accepted raw quantities against target totals. Preserve source snapshots for historical checks. Snapshot
hashes exclude audit tables so a repeat can grow audit history without changing business data.
Receipt verification covers accepted rows; it is not a general stock ledger balancing engine.

## Boundaries

Sources are small complete synthetic snapshots loaded in dependency order. One line per order
and one completed batch per sales order are demo conventions. Per-row quantity limits and QC
release checks exist; aggregate allocation across arbitrary partial shipments/batches, inventory
movement posting, unit conversions requiring density, incremental watermarking, concurrent file
editing and automatic correction of trusted history are out of scope. Stop source writers while
extracting; hashes detect ordinary changes during extraction but do not provide file locking.

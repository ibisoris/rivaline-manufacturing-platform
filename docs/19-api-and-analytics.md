# Phase 3: read-only API and reporting contracts

Rivaline and every record are synthetic. API metadata version is 0.3.0; operational contract
version is `/api/v1`. `/health` remains unchanged. There is no authentication, frontend,
forecasting, optimisation or Power BI dashboard in this phase.

## Architecture and transaction boundary

FastAPI routers validate Pydantic query models, call SELECT-only services, and serialize explicit
Pydantic response models. `api/dependencies.py:read_session` provides one PostgreSQL READ ONLY,
REPEATABLE READ transaction per operational request. This keeps list totals and items consistent
within a request and prevents accidental writes through that transaction. It is not a replacement
for production least-privilege roles. Connection failures produce sanitized HTTP 503 responses.
No schema setup, migration or database connection occurs during application import/startup.

List services execute a count and an ordered SELECT. Inventory detail is one joined query;
sales order detail uses at most two queries. Traceability uses seven bulk SELECTs regardless of
line/batch/inspection counts; tests assert that count with multiple batches. Existing foreign-key
indexes cover its joins. No new indexes were justified for these small snapshots.

## Endpoint catalogue

All endpoints below are GET-only. IDs are the existing positive integer database IDs; discover
them in list responses. Business codes such as SO-0001 are returned but are not interchangeable
with IDs in path parameters. `/docs` and `/openapi.json` describe every response schema.

| Route under /api/v1 | Filters beyond limit/offset | Date field |
|---|---|---|
| /products | active | none |
| /raw-materials | active | none |
| /suppliers | active | none |
| /customers | active | none |
| /inventory | warehouse_id, product_id, raw_material_id | none |
| /inventory/{inventory_id} | detail | none |
| /sales-orders | status, customer_id, product_id | order_date |
| /sales-orders/{order_id} | detail with ordered lines | none |
| /purchase-orders | status, supplier_id | order_date |
| /production-orders | status, product_id | planned_start |
| /production-batches | status, product_id, production_order_id | none |
| /quality-inspections | result, production_batch_id | inspected_at |
| /shipments | status, warehouse_id | shipped_at |
| /etl-runs | status | started_at |
| /data-quality-issues | etl_run_id, severity, status, source_system | created_at |
| /traceability/order/{order_id} | full order lineage | none |
| /kpis/operations | all-time KPIs; no filters | none |

Dated lists accept `date_from`/`date_to` as ISO dates. Bounds are inclusive; timestamp filters
use whole UTC days. Reversed bounds, malformed dates, unsupported statuses, nonpositive IDs,
unknown list query parameters and invalid pagination return 422. Unknown detail/trace IDs
return 404. A valid filter with no matches returns an empty page and total 0. Mutation requests
return 405. The API exposes no unrestricted SQL execution or raw quarantine payloads.

Pagination defaults: limit=50, offset=0, maximum limit=200. Results are ordered by integer ID.
`total` is the count after filters and before pagination; a large offset gives empty items.
Separate requests may see newly loaded data; offset paging is not a durable cursor protocol.
Quantities and money serialize as JSON strings to preserve Decimal precision. Dates are ISO;
timestamps carry timezone offsets on PostgreSQL. Units are explicit on items, inventory,
consumption and quantity KPIs; order-line quantities use the referenced item's canonical unit.

Example (the default seed gives product IDs discoverable through the products list):

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/products?limit=2&offset=0"
curl.exe "http://127.0.0.1:8000/api/v1/sales-orders?status=confirmed&limit=10"
curl.exe "http://127.0.0.1:8000/api/v1/inventory?warehouse_id=1"
curl.exe "http://127.0.0.1:8000/api/v1/traceability/order/1"
curl.exe "http://127.0.0.1:8000/api/v1/kpis/operations"
```

Lists return `{ "items": [...], "total": 48, "limit": 10, "offset": 0 }`. A typical
inventory quantity is `"500.000000"`. Undefined KPI percentages are JSON null, not zero.
Another operational system can discover schemas from OpenAPI, page through GET resources,
follow integer references, retain business codes/provenance and handle 404/422/503 explicitly.
No external integration client or cross-origin browser integration is supplied.

## Traceability shape and limits

The response contains the sales order, customer and lines. Each line contains the real product,
production orders and shipments. Each production order contains batches; each batch contains
inspections and material-consumption events. Consumption includes material, canonical unit,
quantity, supplier lot, purchase line/order, actual supplier and source provenance. Shipment
entries include shipment-line IDs and their batch IDs, linking dispatch back to those batches.

Missing downstream relationships produce empty arrays. No batch, QC result, receipt timestamp
or shipment is invented. Traceability preserves failed/pending QC results as facts. It does not
infer stock movements or allocate unlinked make-to-stock batches to customer orders. The endpoint
returns the complete selected order and is intended for bounded local demonstration datasets.

## Reporting view catalogue

Migration `0002_reporting` adds the following ordinary PostgreSQL views. They are current
SELECT results, not materialized snapshots; no refresh command is needed. Business tables and
rows are unchanged. Downgrade removes only these views in reverse dependency order.

| View | Grain | Definitions and aggregation cautions |
|---|---|---|
| vw_inventory_position | one inventory ID: warehouse/item/lot | On hand, reserved, available=on hand-reserved; product or raw-material unit; snapshot, not ledger |
| vw_order_fulfilment | one sales_order_line_id | Ordered quantity once; qualifying shipments pre-aggregated by line; first/last actual shipped_at; outstanding and overshipped quantities |
| vw_production_performance | one production_order_id | Planned quantity once; batch actuals/counts aggregated before joins; inspected/passed/released batch counts; planned dates only |
| vw_quality_performance | one inspection_id | Product/batch, recorded measurement/unit/result and pass/fail/pending indicators; no implied final inspection |
| vw_supplier_material_flow | one purchase_order_line_id | Actual PO supplier/material; ordered quantity once; consumption pre-aggregated by purchase line; consuming-batch count |
| vw_data_quality_summary | run/source/entity/rule/severity | Issue count; no-issue runs have one zero-count row with nullable issue dimensions; run totals deliberately not repeated |
| vw_operations_kpis | one all-time row | Counts, QC rate and successful-execution ETL rates; source for the KPI API |
| vw_operations_quantities | metric/item_type/unit | Unit-separated quantity totals; source for the KPI API; do not sum across metrics |

Shipment quantities count only dispatched/delivered shipments; pending/cancelled shipments do
not count. Sales cancellation does not erase shipment facts. Production pass counts require at
least one inspection and every recorded inspection to be pass; pending or failed tests prevent
that batch from passing. A batch without inspections is uninspected, not passed. Retests are not
collapsed because no authoritative final-test marker exists.

Purchase `expected_date` is not an actual receipt date. `order_marked_received` reflects the PO
status only; no received quantity, delivery performance or actual receipt timestamp is invented.
Supplier/material consumed totals can exceed ordered totals if later source data says so; the
view exposes observations rather than silently capping them. There are no measured production
start/end timestamps, so actual cycle time, OEE and efficiency improvements are not reported.

## Migrations and compatibility

Run `python -m scripts.migrate_db` before starting the new reporting/KPI routes. Existing versioned
DBs upgrade to head; a verified unversioned Phase 1 DB is stamped then upgraded without rebuilding.
The frozen baseline remains unchanged. Its original test now explicitly targets 0001_phase1,
while a separate live test verifies reporting upgrade/downgrade/re-upgrade and data preservation.
Future changes to view columns/grains or API response fields require documented contract review.
Missing views cause sanitized 503 on KPI requests; `/health` still tests connectivity only.

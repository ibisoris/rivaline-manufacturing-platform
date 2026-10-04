# Operational KPI dictionary (Phase 3)

These are descriptive measures over synthetic data, not measured transformation benefits.
The API reads `vw_operations_kpis` and `vw_operations_quantities`; later BI consumers should
use those same definitions. Scope is all-time because no KPI period filter is implemented.
Counts/rates are separate from quantities. Rates are percentages rounded to six decimal places;
a zero denominator produces null. Quantities retain canonical units and item types.

| KPI/API field | Business meaning and calculation | Grain/source | Limitations |
|---|---|---|---|
| order_count | Count sales orders with status other than cancelled | Order; sales_orders | Includes orders with zero lines; not monetary revenue |
| shipment_count | Count shipments marked dispatched or delivered | Shipment; shipments | Counts headers including any empty header; status does not prove delivery timestamp |
| production_batch_count | Sum batch_count for noncancelled production orders | Batch via vw_production_performance | Includes pending/rejected batches; no duration or efficiency interpretation |
| inspected_batch_count | Count eligible batches with one or more QC inspections | Batch via production view | Pending inspections still make a batch inspected |
| passed_batch_count | Count inspected eligible batches whose every inspection is pass | Batch via production view | Conservative all-history rule; no final/retest semantics available |
| batch_qc_pass_rate_pct | 100 * passed_batch_count / inspected_batch_count | All eligible inspected batches | Null without inspections; excludes uninspected batches, not a release-rate measure |
| etl_successful_runs | Count runs with status succeeded | Execution; etl_runs | A successful run can have rejected rows |
| etl_failed_runs | Count runs with status failed | Execution; etl_runs | Includes post-commit export failures; running executions are neither succeeded nor failed |
| etl_rows_extracted | Sum rows_read over successful runs | Execution events; etl_runs | Replay counts again; not distinct input/business records |
| etl_rows_accepted | Sum rows_loaded over successful runs | Execution events; etl_runs | Includes unchanged accepted replay, not insert counts |
| etl_rows_rejected | Sum rows_rejected over successful runs | Execution events; etl_runs | Fatal rollback/unprocessed rows excluded with failed executions |
| etl_acceptance_rate_pct | 100 * successful accepted / successful extracted | All successful execution rows | Weighted by rows, not mean of individual run percentages |
| etl_rejection_rate_pct | 100 * successful rejected / successful extracted | All successful execution rows | Same denominator; null when extracted is zero |
| data_quality_issue_count | Count all data_quality_issues rows | Issue; data_quality_issues | Includes repeated observations and failures; not unique defects; includes all issue statuses |

Quantity KPIs are returned as a list with `metric`, `item_type`, `unit_of_measure`, `quantity`.
When no relevant rows exist, the quantity group is absent rather than fabricating a unit.

| Metric | Calculation | Grain/source | Limitations |
|---|---|---|---|
| sales_ordered | Sum ordered_quantity for noncancelled sales orders | Sales lines; vw_order_fulfilment | Product unit; no prices or revenue calculation |
| sales_shipped | Sum shipped_quantity, including historical shipments against cancelled orders | Sales lines; fulfilment view | Only dispatched/delivered shipment statuses; overshipment not capped |
| inventory_on_hand | Sum on_hand_quantity by item type and unit | Warehouse/item/lot; vw_inventory_position | Cross-warehouse snapshot; do not infer current ledger balance |
| inventory_available | Sum on_hand-reserved by item type and unit | Inventory view | Does not apply expiry, QC holds or future demand deductions |
| production_planned | Sum planned_quantity for noncancelled production orders | Production order; vw_production_performance | Planned quantity counted once even with multiple batches |
| production_actual | Sum actual_quantity for those orders | Batch totals aggregated to production order | Includes actual recorded quantities of all batch statuses, not just released stock |
| procurement_ordered | Sum ordered_quantity for noncancelled purchase orders | Purchase line; vw_supplier_material_flow | Ordered, not actually received quantities |
| material_consumed | Sum recorded consumed_quantity, including historical consumption against cancelled POs | Consumption aggregated to purchase line; supplier flow view | Uses actual PO supplier, not preferred supplier; not receipt measurement |

Do not add sales, production, purchasing and shipment quantities together: they describe overlapping
flows. Do not add kg to L, or raw-material stock to product stock without explicit analytical intent.
No density conversion, stock-turn ratio, forecast accuracy, OEE, actual production lead time,
actual supplier delivery rate or claimed percentage improvement is supported here.

The verified Phase 2 fixture has 48 sales orders, 48 qualifying shipments, 48 inspected/passed
batches, 9,200 kg in each main flow, and 8,000 kg each of product and raw-material stock. Two
successful ETL executions produce 928 extracted, 832 accepted, 96 rejected events and 96 issues.
These counts describe the synthetic demonstration only; new runs/data legitimately change them.


Phase 4 inventory risk and reorder measures have a separate [calculation dictionary](22-inventory-and-reorder.md).
The Phase 3 KPI definitions above are unchanged; proposals are not incoming purchases or measured benefits.


## Phase 5 forecast metrics

MAE is mean absolute forecast error; RMSE is the square root of mean squared forecast error.
Both retain the product unit. WAPE is 100 * total absolute error / total actual demand; it is null
when the actual total is zero. Every candidate is reported per product and overall within a unit,
separately for validation and final holdout. Overall WAPE is not an average of percentages.
Naive is the required baseline. Selection uses validation MAE with deterministic simplicity ties.
The [forecast contract](24-demand-forecasting.md) defines windows, units, grains and limitations;
these are synthetic evaluation measures, not measured business improvements. Phase 3 KPIs are unchanged.

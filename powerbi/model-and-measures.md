# Power BI semantic model and DAX catalogue

Synthetic data only. Import mode. One configured vintage per forecast, reorder and plan.

## Imported reporting entities

| Entity | Source | Grain |
|---|---|---|
| Product | `products` | One product |
| Material | `raw_materials` | One material |
| Supplier | `suppliers` | One supplier |
| Customer | `customers` | One customer |
| Resource | `production_resources` | One production resource |
| Operations | `vw_operations_kpis` | Singleton all-time trusted operational summary |
| Inventory | `vw_inventory_risk` | One pooled raw material |
| Reorders | `vw_reorder_recommendations` | One recommendation in the selected reorder run |
| Orders | `vw_order_fulfilment` | One sales order line |
| Production | `vw_production_performance` | One operational production order |
| Quality | `vw_quality_performance` | One inspection; inspection rates differ from batch pass rate |
| Procurement | `vw_supplier_material_flow` | One purchase order line; orders are not measured receipts |
| Data Quality | `vw_data_quality_summary` | One ETL run/source/entity/rule/severity aggregate |
| Demand History | `vw_demand_history` | One archived dataset/product/month |
| Forecast | `vw_demand_forecast` | One selected forecast run/product/month |
| Backtest | `vw_forecast_backtest` | One selected-model product/holdout month; selected model joined without repeating horizon |
| Production Plan | `vw_production_plan` | One plan run/product/month |
| Capacity | `vw_capacity_utilisation` | One plan run/resource/month; capacity never taken from product lines |
| Planning Materials | `vw_planning_materials` | One plan run/product/month/material; availability is non-additive |

Calendar is a contiguous daily dimension from the earliest selected archive month to the latest
selected forecast period end. Month sorts by MonthIndex. Metrics is a one-row calculated measure
container. Auto date/time is disabled. UTC timestamps remain source metadata; period dates are
midnight dateTime keys. Decimal quantities use Power BI number/double to retain six-place inputs;
currency/fixed-decimal types would truncate to four places. Validate displayed six-place values
with tolerance 0.000001; PostgreSQL remains the exact Decimal authority.

## Relationships

Every link is dimension one -> fact many with single-direction filtering. No many-to-many,
bidirectional or fact-to-fact model relationships. The Backtest M join uses a distinct
product/selected_model table, so the three forecast horizon rows cannot multiply holdout errors.

| Many side | One side |
|---|---|
| Inventory[item_id] | Material[id] |
| Reorders[raw_material_id] | Material[id] |
| Orders[product_id] | Product[id] |
| Orders[customer_id] | Customer[id] |
| Orders[order_date] | Calendar[Date] |
| Production[product_id] | Product[id] |
| Production[planned_start] | Calendar[Date] |
| Quality[product_id] | Product[id] |
| Procurement[raw_material_id] | Material[id] |
| Procurement[supplier_id] | Supplier[id] |
| Procurement[order_date] | Calendar[Date] |
| Demand History[product_id] | Product[id] |
| Demand History[period_start] | Calendar[Date] |
| Forecast[product_id] | Product[id] |
| Forecast[period_start] | Calendar[Date] |
| Backtest[product_id] | Product[id] |
| Backtest[period_start] | Calendar[Date] |
| Production Plan[product_id] | Product[id] |
| Production Plan[resource_id] | Resource[id] |
| Production Plan[period_start] | Calendar[Date] |
| Capacity[resource_id] | Resource[id] |
| Capacity[period_start] | Calendar[Date] |
| Planning Materials[product_id] | Product[id] |
| Planning Materials[raw_material_id] | Material[id] |
| Planning Materials[period_start] | Calendar[Date] |

Operations is an intentionally disconnected all-time singleton. Product filters do not change
shared resource capacity; supplier filters affect procurement only. Resource filters affect
Capacity and Production Plan, while Planning Materials remains all-resource and is labelled so.
Different date roles and the separate archive universe are not forced into ambiguous joins.

## Measures

DAX is authored below and in Metrics.tmdl. Static bindings and equivalent PostgreSQL/Python
calculations are verified; DAX engine execution awaits Power BI Desktop refresh. Percent measures
return fractions and use percentage formatting, not multiplied values formatted twice.

### Orders

All-time noncancelled orders; unaffected by product/month filters.

```dax
MAX(Operations[order_count])
```

Format: `#,0`.

### Sales Quantity kg

Operational booked quantity, separate from the archived evaluation universe.

```dax
CALCULATE(SUM(Orders[ordered_quantity]), Orders[order_status] <> "cancelled", Orders[unit_of_measure] = "kg")
```

Format: `#,0.00`.

### Material On Hand kg

Pooled raw-material stock only; do not add finished goods.

```dax
CALCULATE(SUM(Inventory[on_hand_quantity]), Inventory[unit_of_measure] = "kg")
```

Format: `#,0.00`.

### Projected Material kg

Phase 4 available plus assumed incoming less current requirements.

```dax
CALCULATE(SUM(Inventory[projected_quantity]), Inventory[unit_of_measure] = "kg")
```

Format: `#,0.00`.

### Materials At Risk

Excludes at_reorder: equality does not trigger replenishment.

```dax
COUNTROWS(FILTER(Inventory, Inventory[risk_status] IN {"shortage", "below_safety", "below_reorder", "invalid_policy", "incomplete_bom"}))
```

Format: `#,0`.

### Recommended Reorder kg

Selected immutable reorder run, proposed status; not open supply.

```dax
CALCULATE(SUM(Reorders[quantity]), Material[unit_of_measure] = "kg", Reorders[status] = "proposed")
```

Format: `#,0.00`.

### Procurement Ordered kg

Ordered quantity, not measured receipts or on-time delivery.

```dax
CALCULATE(SUM(Procurement[ordered_quantity]), Procurement[unit_of_measure] = "kg", Procurement[order_status] <> "cancelled")
```

Format: `#,0.00`.

### Archived Demand kg

Alternative synthetic history; never add to operational sales.

```dax
CALCULATE(SUM('Demand History'[quantity]), 'Demand History'[unit_of_measure] = "kg")
```

Format: `#,0.00`.

### Forecast Demand kg

One selected forecast vintage, monthly future demand.

```dax
CALCULATE(SUM(Forecast[quantity]), Forecast[unit_of_measure] = "kg")
```

Format: `#,0.000000`.

### Holdout Actual kg

Actual demand on selected-model holdout months only.

```dax
SUM(Backtest[actual_quantity])
```

Format: `#,0.000000`.

### Holdout Prediction kg

Selected model prediction on holdout months only.

```dax
SUM(Backtest[predicted_quantity])
```

Format: `#,0.000000`.

### Holdout Variance kg

Signed holdout error; never future forecast minus missing future actual.

```dax
SUMX(Backtest, Backtest[predicted_quantity] - Backtest[actual_quantity])
```

Format: `#,0.000000`.

### Selected Policy MAE kg

Mean absolute error across selected-model test observations, not mean candidate MAEs.

```dax
AVERAGEX(Backtest, ABS(Backtest[predicted_quantity] - Backtest[actual_quantity]))
```

Format: `#,0.000000`.

### Selected Policy RMSE kg

Root of pooled squared selected-model test errors.

```dax
SQRT(AVERAGEX(Backtest, POWER(Backtest[predicted_quantity] - Backtest[actual_quantity], 2)))
```

Format: `#,0.000000`.

### Selected Model

Shows a single selected model only when filter context supports one.

```dax
SELECTEDVALUE(Forecast[selected_model], "Multiple selected models")
```

Format: `text`.

### Production Requirement kg

Forecast netted against original finished stock once across the horizon.

```dax
CALCULATE(SUM('Production Plan'[net_requirement]), 'Production Plan'[unit_of_measure] = "kg")
```

Format: `#,0.000000`.

### Inventory Offset kg

Stock offset within one selected plan; not new supply.

```dax
SUM('Production Plan'[inventory_offset])
```

Format: `#,0.000000`.

### Proposed Production kg

Includes any minimum-batch surplus; not approved execution.

```dax
SUM('Production Plan'[proposed_quantity])
```

Format: `#,0.000000`.

### Allocated Production kg

Whole batches that fit both materials and residual capacity.

```dax
SUM('Production Plan'[allocated_quantity])
```

Format: `#,0.000000`.

### Constrained Production kg

Unmet net demand, not the whole proposed quantity of a partly allocated line.

```dax
CALCULATE(SUM('Production Plan'[unmet_quantity]), 'Production Plan'[status] <> "FEASIBLE")
```

Format: `#,0.000000`.

### Proposed Batches

Proposed computational batches; no execution records.

```dax
SUM('Production Plan'[batch_count])
```

Format: `#,0`.

### Material Requirement kg

Component needs at plan/product/month/material grain.

```dax
CALCULATE(SUM('Planning Materials'[required_quantity]), 'Planning Materials'[unit_of_measure] = "kg")
```

Format: `#,0.00`.

### Material Shortage kg

Incremental shortages at the allocation turn, not a purchase instruction.

```dax
CALCULATE(SUM('Planning Materials'[shortage_quantity]), 'Planning Materials'[unit_of_measure] = "kg")
```

Format: `#,0.00`.

### Capacity Required Hours

Resource-month proposed workload; intentionally unaffected by product slicers.

```dax
SUM(Capacity[required_hours])
```

Format: `#,0.00`.

### Capacity Available Hours

Shared residual capacity counted once per resource/month.

```dax
SUM(Capacity[available_hours])
```

Format: `#,0.00`.

### Capacity Allocated Hours

Whole-batch allocated workload.

```dax
SUM(Capacity[allocated_hours])
```

Format: `#,0.00`.

### Capacity Utilisation %

Ratio of aggregate hours, not an average of row percentages; null if zero capacity.

```dax
DIVIDE([Capacity Required Hours], [Capacity Available Hours])
```

Format: `0.00%`.

### Capacity Shortfall Hours

Sum positive resource-month overload; spare capacity elsewhere cannot cancel it.

```dax
SUM(Capacity[overload_hours])
```

Format: `#,0.00`.

### December Mixing Required Hours

Explicit verified example; other cards show current page context.

```dax
CALCULATE([Capacity Required Hours], REMOVEFILTERS('Calendar'), REMOVEFILTERS(Resource), 'Calendar'[Month] = "2026-12", Resource[code] = "SYN-MIX")
```

Format: `0.00`.

### December Mixing Available Hours

Explicit December resource capacity, not horizon sum.

```dax
CALCULATE([Capacity Available Hours], REMOVEFILTERS('Calendar'), REMOVEFILTERS(Resource), 'Calendar'[Month] = "2026-12", Resource[code] = "SYN-MIX")
```

Format: `0.00`.

### Batch QC Pass Rate %

Phase 3 all-time eligible batch definition; not inspection pass rate.

```dax
DIVIDE(MAX(Operations[passed_batch_count]), MAX(Operations[inspected_batch_count]))
```

Format: `0.00%`.

### QC Inspections

Inspection-grain count, including repeats.

```dax
COUNTROWS(Quality)
```

Format: `#,0`.

### QC Passed Inspections

Passed inspection records; not released batches.

```dax
SUM(Quality[pass_indicator])
```

Format: `#,0`.

### ETL Accepted Rows

Successful execution events, including repeated accepted rows on replay.

```dax
MAX(Operations[etl_rows_accepted])
```

Format: `#,0`.

### ETL Rejected Rows

Successful execution rejected events, including replay.

```dax
MAX(Operations[etl_rows_rejected])
```

Format: `#,0`.

### ETL Acceptance Rate %

Weighted accepted/extracted across successful runs.

```dax
DIVIDE([ETL Accepted Rows], MAX(Operations[etl_rows_extracted]))
```

Format: `0.00%`.

### ETL Rejection Rate %

Weighted rejected/extracted across successful runs.

```dax
DIVIDE([ETL Rejected Rows], MAX(Operations[etl_rows_extracted]))
```

Format: `0.00%`.

### Data Quality Issues

Issue observations at ETL/run/source/rule grain; not distinct source records.

```dax
SUM('Data Quality'[issue_count])
```

Format: `#,0`.

### ETL Successful Runs

Audited successful ETL executions.

```dax
MAX(Operations[etl_successful_runs])
```

Format: `#,0`.

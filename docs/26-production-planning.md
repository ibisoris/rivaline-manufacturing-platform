# Production planning and capacity decision support

All organisations, quantities, policies and results are synthetic. Phase 6 proposes production;
it never approves a schedule or creates operational production orders, batches, purchases or
inventory transactions. The modular monolith and Phase 1-5 execution contracts remain unchanged.

## Scope and grain

A line is one product/month within one complete scenario or forecast vintage. A batch is a
computational quantity within that line, not a production_batches row. Capacity is one
resource/month; material detail is one plan line/raw material. All months use the first day.
Manual requests contain 1-48 unique product/month entries and at most 12 distinct months.
Quantities are nonnegative Decimal, at most 1,000,000 canonical units per entry, six decimal
places. A product/month is limited to 10,000 preferred batches. Missing policies, mismatched
units, missing/ambiguous active BOMs and incomplete open-production BOMs fail closed.

A forecast request identifies exactly one immutable Phase 5 run and processes its entire
three-month horizon before applying API display filters. A manual request is an explicitly
additional, standalone scenario. It is never added to forecast demand. Duplicate product/month
entries are rejected; the caller must aggregate disjoint demand explicitly.

Historical actual sales are not future forecasts. The existing fixture has no unfulfilled
confirmed sales. If any outstanding confirmed sales exist, forecast planning returns 409:
there is no governed forecast-consumption/allocation contract to establish overlap safely.
Manual additional demand remains supported with those commitments protected in the Phase 4
stock baseline. This conservative boundary prevents silently adding firm demand and forecasts.
Confirmed-order-to-plan integration is not claimed. No priority field can mislabel manual
input as an actual confirmed customer order.

## Demand netting

For each product, initial usable finished goods = max(Phase 4 projected stock, 0):

```text
projected finished stock = on_hand - reserved - outstanding_confirmed_sales
inventory_offset = min(gross_demand, remaining_original_finished_stock)
surplus_offset = min(gross_demand - inventory_offset, earlier_allocated_batch_surplus)
net_requirement = gross_demand - inventory_offset - surplus_offset
```

Stock is pooled across warehouses and lots, used once across chronological periods, and never
replenished implicitly each month. Remaining stock is decremented by its offset. Only allocated
minimum-batch overproduction creates hypothetical surplus for later periods. Proposed but
unallocated output never offsets later demand. Unmet demand is explicit and is not automatically
moved to another period or counted again. Production output is not assumed incoming finished
stock because its relationship to the inventory snapshot is not authoritative.

Phase 4 reservations and existing requirements are conservatively additive and can overlap;
that pre-existing allocation limitation is retained, not presented as exact available-to-promise.
No stock expiry, quarantine hold or warehouse-transfer feasibility is inferred.

## Synthetic policies and resources

| Product | Resource | Priority | Minimum kg | Preferred kg | Maximum kg | kg/hour |
|---|---|---:|---:|---:|---:|---:|
| SYN-FG-001 | SYN-MIX | 1 | 200 | 1000 | 1200 | 100 |
| SYN-FG-002 | SYN-MIX | 2 | 200 | 1000 | 1200 | 100 |
| SYN-FG-003 | SYN-FILL | 3 | 200 | 1000 | 1200 | 100 |
| SYN-FG-004 | SYN-FILL | 4 | 200 | 1000 | 1200 | 100 |

SYN-MIX is the synthetic Mixing Line and SYN-FILL the synthetic Finishing Line. Each has
**10 residual hours per month**, repeated for each requested month. These deliberately small
capacities demonstrate constraints. Residual means capacity assumed available after operational
commitments outside this proposal; it is not a full shift calendar or a measured factory rate.
The prototype does not derive existing execution load or send every product through both lines.
One resource per product is the explicit compatibility rule. Units/hour use the product's
canonical unit. There is no setup, cleaning, downtime, yield loss, routing, labour or overtime model.

`seed-policies` adds only missing synthetic keys and rejects conflicting values. Repeating the
seed adds zero rows. Database checks enforce minimum <= preferred <= maximum, positive rate,
positive priority and nonnegative capacity. Existing operational product/BOM/order tables are
not extended or redesigned.

## Batch sizing

Split net demand into preferred-size batches and a final remainder. If that remainder is below
the minimum, raise that final batch to the minimum. Do not merge it into a larger earlier batch.
All batches stay within maximum because minimum <= preferred <= maximum. Maximum is a safety
bound, not a target. Zero net demand produces no batches and no material or capacity consumption.

Examples: 2,300 kg -> [1,000, 1,000, 300]; 2,100 kg -> [1,000, 1,000, 200], proposing 2,200 kg.
The latter's 100 kg surplus carries forward only if allocated output actually exceeds net demand.
This is deterministic lot sizing, not cost optimisation.

## Materials and allocation

The service reuses `planning.inventory.scenario`, `positions` and `explode`: active BOM validation,
existing stock/incoming/requirements, and Decimal ROUND_HALF_UP explosion at six places. Material
requirement is the **sum of each proposed batch's rounded BOM requirement**:

```text
batch_component = round(batch_quantity * component_quantity / BOM_output_quantity, 6)
initial_material_available = max(Phase 4 projected material position, 0)
line_material_shortage = max(sum(batch_component) - remaining_material_available, 0)
```

Phase 4 already subtracts outstanding material needs of planned/released execution orders.
Confirmed purchase lines are assumed wholly outstanding and available at the planning start;
received/open/cancelled purchases and reorder proposals are not incoming supply. Expected dates
and partial receipts cannot establish time-phased availability. A FEASIBLE result is conditional
on these assumptions, not a promise that supplies arrive on time. Baseline deficits are protected
by flooring new allocatable supply at zero; reported shortages are for this incremental proposal.

Allocate in chronological month, ascending product-policy priority, then product-code order.
Within a line, visit proposed batches in sequence. Allocate a whole batch only if **both** every
component and the remaining resource hours suffice. Allocated batches decrement shared material
pools across the entire horizon and resource hours within the month. An unallocated batch consumes
neither. A smaller subsequent batch may fit even when an earlier larger batch cannot; this is
explicit greedy packing, not a sequence-dependent shop-floor schedule. Return rank, policy,
allocated quantity, residual capacity, batch reasons and unmet demand to explain the decision.

Existing firm commitments are protected before additional manual demand; they are not mixed
into the ranked forecast list. No invented confirmed-demand priority or black-box score is used.

## Capacity and statuses

```text
batch_hours = ceil_to_6_decimals(batch_quantity / units_per_hour)
line_required_hours = sum(batch_hours)
line_available_hours = resource hours remaining when this line is considered
line_overload = max(line_required_hours - line_available_hours, 0)
resource_month_required = sum(all proposed line hours on that resource/month)
resource_month_overload = max(resource_month_required - resource_month_available, 0)
utilisation_pct = round(100 * required_hours / available_hours, 2)
```

Zero available hours gives null utilisation (including zero demand), not division by zero or a
fabricated percentage. Six-place upward hour rounding makes allocation conservative; reported
rates/hours are synthetic planning arithmetic, not measurements at microhour precision. Capacity
utilisation uses proposed workload; allocated hours are separately reported. Do not sum line
available hours: they are successive views of the same shared resource pool.

Status tests the entire proposed line against material/capacity available at its allocation turn:
FEASIBLE, MATERIAL_CONSTRAINED, CAPACITY_CONSTRAINED, or MATERIAL_AND_CAPACITY_CONSTRAINED.
Material and capacity flags are assessed independently so one failure does not hide the other.
An apparently feasible capacity row only describes hours; inspect material/line status as well.
Explanations retain product, period, netting, batches, hours, rank, shortages and allocation.

## Persistence and reproducibility

Calculations and all HTTP routes write nothing. Only the explicit `save-forecast` CLI persists
one `production_plan_runs` row and normalized line/capacity/material rows, in one transaction.
These are decision-support evidence, never execution records. Resource/policy seed is a separate
explicit CLI action. What-if scenarios cannot be persisted by the CLI or HTTP.

The SHA-256 identity covers algorithm version, exact demand mode/vintage/rows, Phase 4 position
inputs, selected policies/resources, and every selected active BOM's component/output values.
The run stores complete inputs and structured output, plus UTC generation time. Exact replay
returns the original run/time and validates normalized reporting rows, refusing incomplete or
conflicting saved evidence. Changed inputs create a separate snapshot; returning to prior inputs
returns that original run. Existing runs are not overwritten. Snapshot immutability is an
application contract, not protection against database administrators. Single-process writers
are intended; unique constraints prevent uncontrolled concurrent duplicates but no retry service
or concurrency certification is provided.

Current API calculations can differ from historical reporting snapshots after stock/policy
changes. Use calculation_code versus plan_run_code to compare identical inputs, and explicitly
refresh via CLI when a new reporting snapshot is desired. Do not sum different plan runs.
The `persisted=false` field describes the computational report; the enclosing save CLI response
identifies the stored run. Old evidence retains the original computation rather than being relabelled.

## APIs

All routes use `/api/v1/planning`, Pydantic contracts, Decimal strings and the existing PostgreSQL
REPEATABLE READ / READ ONLY session. Even POST is computational. OpenAPI metadata is 0.6.0.

| Method and route | Contract |
|---|---|
| GET /production-plan | Required forecast_run_code; optional product_id, period_start, status, limit/offset |
| POST /production-plan/what-if | JSON demands list of product_id, period_start, quantity, unit_of_measure |
| GET /capacity | Same forecast filters; resource/month totals retain all competing products |
| GET /constraints | Same filters; only constrained product/month lines |

GET filtering/pagination happens after full-horizon allocation, so filtering cannot release
capacity or inventory assigned to another product. Capacity filters select resource/month keys;
they never remove competing load from their totals. Lists default to 50, maximum 200. Unknown
filters, duplicate demand, invalid dates/quantities or enum values return 422; unknown product/run
404; missing policy/BOM/unit conflict/unsupported firm-forecast overlap 409; database failure 503.
OpenAPI includes a POST example. All prior endpoints remain intact.

```json
{"demands":[{"product_id":1,"period_start":"2026-11-01","quantity":"5000","unit_of_measure":"kg"}]}
```

## Reporting views and migration

Alembic `0006_production` adds six tables and five views; previous migrations are unchanged.
Tables: production_resources, production_policies, production_plan_runs, production_plan_lines,
production_capacity_results, production_material_results. Foreign keys do not cascade-delete
traceability. Downgrade refuses while a plan run exists; empty-evidence downgrade removes the
new configuration, tables and views only. Migration tests run in rollback-isolated PostgreSQL schemas.

| View | Exact grain | Use |
|---|---|---|
| vw_production_plan | Plan run/product/month | Demand, offsets, net/proposed/allocated output, batches, hours, status and reason |
| vw_capacity_utilisation | Plan run/resource/month | Required, available, allocated, overload hours and utilisation |
| vw_planning_constraints | Constrained subset of plan run/product/month | Status and human-readable reason |
| vw_forecast_to_production | Plan run/forecast run/product/month | Forecast through net production and feasibility |
| vw_planning_materials | Plan run/product/month/raw material | Required, available, allocated, remaining and shortage quantities with units |

Only nonzero-production lines have material rows. Resource-month rows include zero-workload
months when products have demand covered by stock. Views read frozen snapshots, not live joins
to changed policy/stock values. Do not multiply product totals by joining material detail without
first aggregating at the appropriate grain. No Power BI file or dashboard is created.

## KPIs

Sum gross, inventory/surplus offset, net, proposed, allocated and unmet quantities within one run
and canonical unit. Batch count sums proposed line batches. Material requirements/shortages retain
raw-material identity/unit; availability is a successive shared pool, not an additive measure.
Capacity totals must use the resource/month view. Product counts classify a product as constrained
if any of its months is constrained; feasible products have all requested months feasible.
Feasible-plan percentage here is 100 * feasible product-month lines / all product-month lines;
label that grain explicitly and use null for an empty denominator. No measured business benefits
or production-time savings are claimed. See the KPI dictionary and validation report.

## Commands and future production considerations

```powershell
.venv\Scripts\python.exe -m scripts.migrate_db
.venv\Scripts\python.exe -m scripts.run_production seed-policies
.venv\Scripts\python.exe -m scripts.run_production forecast --forecast-run-code <Phase-5-run-code>
.venv\Scripts\python.exe -m scripts.run_production save-forecast --forecast-run-code <Phase-5-run-code>
.venv\Scripts\python.exe -m scripts.run_production what-if --product-id 1 --period 2026-11-01 --quantity 5000 --unit kg
.venv\Scripts\python.exe -m scripts.verify_phase6
```

Before real deployment: governed firm/forecast consumption, dated receipts, reservations and
inventory/QC availability, capacity calendars and operational workload, approved routings and
setup rules, approval/release state transitions, authentication and least-privilege roles are
required. No MES, autonomous purchasing/release, routing solver, UI or cloud infrastructure is
implemented. Later optimisation could compare greedy allocation against measured business
objectives and setup constraints, only with separately approved scope and reliable inputs.
Phase 7 Power BI remains unimplemented and requires approval.

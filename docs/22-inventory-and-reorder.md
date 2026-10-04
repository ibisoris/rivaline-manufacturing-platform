# Inventory intelligence and reorder decision support (Phase 4)

All organisations, stock, BOMs, policies and evaluation records are synthetic. These rules support
human decisions; they do not create purchase orders, select suppliers, forecast demand or schedule
production. Phase 5 requires separate approval.

## Business problem and scope

Operations needs an explainable comparison of stock, known requirements and replenishment policy.
The trusted records can support a pooled, all-time planning position. They cannot establish dated
warehouse allocations, partial purchase receipts, transit time, quality/expiry availability or a
complete stock movement ledger. The API therefore reports assumptions alongside the numbers.

The reusable implementation is `planning/inventory.py`, with typed shared contracts in
`planning/contracts.py`. API requests use the existing READ ONLY / REPEATABLE READ transaction.
Calculation persistence is only through the explicit local CLI. No connection or write occurs
at import/startup. Reporting definitions live in migration SQL and are shared by the API and
future Power BI consumers.

## Planning-policy reference data

`planning_policies` contains one policy per raw material, not one per lot. Quantities use the
material's canonical unit; a mismatch suppresses the proposal and generation rejects the run.
The warehouse is a proposed delivery destination, **not the scope of the stock calculation**.
All warehouse stock is pooled. No order or purchase warehouse allocation is inferred.
Finished products expose positions but have no raw-material purchasing policy.

| Synthetic material | Safety stock kg | Reorder point kg | Target kg | MOQ kg | Destination |
|---|---:|---:|---:|---:|---|
| SYN-RM-001 | 300 | 500 | 1000 | 100 | SYN-WH-RAW |
| SYN-RM-002 | 500 | 2500 | 3000 | 100 | SYN-WH-RAW |
| SYN-RM-003 | 2200 | 2400 | 3000 | 1500 | SYN-WH-RAW |
| SYN-RM-004 | 500 | 2000 | 3000 | 100 | SYN-WH-RAW |

These deliberately varied, deterministic teaching policies are defined in `planning/policies.py`.
They are not calibrated to real service levels, lead times or supplier terms. The seed adds only
missing policies, returns zero on replay and refuses conflicting existing values. It never edits
historical stock, production, purchasing, sales or BOM records. No lead time was added because this
phase has no dated delivery model. Database checks require 0 <= safety <= reorder < target and
MOQ >= 0; raw-material uniqueness prevents overlapping policies.

## Inventory definitions

Grain is one item type / item ID, across all warehouses and lots. All master items appear, even
without inventory rows, so an item without stock does not disappear from the risk calculation.
Canonical units are retained; different materials and product/material stock are never totalled
into an undifferentiated quantity.

```text
on_hand = sum(inventory.quantity)
reserved = sum(inventory.reserved_quantity)
available = on_hand - reserved
projected = available + assumed_confirmed_incoming - known_required
shortage = max(0, -projected)
```

For raw materials, known_required is the outstanding BOM requirement below. For products, it is
outstanding confirmed sales-line quantity from the existing fulfilment view (ordered minus
qualifying dispatched/delivered shipments, floored at zero). Open/unconfirmed, fulfilled and
cancelled sales headers do not add product demand. Raw-material demand comes from production
orders only: sales lines are not also exploded, avoiding duplicate requirements for linked orders.
Unscheduled sales demand is visible as a product commitment and is not silently converted into
production. Production output is not treated as incoming product stock because stock-posting
relationships do not establish whether that output is already included in the inventory snapshot.

Reserved stock and requirements have no allocation link. Deducting both is a deliberately
**conservative additive assumption** and may double count an overlapping commitment. Users must
resolve allocation overlap before purchasing. This is not an exact available-to-promise ledger.

Assumed incoming is the sum of whole confirmed purchase-line quantities. Open, received and
cancelled orders contribute zero. There are no receipt quantities; a confirmed line is assumed
wholly outstanding, with no partial receipt deduction. Expected dates are not used as guarantees.
Received quantities are never added again to on-hand stock. Existing reorder proposals are not
incoming supply, even if a proposal's status is accepted.

## BOM explosion and existing material requirements

Use the exact BOM selected on each planned/released production order. Completed/cancelled
orders contribute no future need. A selected historical BOM remains authoritative even if a
newer version exists; production is not automatically switched to another recipe.

```text
gross_component = round(planned_product_quantity * BOM_line_quantity / BOM_output_quantity, 6)
recorded_consumption = sum(consumption for this production order and material, across batches)
required_component = max(gross_component - recorded_consumption, 0)
```

The ratio is material-unit per product-unit. Component units can differ from the output unit;
no density conversion is inferred or needed for the BOM's explicit dimensional ratio. PostgreSQL
uses exact NUMERIC arithmetic; the pure what-if calculation uses Decimal with ROUND_HALF_UP.
Six decimal places match stored quantities. Very small requirements can round to zero at that
resolution. SQLite is a portability test backend and is not the production arithmetic authority.

Consumption is pre-aggregated before joining to BOM lines. Stock and purchase rows are separately
aggregated before joining to requirements: multiple batches, lots or purchase lines do not multiply
requirements. Requirements retain production order, sales line, product and BOM IDs. They identify
which requirements share a constrained material; no priority allocation or scheduling is performed.

An open production order with an empty BOM causes planning API/calculation error 409 rather than
an apparently healthy position. The risk view also exposes incomplete_bom_count and suppresses
recommendations with risk_status=incomplete_bom for direct reporting consumers. An empty/missing
or ambiguous what-if BOM is rejected. Quantities and referenced keys retain original constraints.

## Reorder formula and explanation

```text
if projected < reorder_point:
    recommended = max(target_stock - projected, minimum_order_quantity)
else:
    recommended = 0
```

The trigger is strictly below the reorder point. Equality is `at_reorder` with no order proposed;
this makes an item at its threshold visible without inventing a demand forecast. Safety stock
classifies `below_safety` risk, and reorder >= safety ensures a safety breach also triggers the
rule. A deficit is `shortage`; positive stock below the trigger is `below_reorder`; otherwise it
is `healthy`. `no_policy`/`invalid_policy` return null recommendations rather than interpreting
missing configuration as zero demand. Shortage is physical deficit, not the gap to target.
MOQ is a lower bound, not a pack-size multiple, and can restore stock above the target.

Each position contains the numeric inputs, thresholds, projected/shortage/recommended quantities,
risk status and a plain-language explanation. For example, the fixture's SYN-RM-002 has 2,000 kg
projected stock, below its 2,500 kg trigger, so it proposes 1,000 kg to restore a 3,000 kg target.
SYN-RM-003 proposes 1,500 kg because its MOQ exceeds the 1,000 kg target gap.

## Reproducibility, history and persistence

`planning_runs` stores a SHA-256 code over canonical JSON of algorithm version, ordered position
inputs/results and ordered requirement details. It stores that complete calculation snapshot and
an aware timestamp. The timestamp does not affect the hash. Proposals use the existing unchanged
`reorder_recommendations` table, source_system=phase4_reorder_v1, source_record_id=run_hash:material_id.
Its existing unique source key prevents duplicate proposals. Only positive proposals are saved;
a healthy calculation still has an auditable run with zero proposals.

The run and all proposals are committed atomically by the CLI. Exact-input replay returns the
original run/time and does not reset accepted/dismissed status. Changed relevant calculation
inputs create another immutable run; returning to old inputs returns that original run. Historical
proposals are not silently overwritten, cancelled or added together. Filter by run_code for a
single snapshot; old proposed rows do not imply additional purchase commitments. Snapshot numbers
remain unchanged even if current stock/policies change. These are application-level immutable
records, not protection against unrestricted direct SQL administrators.

Calculation identity covers relevant numerical inputs and requirement IDs, not every contributing
lot/purchase event ID. The underlying operational provenance remains available through Phase 3.
The run link uses the existing source-key convention rather than adding a nullable column to the
established proposal table. External legacy proposals can be listed with null snapshot/run fields.
Do not edit source keys manually. Run the local writer as a single process. Database uniqueness
rolls back conflicting concurrent generation; no distributed retry service is implemented.

## What-if behavior and HTTP endpoints

What-if uses GET because one product, quantity, canonical unit and optional BOM ID fit a small
validated query and the operation is read-only. It does not save runs, proposals, orders or stock.
Without bom_id, exactly one active BOM must exist. An explicit BOM must be active and match the
product. Incremental needs are added to the existing pooled position, never substituted for it.
The response includes baseline/scenario position, shortage/additional shortage, recommended quantity,
formula explanation and IDs of existing production requirements sharing each affected material.

All routes are under `/api/v1`:

| GET route | Filters / purpose |
|---|---|
| /inventory/positions | item_type, item_id, shortage_only; pooled positions and current rule result |
| /planning/material-requirements | raw_material_id, production_order_id; outstanding production BOM lines |
| /planning/material-availability | product_id, quantity, unit_of_measure, optional bom_id; what-if |
| /reorder-recommendations | raw_material_id, warehouse_id (destination), status, run_code; saved history |
| /reorder-recommendations/{id} | Saved proposal, frozen position and affected requirement rows |

Lists use the established items/total/limit/offset envelope, default 50, maximum 200. Ordering is
item type/ID, production order/material, or proposal ID as appropriate. Unknown list filters,
invalid IDs/quantities and unsupported units in query format return 422; unknown detail/product
404; unit mismatch or incomplete/ambiguous BOM 409; unavailable database 503. A canonical unit is
an exact case-sensitive identifier; a well-formed but mismatching unit returns 409. Decimal output
is strings. Proposal timestamps are serialized in UTC. OpenAPI metadata is now 0.4.0, retaining
all existing `/api/v1` contracts. Register positions before `/inventory/{inventory_id}` to preserve
both routes. No warehouse filter is offered for pooled positions; Phase 3 inventory supports
physical warehouse stock queries.

## Reporting views and migrations

| View | Grain | Intended use |
|---|---|---|
| vw_material_requirements | Open production order / BOM raw material | Gross, consumed and outstanding need with source order IDs |
| vw_inventory_risk | Item type / item ID, pooled | Current stock, requirements, incoming assumptions, policy, shortage and rule result |
| vw_reorder_recommendations | Persisted recommendation ID | Proposal history and linked calculation run/version; do not sum across runs |

`0003_planning` adds two tables and three ordinary views; no original table is changed.
`0004_fractional_bom` explicitly multiplies by numeric 1.0 before division, preventing SQLite's
integer-affinity truncation while retaining exact PostgreSQL NUMERIC behavior. It replaces only
the material-requirements view. The already-applied prior migration remains frozen.
No historical operational or ETL data is edited. Downgrade refuses to remove planning tables while
run history exists; explicit history archival would be a separately reviewed operation.

`PHASE1_TABLES` freezes the original 23-table scope. ETL business snapshots retain that scope;
they still include the original recommendation table and therefore legitimately change when new
proposals are generated. Phase 4 evidence compares original rows separately from authorized new
proposals. Baseline and Phase 3 migration tests target their fixed revisions. New tests check
current metadata equality, migration roundtrips and preservation; prior assertions remain covered.

## Commands and production considerations

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate_db
.\.venv\Scripts\python.exe -m scripts.run_planning seed-policies
.\.venv\Scripts\python.exe -m scripts.run_planning positions
.\.venv\Scripts\python.exe -m scripts.run_planning requirements
.\.venv\Scripts\python.exe -m scripts.run_planning calculate
.\.venv\Scripts\python.exe -m scripts.run_planning calculate
.\.venv\Scripts\python.exe -m scripts.run_api
curl.exe "http://127.0.0.1:8000/api/v1/planning/material-availability?product_id=1&quantity=10000&unit_of_measure=kg"
```

The deterministic demonstration has completed production and received purchasing records, so
zero current material-requirement rows is correct. Scenario tests create temporary synthetic
open requirements and incoming orders inside isolated test databases, never rewriting history.
The preserved stock is 2,000 kg per material; the 10,000 kg product what-if explodes to 2,500 kg
per component and exposes a 500 kg shortage for each of four synthetic materials.

Before production use, establish authoritative allocations/receipts, warehouse transfer rules,
unit governance, policy approval, snapshot freshness and expiry/QC availability. APIs are local
and unauthenticated. Reads are bounded in their response size, but this prototype calculates
complete pooled sets and loads proposal history before filtering; it is not certified for large
volumes. No concurrency/load benchmark, procurement integration or Power BI dashboard is claimed.
No measured stockout reduction or financial benefit is inferred from deterministic correctness.

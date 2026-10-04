# ADR 004: pooled, explainable inventory decision support

Status: accepted for the explicitly approved Phase 4 synthetic prototype.

The model has inventory reservations and production-selected BOMs, but no requirement allocations,
partial receipt quantities or order warehouse destinations. Use pooled stock with conservative
additive reservation/requirement deductions; treat confirmed purchases as wholly outstanding by
explicit assumption. Do not infer production, receipt or supplier performance states.

Add only planning_policies and planning_runs. Reuse reorder_recommendations and its unique source
keys for immutable content-addressed results. Do not evolve original operational tables. Writes
are explicit CLI transactions; HTTP remains read-only. GET what-if has a small scalar input and
no persistence. SQL reporting views and API share definitions; Decimal is used for scenario rules.

Policy destination warehouse is a proposed delivery location, not the stock aggregation scope.
Do not offer a misleading warehouse filter for globally unallocated requirements. Preserve existing
warehouse inventory routes. No forecast, supplier optimisation or autonomous purchasing is included.

Tradeoffs and exact arithmetic, status, snapshot and concurrency semantics are documented in
[the Phase 4 contract](../22-inventory-and-reorder.md). Production allocations/receipts and approved
policy governance would require a separately scoped schema/workflow review.

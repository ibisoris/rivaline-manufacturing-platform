# ADR 006: Explicit monthly production decision support

Status: accepted for the synthetic Phase 6 prototype.

Reuse Phase 4 stock/BOM arithmetic and one explicit Phase 5 forecast vintage. Keep manual
additional demand separate, rejecting unsupported firm/forecast overlap. Use chronological
product-policy/code prioritisation and whole-batch greedy allocation against shared materials
and residual resource-month capacity. This is explainable and testable without an optimiser.

Add small resource/policy tables rather than changing execution contracts. Persist optional
forecast snapshots only through an explicit CLI so stable reporting views have reproducible
inputs and outputs. HTTP, including POST what-if, stays READ ONLY. Immutable hash-keyed runs
prevent duplicate replay and preserve alternatives. No snapshot releases an operational order.

Tradeoffs: residual capacity and pooled/undated incoming are declared assumptions, not MES or
available-to-promise guarantees. Firm-demand forecast consumption is deliberately rejected
until an authoritative overlap contract exists. Whole-batch allocation can leave unused capacity
and unmet demand; it does not optimise margin, lateness or setups. See document 26 for formulas.

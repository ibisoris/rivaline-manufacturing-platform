# To-be: implemented Phase 2 integration

Generate departmental snapshots -> extract with strict file schemas -> normalize -> validate
master/dependent references -> load each valid row atomically -> audit and quarantine rejects
-> reconcile accepted target values -> demonstrate customer-to-supplier lineage.

The complete load order is sales, purchasing, inventory, production, quality, dispatch.
Bad rows do not enter trusted tables. Corrections to rejected rows can be replayed; conflicting
changes to already accepted rows require review. Every execution receives a new audit identity.
No forecasting, inventory decisions, production scheduling or dashboard is implemented.

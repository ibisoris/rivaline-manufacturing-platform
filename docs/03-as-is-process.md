# As-is: disconnected synthetic departments

Rivaline is fictional. Six exports represent departmental snapshots from January-February 2026.
They deliberately use inconsistent master codes, casing and units; none contains proprietary data.

| Department | File | Grain | Valid / defective rows |
|---|---|---|---|
| Sales | legacy_sales.db | records table, one single-line customer order | 48 / 8 |
| Procurement | purchasing_register.xlsx | records sheet, one single-line purchase order | 192 / 8 |
| Stores | inventory_export.csv | warehouse/item/lot stock snapshot | 32 / 8 |
| Production | production_log.csv | completed batch with four explicit material consumptions | 48 / 8 |
| Quality | quality_inspections.xlsx | synthetic score inspection per batch | 48 / 8 |
| Dispatch | dispatch_history.csv | single-batch shipment against one sales line | 48 / 8 |

Source owners are fictional departmental roles, not real people. Four raw-material
positions are served by the three fictional seed suppliers. Every completed product batch
has a customer order, four purchase lines, a QC result and a dispatch record.
Fixture generation uses fixed seed 20261003. The machine-readable manifest lists all 48
intentional defects, physical positions (1-based data rows), fields, values and expected rules.
The accepted code/unit variations are also deliberate: RM-001/rm001/RM_001, padded status
strings and grams versus kg. They normalize without becoming rejects.

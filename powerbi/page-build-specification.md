# Page and visual build specification

Generated PBIR contains six pages and 62 visuals at 1920 x 1080. The original first-page ID,
project/semantic-model references, compatibility level, culture and base theme are retained.
The page navigator is consistent across pages. Tables/charts use explicit titles and measure units.

This is a precise reconstruction/fallback specification, not evidence of visual rendering.
Open in Desktop to check built-in visual roles, query execution, text wrapping, cards, tooltips,
slicer propagation, totals and page navigation. Schema validation cannot prove those behaviors.

## Common Desktop acceptance steps

1. Open RivalineOperations.pbip, not the retained original PBIX. Set credentials locally and refresh.
2. Confirm all 21 tables, 25 relationships and 39 measures load. Mark Calendar[Date] as the date table
   if Desktop has not inferred it; keep automatic date tables disabled.
3. Check visual positions against the rectangles below; resize overflowing headers/table columns.
4. Use the existing base theme and slate titles; optional refinements must preserve measures/grains.
5. Ensure matrix/table totals never sum availability across allocation turns. Keep raw detail columns
   as Do not summarize. Keep source IDs available for audit; replace displayed IDs with code labels
   through Product/Material dimensions where desired without changing row grain.
6. On Demand & Forecasting, validate MAE/RMSE under Product filters. Clicking future months can
   correctly leave no holdout observations; optionally disable forward-chart interactions with
   accuracy cards so those cards retain the full holdout. Do not turn blanks into zero errors.
7. On Production & Capacity, select December and SYN-MIX to inspect 11.76/10h and 117.60%.
   December example cards intentionally ignore the month/resource selection and are clearly labelled.
8. Static reference text describes the verified synthetic fixture, not an automatically refreshed KPI.
   Review it when switching vintages. The report cannot submit what-if requests; the labelled 5,000kg
   scenario is evidence from Phase 6, separate from the saved forecast plan.

## Manual completion boundary

All target pages and visuals have been attempted and generated. No visuals are claimed rendered.
If Desktop rejects a built-in visual configuration, recreate that visual with the type, role
bindings and rectangle listed below; retain the semantic-model measure definitions. Validate
the remainder before saving. No automatic schema-version downgrade or silent repair is performed.

## 01  Executive Operations

Synthetic management view | Current stock, selected forecast and proposed production

| Type / title | x, y, width, height | Binding / content |
|---|---|---|
| card / Orders / all-time | 48, 170, 440, 140 | Values: Metrics[Orders] |
| card / Materials at risk | 508, 170, 440, 140 | Values: Metrics[Materials At Risk] |
| card / Batch QC pass / all-time | 968, 170, 440, 140 | Values: Metrics[Batch QC Pass Rate %] |
| card / Forecast demand / kg | 1428, 170, 440, 140 | Values: Metrics[Forecast Demand kg] |
| clusteredColumnChart / Material position / kg | 48, 340, 890, 300 | Category: Material[code]; Y: Metrics[Material On Hand kg], Metrics[Projected Material kg] |
| clusteredColumnChart / Required vs available capacity / hours | 962, 340, 890, 300 | Category: Calendar[Month]; Y: Metrics[Capacity Required Hours], Metrics[Capacity Available Hours] |
| tableEx / Management exceptions / proposed plan | 48, 668, 1350, 270 | Values: Production Plan[product_id], Production Plan[period_start], Production Plan[status], Metrics[Constrained Production kg] |
| textbox / Read first | 1420, 668, 432, 270 | December mixing needs 11.76 hours against 10 available. FG-002 has 844 kg unmet. These are synthetic proposed plans; no orders are released. Filters and future refreshes may change results. |
| textbox /  | 48, 25, 1800, 115 | 01  Executive Operations / Synthetic management view / Current stock, selected forecast and proposed production |
| pageNavigator /  | 48, 975, 1804, 58 | Built-in page navigation |

## 02  Inventory & Procurement

Pooled raw materials | Reorder proposals are not open purchase supply

| Type / title | x, y, width, height | Binding / content |
|---|---|---|
| card / On hand / kg | 48, 170, 440, 140 | Values: Metrics[Material On Hand kg] |
| card / Projected / kg | 508, 170, 440, 140 | Values: Metrics[Projected Material kg] |
| card / Materials at risk | 968, 170, 440, 140 | Values: Metrics[Materials At Risk] |
| card / Proposed reorder / kg | 1428, 170, 440, 140 | Values: Metrics[Recommended Reorder kg] |
| slicer / Material | 48, 335, 420, 100 | Values: Material[code] |
| slicer / Supplier / procurement only | 490, 335, 448, 100 | Values: Supplier[code] |
| clusteredColumnChart / Current stock and projected balance / kg | 48, 455, 890, 465 | Category: Material[code]; Y: Metrics[Material On Hand kg], Metrics[Projected Material kg] |
| tableEx / Reorder proposals / selected run | 962, 335, 890, 280 | Values: Material[code], Reorders[status], Reorders[reason], Metrics[Recommended Reorder kg] |
| tableEx / Supplier material flow / orders, not receipts | 962, 645, 890, 275 | Values: Supplier[code], Material[code], Metrics[Procurement Ordered kg] |
| textbox /  | 48, 25, 1800, 115 | 02  Inventory & Procurement / Pooled raw materials / Reorder proposals are not open purchase supply |
| pageNavigator /  | 48, 975, 1804, 58 | Built-in page navigation |

## 03  Demand & Forecasting

Archived actual demand and future forecasts are separate from operational sales

| Type / title | x, y, width, height | Binding / content |
|---|---|---|
| card / Forecast / kg | 48, 170, 440, 140 | Values: Metrics[Forecast Demand kg] |
| card / Selected-policy holdout MAE / kg | 508, 170, 440, 140 | Values: Metrics[Selected Policy MAE kg] |
| card / Selected-policy holdout RMSE / kg | 968, 170, 440, 140 | Values: Metrics[Selected Policy RMSE kg] |
| card / Selected model | 1428, 170, 440, 140 | Values: Metrics[Selected Model] |
| slicer / Product | 48, 335, 420, 100 | Values: Product[code] |
| lineChart / Archived demand and forward forecast / kg | 48, 455, 1120, 465 | Category: Calendar[Month]; Y: Metrics[Archived Demand kg], Metrics[Forecast Demand kg] |
| lineChart / Holdout actual vs predicted / kg | 1190, 335, 662, 280 | Category: Calendar[Month]; Y: Metrics[Holdout Actual kg], Metrics[Holdout Prediction kg] |
| tableEx / October-December forecast / kg per product/month | 1190, 645, 662, 275 | Values: Product[code], Forecast[period_start], Forecast[selected_model], Metrics[Forecast Demand kg] |
| textbox /  | 48, 25, 1800, 115 | 03  Demand & Forecasting / Archived actual demand and future forecasts are separate from operational sales |
| pageNavigator /  | 48, 975, 1804, 58 | Built-in page navigation |

## 04  Production & Capacity

Proposed plan | Whole batches compete for finite materials and residual hours. Separate verified what-if: FG-001 +5,000 kg -> 3,000 kg net; 30h needed vs 10h available; 2,000 kg unmet.

| Type / title | x, y, width, height | Binding / content |
|---|---|---|
| card / Net production / kg | 48, 170, 440, 140 | Values: Metrics[Production Requirement kg] |
| card / Unmet production / kg | 508, 170, 440, 140 | Values: Metrics[Constrained Production kg] |
| card / December mixing required / h | 968, 170, 440, 140 | Values: Metrics[December Mixing Required Hours] |
| card / December mixing available / h | 1428, 170, 440, 140 | Values: Metrics[December Mixing Available Hours] |
| slicer / Month | 48, 335, 400, 100 | Values: Calendar[Month] |
| slicer / Resource | 470, 335, 468, 100 | Values: Resource[code] |
| clusteredColumnChart / Resource capacity / hours | 48, 455, 890, 220 | Category: Resource[code]; Y: Metrics[Capacity Required Hours], Metrics[Capacity Available Hours] |
| tableEx / Capacity detail / one resource/month | 48, 700, 890, 220 | Values: Resource[code], Calendar[Month], Metrics[Capacity Required Hours], Metrics[Capacity Available Hours], Metrics[Capacity Utilisation %], Metrics[Capacity Shortfall Hours] |
| tableEx / Forecast to production / product/month | 962, 335, 890, 280 | Values: Product[code], Production Plan[period_start], Production Plan[status], Metrics[Production Requirement kg], Metrics[Allocated Production kg], Metrics[Constrained Production kg] |
| tableEx / All-resource material turns / kg, availability is not additive | 962, 645, 890, 275 | Values: Planning Materials[product_id], Planning Materials[period_start], Material[code], Planning Materials[available_quantity], Planning Materials[remaining_quantity], Metrics[Material Requirement kg], Metrics[Material Shortage kg] |
| textbox /  | 48, 25, 1800, 115 | 04  Production & Capacity / Proposed plan / Whole batches compete for finite materials and residual hours. Separate verified what-if: FG-001 +5,000 kg -> 3,000 kg net; 30h needed vs 10h available; 2,000 kg unmet. |
| pageNavigator /  | 48, 975, 1804, 58 | Built-in page navigation |

## 05  Quality & Data Trust

Audited records | ETL replay counts execution events, not unique business records

| Type / title | x, y, width, height | Binding / content |
|---|---|---|
| card / Batch QC pass / all-time | 48, 170, 440, 140 | Values: Metrics[Batch QC Pass Rate %] |
| card / ETL acceptance | 508, 170, 440, 140 | Values: Metrics[ETL Acceptance Rate %] |
| card / ETL rejection | 968, 170, 440, 140 | Values: Metrics[ETL Rejection Rate %] |
| card / Data quality issues | 1428, 170, 440, 140 | Values: Metrics[Data Quality Issues] |
| clusteredColumnChart / QC results / inspection counts | 48, 340, 890, 280 | Category: Quality[result]; Y: Metrics[QC Inspections] |
| clusteredColumnChart / Issues by source / observations | 962, 340, 890, 280 | Category: Data Quality[source_system]; Y: Metrics[Data Quality Issues] |
| tableEx / Validation rules and lineage | 48, 650, 1350, 270 | Values: Data Quality[run_code], Data Quality[source_system], Data Quality[rule_code], Data Quality[severity], Metrics[Data Quality Issues] |
| textbox / Trust boundary | 1420, 650, 432, 270 | Known synthetic fixture: 416 accepted and 48 rejected source rows per run. Two audited executions retain 96 issue observations. Customer-to-supplier traceability is available through the operational API. QC pass is not a production-release approval. |
| textbox /  | 48, 25, 1800, 115 | 05  Quality & Data Trust / Audited records / ETL replay counts execution events, not unique business records |
| pageNavigator /  | 48, 975, 1804, 58 | Built-in page navigation |

## 06  Transformation & Value

From fragmented records to explainable management decisions | Fictional case study

| Type / title | x, y, width, height | Binding / content |
|---|---|---|
| textbox / 01  Fragmented sources | 48, 175, 585, 245 | SQLite sales, CSV stock and production, Excel purchasing and quality. Synthetic data with reproducible defects. |
| textbox / 02  Trusted ingestion | 663, 175, 585, 245 | Python validation, explicit quarantine, source keys and ETL run lineage. Reconciliation protects quantities. |
| textbox / 03  Integrated operations | 1278, 175, 585, 245 | PostgreSQL shared records and stable reporting views. FastAPI connects orders, batches, inspections and suppliers. |
| textbox / 04  Explainable decisions | 48, 455, 585, 245 | Inventory rules, chronological forecast evaluation and finite-capacity production proposals. Reasons remain visible. |
| textbox / 05  Management intelligence | 663, 455, 585, 245 | Compare demand with supply, inspect material risk, identify the December capacity bottleneck and review data trust. |
| textbox / 06  Honest value proposition | 1278, 455, 585, 245 | Improved visibility is demonstrated by connected evidence. No financial ROI, time saving or operational improvement is claimed without measurement. |
| textbox / Demonstration route | 48, 760, 1800, 165 | Start with executive exceptions. Inspect RM-002 / RM-003 reorder proposals. Review selected-policy holdout MAE. Show December mixing: 11.76 hours vs 10, with 844 kg FG-002 unmet. Finish with audited ETL and traceability. This is decision support, not autonomous execution. |
| textbox /  | 48, 25, 1800, 115 | 06  Transformation & Value / From fragmented records to explainable management decisions / Fictional case study |
| pageNavigator /  | 48, 975, 1804, 58 | Built-in page navigation |

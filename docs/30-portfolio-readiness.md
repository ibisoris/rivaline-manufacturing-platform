# Phase 8: portfolio and interview readiness

Prepared 2026-10-08 as an independent, fictional manufacturing digital transformation case
study for a general professional portfolio. Rivaline connects process-manufacturing data to
operational intelligence and decision support. All business data remains synthetic.

## Deliverables

- Main README: four dashboard images, six-page guide, PostgreSQL Import-mode connection,
  integration/ETL/quality/traceability/forecasting/inventory/capacity evidence and an eight-minute demo.
- The proposed 20% production-efficiency improvement is a fictional business-case objective,
  explicitly a target, not a measured result.
  The README gives a prospective baseline and evaluation approach without inventing ROI.
- Existing phase workflows and documentation retained; stale reporting status statements corrected.
- `docs/images/powerbi/`: four optimized PNGs, provenance and reproduction instructions.
- `scripts/prepare_powerbi_screenshots.ps1`: deterministic Windows crop and decoded-pixel verification.
- Raw captures in `screenshots-temp/` ignored; no application, database or report-model edits.

## Image validation

All four originals opened successfully and were visually inspected. Crops remove only external
Desktop ribbon/tab strips, preserve full canvas width and report navigation, and retain every
pixel of the selected dashboard area. No resampling or generated image content is used.

| Image | Original bytes | Optimized bytes | Output size |
|---|---:|---:|---|
| Executive | 79,846 | 56,296 | 1335 x 740 |
| Inventory | 98,537 | 60,293 | 1306 x 744 |
| Forecasting | 111,587 | 71,671 | 1305 x 742 |
| Production | 105,779 | 72,219 | 1298 x 737 |

Total: 395,749 to 260,479 bytes (34.2% reduction), with decoded cropped pixels unchanged.
Hashes and exact crop boxes are in [provenance](images/powerbi/provenance.json).

## Command verification and boundaries

README modules and argument choices were checked against actual implementations. Migration,
seeding, legacy generation/ETL, policy generation and saved snapshot commands were reviewed
without rerunning them against the verified business database. Their write behavior is labelled.
Forecast code placeholders use valid PowerShell variable syntax. Docker remains an alternative
not executed on this machine; initial installation and provisioning are not claimed retested.

Read-only interview commands, API route contracts, local Markdown links, PowerShell code-block
syntax and crop reproduction are checked separately from application regression tests.
Native PostgreSQL Power BI tests are separate from service-independent/SQLite default tests.
The exact Desktop visual schema 2.13 remains unavailable; the existing explicit 2.12 structural
compatibility check is retained, alongside prior user-confirmed Desktop validation.

## Remaining manual checks

- Preview the README in GitHub at desktop and narrow widths after publication; check image zoom
  and Mermaid layout. No remote publication is authorised in this phase.
- Rehearse the five-, eight- or ten-minute narrative with local credentials already configured;
  clear slicers and use the saved run parameters before opening each page.
- Scroll tables in Desktop for truncated cells/rows; supplied screenshots intentionally preserve
  the original viewport. Do not interpret an off-screen row as missing data.
- Review the portfolio narrative for clarity with a general technical and business audience.
  Distinguish implemented capabilities, synthetic validation evidence and proposed future outcomes.

The implementation and wording-review stages were completed without staging or committing.
The user subsequently authorised the final local Phase 8 checkpoint; pushing remains unauthorised.


## Executed validation results (2026-10-08)

| Check | Result |
|---|---|
| Default pytest | 99 passed, 6 skipped; one existing Starlette/httpx deprecation warning |
| Power BI tests with native PostgreSQL | 5 passed |
| Power BI schema/binding checks | Passed: 76 documents, 62 visuals, 21 tables, 25 relationships, 39 measures; 62 schema compatibility checks explicitly reported |
| Ruff lint and formatting | Passed |
| Screenshot reproduction | Four PNGs readable; full decoded-pixel equality after lossless crop/re-encode |
| README command modules / CLI help | 10 modules resolved; 4 argument-parser help checks passed |
| Read-only interview commands | ETL summary, SO-0001 trace and inventory positions executed successfully |
| API contract references | All 18 README URL occurrences match actual API routes or docs endpoints |
| PowerShell syntax | All 17 README PowerShell blocks parsed successfully |
| Local documentation links | 35 relative links resolved across README and related guides |
| Database preservation | All 35 tables / 1,497 rows match Phase 7 baseline before and after demo commands |

The setup/install/migration/write workflows were verified by source inspection, not rerun.
API URLs were checked against generated OpenAPI; a live HTTP server was not launched this phase.
The screenshot script was executed twice; originals retained their provenance hashes.
The default test skips require PostgreSQL; the separate BI suite explicitly used native PostgreSQL.
No operational data, application code, DAX, Power Query or report definitions were changed.

Intended source-control scope is limited to README/guide improvements, the image assets and
provenance, the crop script and the raw-capture ignore rule. Candidate text was scanned for
credential patterns and local credential values without displaying secrets. The existing README
connection-string placeholder is documentation, not a credential. Raw captures, .env, PBIX,
.pbi caches, temporary files and local backups remain excluded from the checkpoint.


## Neutral portfolio wording review (2026-10-08)

The README and this report now describe an independent fictional manufacturing digital
transformation case study for a general professional portfolio. Named application framing
and audience-specific guidance were replaced with neutral technical and business language.
The proposed 20% efficiency objective remains explicitly fictional and unachieved.

Review covered tracked files and untracked source candidates across documentation, source,
configuration, scripts, reporting text and metadata, excluding version-control history, virtual
environments, caches and generated local files. Existing technical vendor names and synthetic
Rivaline entities retain their technical meaning. Documentation links and whitespace were checked;
README command blocks and image references were preserved. No calculation, database record,
Power BI definition or screenshot was changed. No staging, commit or push was performed.


## Final local checkpoint review

The final checkpoint contains only the portfolio README, updated Power BI guide, this validation
report, four curated PNGs, their provenance/instructions, the reproduction script and ignore rule.
The fictional proposed 20% target and all detailed setup/testing/demo instructions are retained.
Final lightweight checks cover screenshot reproduction and hashes, documentation links and
PowerShell syntax, repository-wide neutral wording, credential/local-file exclusion, Power BI
schema/bindings, Ruff and Git whitespace. The earlier executed full-suite results above remain
the regression evidence for this documentation-only checkpoint. No business data or report model
changes are included. Commit message: `docs: complete manufacturing platform portfolio and demo guide`.
No push is authorised.

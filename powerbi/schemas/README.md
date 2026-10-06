# Microsoft JSON schemas used for offline validation

Downloaded from the exact Microsoft developer schema URLs recorded in manifest.json.
The existing generated project declares report 3.3.0, page 2.1.0, PBIR definition 4.0,
PBISM definition 4.2 and compatibility level 1606. Those definitions are retained.

No visual existed in the original blank report. Its theme import metadata mentions visual
2.13.0, which is not itself a visualContainer schema guarantee. The corresponding attempted
visualContainer/2.13.0 URL returned 404. Microsoft's published repository lists 2.12.0 as the
latest visualContainer schema; new visuals use that documented version and its referenced
visualConfiguration 2.7.0. JSON Schema validation passes; Desktop compatibility and rendering
still require opening/refreshing the project, and are not claimed by this check.

Source: https://github.com/microsoft/json-schemas/tree/main/fabric/item/report/definition
The JSON files are pinned locally so default tests require no network. manifest.json maps
canonical URLs to local copies. No schema values or validation constraints were weakened.


## Desktop save round-trip (2026-10-06)

Desktop saved all 62 visual containers with a 2.13.0 declaration. The exact Microsoft schema
URL still returns HTTP 404. Those manually validated saved files are preserved. The validator
checks their structure against the pinned 2.12.0 schema using an in-memory declaration change,
reports them as `schema_compatibility_documents`, and does not claim exact 2.13 conformance.
All other documents use their declared pinned schemas. No schema constraints were modified.
The user confirmed successful post-fix Desktop open, refresh and rendering on all six pages.

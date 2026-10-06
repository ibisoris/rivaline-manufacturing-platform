"""Offline schema, binding, relationship and artifact validation; not a Desktop engine test."""

import json
import re
from pathlib import Path

from jsonschema import validators
from referencing import Registry, Resource

ROOT = Path("powerbi")


def validate(root: Path = ROOT) -> dict:
    schema_root = ROOT / "schemas"
    manifest = json.loads((schema_root / "manifest.json").read_text())
    documents = {
        url: json.loads((schema_root / name).read_text()) for url, name in manifest.items()
    }
    registry = Registry().with_resources(
        (url, Resource.from_contents(value)) for url, value in documents.items()
    )
    checked = 0
    compatibility_checked = 0
    for path in root.rglob("*"):
        if not path.is_file() or any(
            part in {".pbi", ".phase7-backup", "schemas"} for part in path.parts
        ):
            continue
        if path.suffix not in {".json", ".pbip", ".pbir", ".pbism"} and path.name != ".platform":
            continue
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        url = value.get("$schema") if isinstance(value, dict) else None
        if not url:
            continue
        # Desktop 2.158 saves 2.13, whose official URL currently returns 404.
        # Keep the saved report intact and explicitly report structural validation
        # against the pinned published 2.12 schema, not exact 2.13 conformance.
        if url.endswith("visualContainer/2.13.0/schema.json"):
            url = url.replace("/2.13.0/", "/2.12.0/")
            compatibility_checked += 1
            value = {**value, "$schema": url}  # In-memory compatibility check only.
        schema = documents[url]
        validator = validators.validator_for(schema)(schema, registry=registry)
        errors = sorted(validator.iter_errors(value), key=lambda e: str(e.path))
        assert not errors, f"{path}: {errors[0].message if errors else ''}"
        checked += 1
    spec = json.loads((root / "model-spec.json").read_text())
    fields = {t["name"]: {c["name"] for c in t["columns"]} for t in spec["tables"]}
    fields["Calendar"] = {"Date", "Month", "MonthIndex"}
    measures = {m["name"] for m in spec["measures"]}
    fields["Metrics"] = {"Anchor"}
    model = root / "RivalineOperations.SemanticModel/definition"
    for table, columns in fields.items():
        source = (model / "tables" / (table + ".tmdl")).read_text()
        for column in columns:
            assert re.search(
                r"^\tcolumn (?:'" + re.escape(column) + r"'|" + re.escape(column) + r")$",
                source,
                re.M,
            ), (table, column)
    metric_text = (model / "tables/Metrics.tmdl").read_text()
    for measure in spec["measures"]:
        assert re.search(
            r"^\tmeasure (?:'"
            + re.escape(measure["name"])
            + r"'|"
            + re.escape(measure["name"])
            + r") = "
            + re.escape(measure["expression"])
            + r"$",
            metric_text,
            re.M,
        ), measure["name"]
        for quoted, plain, column in re.findall(
            r"(?:'([^']+)'|([A-Za-z][A-Za-z ]*))\[([^]]+)\]", measure["expression"]
        ):
            table = (quoted or plain).strip()
            assert table in fields and column in fields[table], (measure["name"], table, column)
    # Relationship validation forbids fact-to-fact paths and duplicates.
    dimensions = {"Product", "Material", "Supplier", "Customer", "Resource", "Calendar"}
    keys = set()
    for r in spec["relationships"]:
        assert r["dimension"] in dimensions and r["fact"] not in dimensions
        assert r["column"] in fields[r["fact"]] and r["key"] in fields[r["dimension"]]
        key = (r["fact"], r["column"], r["dimension"])
        assert key not in keys
        keys.add(key)
    pages = json.loads((root / "RivalineOperations.Report/definition/pages/pages.json").read_text())
    assert len(pages["pageOrder"]) == 6
    names = set()
    visuals = 0
    for page in pages["pageOrder"]:
        folder = root / "RivalineOperations.Report/definition/pages" / page
        assert json.loads((folder / "page.json").read_text())["name"] == page
        for file in folder.glob("visuals/*/visual.json"):
            v = json.loads(file.read_text())
            name = v["name"]
            assert name not in names and file.parent.name == name
            names.add(name)
            visuals += 1
            position = v["position"]
            assert 0 <= position["x"] and position["x"] + position["width"] <= 1920
            assert 0 <= position["y"] and position["y"] + position["height"] <= 1080
            query_state = v["visual"].get("query", {}).get("queryState", {})
            native_refs = [
                projection["nativeQueryRef"]
                for role in query_state.values()
                for projection in role["projections"]
                if "nativeQueryRef" in projection
            ]
            assert len(native_refs) == len(set(native_refs)), (
                f"{file}: duplicate native reference names: {native_refs}"
            )
            for role in query_state.values():
                for projection in role["projections"]:
                    expression = projection["field"]
                    kind = next(iter(expression))
                    ref = expression[kind]
                    table = ref["Expression"]["SourceRef"]["Entity"]
                    column = ref["Property"]
                    assert column in (
                        measures if kind == "Measure" and table == "Metrics" else fields[table]
                    ), (table, column)
    page_spec = json.loads((root / "page-spec.json").read_text())
    expected_visuals = {v["name"] for p in page_spec["pages"] for v in p["visuals"]}
    assert names == expected_visuals, "Report contains missing or obsolete generated visuals"
    return dict(
        schema_documents=checked,
        schema_compatibility_documents=compatibility_checked,
        tables=len(fields),
        relationships=len(keys),
        measures=len(measures),
        pages=6,
        visuals=visuals,
        desktop_refresh_render="not validated",
        dax_engine="not executed",
    )


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))

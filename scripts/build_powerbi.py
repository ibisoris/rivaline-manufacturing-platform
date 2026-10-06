"""Deterministic generation within the inspected PBIP/PBIR/TMDL project format.

Does not connect to PostgreSQL, open Desktop, read credentials or change binary/local artifacts.
"""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path("powerbi")
REPORT = "RivalineOperations.Report"
MODEL = "RivalineOperations.SemanticModel"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def mquote(value: str) -> str:
    return json.dumps(value)


def table_text(table: dict) -> str:
    name = table["name"]
    lines = ["/// " + table["grain"], "table " + quote(name)]
    for column in table["columns"]:
        c, typ = column["name"], column["type"]
        lines += [
            "",
            "\tcolumn " + quote(c),
            "\t\tdataType: " + typ,
            "\t\tsummarizeBy: none",
            "\t\tsourceColumn: " + c,
        ]
        if typ == "double":
            lines += ["\t\tformatString: #,0.000000"]
        if typ == "dateTime":
            lines += ["\t\tformatString: yyyy-MM-dd"]
        if c == "id" or c.endswith("_id"):
            lines += ["\t\tisHidden"]
    cols = ", ".join(mquote(c["name"]) for c in table["columns"])
    query = [
        "let",
        '    Source = ReportingSource{[Schema="public", Item='
        + mquote(table["source"])
        + "]}[Data],",
    ]
    conditions = []
    for field, kind, value in table["filters"]:
        conditions.append("[" + field + "] = " + (value if kind == "parameter" else mquote(value)))
    query += [
        "    Filtered = "
        + (
            "Table.SelectRows(Source, each " + " and ".join(conditions) + ")"
            if conditions
            else "Source"
        )
        + ",",
        "    Selected = Table.SelectColumns(Filtered, {" + cols + "}),",
    ]
    previous = "Selected"
    if name == "Backtest":
        query += [
            '    Models = Table.Distinct(Table.SelectColumns(Forecast, {"product_id",'
            ' "selected_model"})),',
            '    Matched = Table.NestedJoin(Selected, {"product_id", "model_name"}, '
            'Models, {"product_id", "selected_model"}, "SelectedModel", '
            "JoinKind.Inner),",
            '    SelectedOnly = Table.RemoveColumns(Matched, {"SelectedModel"}),',
        ]
        previous = "SelectedOnly"
    types = {
        "int64": "Int64.Type",
        "double": "type number",
        "dateTime": "type datetime",
        "string": "type text",
    }
    pairs = ", ".join(
        "{" + mquote(c["name"]) + ", " + types[c["type"]] + "}" for c in table["columns"]
    )
    query += ["    Typed = Table.TransformColumnTypes(" + previous + ", {" + pairs + "}),"]
    if name in {"Forecast", "Demand History", "Production Plan", "Backtest"}:
        query += [
            "    Result = if Table.IsEmpty(Typed) then error "
            '"Selected reporting data is empty or incompatible" else Typed'
        ]
    elif name in {"Capacity", "Planning Materials"}:
        query += [
            '    Result = if Table.IsEmpty(#"Production Plan") then error '
            '"Select a matching plan and forecast" else Typed'
        ]
    else:
        query += ["    Result = Typed"]
    query += ["in", "    Result"]
    lines += ["", "\tpartition " + quote(name) + " = m", "\t\tmode: import", "\t\tsource ="]
    lines += ["\t\t\t" + line for line in query]
    return "\n".join(lines) + "\n"


def model_files(spec: dict, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    tables = target / "tables"
    tables.mkdir(exist_ok=True)
    for table in spec["tables"]:
        (tables / (table["name"] + ".tmdl")).write_text(table_text(table), encoding="utf-8")
    expressions = []
    for name, value in spec["parameters"].items():
        expressions += [
            "expression "
            + name
            + " = "
            + mquote(value)
            + ' meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
            "",
        ]
    expressions += [
        "expression ReportingSource = PostgreSQL.Database(Server, Database, "
        "[CreateNavigationProperties=false])",
        "",
    ]
    (target / "expressions.tmdl").write_text("\n".join(expressions), encoding="utf-8")
    calendar = (ROOT / "templates/Calendar.tmdl").read_text(encoding="utf-8")
    (tables / "Calendar.tmdl").write_text(calendar, encoding="utf-8")
    metrics = ["table Metrics"]
    for measure in spec["measures"]:
        metrics += [
            "",
            "\t/// " + measure["description"],
            "\tmeasure " + quote(measure["name"]) + " = " + measure["expression"],
        ]
        if measure["format"]:
            metrics += ["\t\tformatString: " + measure["format"]]
    metrics += [
        "",
        "\tcolumn Anchor",
        "\t\tdataType: int64",
        "\t\tisHidden",
        "\t\tsourceColumn: [Anchor]",
        "\tpartition Metrics = calculated",
        "\t\tmode: import",
        '\t\tsource = ROW("Anchor", 1)',
    ]
    (tables / "Metrics.tmdl").write_text("\n".join(metrics) + "\n", encoding="utf-8")
    relationships = []
    for r in spec["relationships"]:
        identifier = hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()[:32]
        relationships += [
            "relationship " + identifier,
            "\tfromColumn: " + quote(r["fact"]) + "." + quote(r["column"]),
            "\ttoColumn: " + quote(r["dimension"]) + "." + quote(r["key"]),
            "\tfromCardinality: many",
            "\ttoCardinality: one",
            "\tcrossFilteringBehavior: oneDirection",
            "",
        ]
    (target / "relationships.tmdl").write_text("\n".join(relationships), encoding="utf-8")
    header = (ROOT / "templates/model.tmdl").read_text(encoding="utf-8")
    header = header.replace(
        "__PBI_TimeIntelligenceEnabled = 1", "__PBI_TimeIntelligenceEnabled = 0"
    )
    header += (
        "\n"
        + "\n".join(
            "ref table " + quote(n)
            for n in [t["name"] for t in spec["tables"]] + ["Calendar", "Metrics"]
        )
        + "\n"
    )
    (target / "model.tmdl").write_text(header, encoding="utf-8")


def literal(value):
    val = (
        "true"
        if value is True
        else "false"
        if value is False
        else str(value)
        if isinstance(value, (int, float))
        else quote(value)
    )
    return {"expr": {"Literal": {"Value": val}}}


def field(table: str, name: str, measure: bool = False) -> dict:
    return {
        "field": {
            "Measure" if measure else "Column": {
                "Expression": {"SourceRef": {"Entity": table}},
                "Property": name,
            }
        },
        "queryRef": table + "." + name,
        "nativeQueryRef": name,
    }


def generate_pages(target: Path) -> list[dict]:
    pages = []

    def page(name, title, subtitle):
        p = dict(name=name, title=title, subtitle=subtitle, visuals=[])
        pages.append(p)
        return p

    def visual(p, kind, title, x, y, w, h, roles=None, text=None):
        name = hashlib.sha256((p["name"] + str(len(p["visuals"])) + title).encode()).hexdigest()[
            :20
        ]
        v = {
            "$schema": SCHEMA + "visualContainer/2.12.0/schema.json",
            "name": name,
            "position": dict(
                x=x, y=y, z=len(p["visuals"]), height=h, width=w, tabOrder=len(p["visuals"])
            ),
            "visual": {"visualType": kind, "drillFilterOtherVisuals": True},
        }
        config = v["visual"]
        config["visualContainerObjects"] = {
            "title": [
                {
                    "properties": {
                        "show": literal(bool(title)),
                        "text": literal(title),
                        "fontSize": literal(16),
                        "fontColor": {"solid": {"color": literal("#17324D")}},
                    }
                }
            ],
            "background": [
                {
                    "properties": {
                        "show": literal(True),
                        "color": {"solid": {"color": literal("#FFFFFF")}},
                        "transparency": literal(0),
                    }
                }
            ],
        }
        if roles:
            projections = [projection for values in roles.values() for projection in values]
            references = [projection["nativeQueryRef"] for projection in projections]
            for projection in projections:
                if references.count(projection["nativeQueryRef"]) > 1:
                    projection["nativeQueryRef"] = projection["queryRef"]
            config["query"] = {
                "queryState": {role: {"projections": values} for role, values in roles.items()}
            }
        if text is not None:
            config["objects"] = {
                "general": [
                    {
                        "properties": {
                            "paragraphs": [
                                {
                                    "textRuns": [
                                        {
                                            "value": text,
                                            "textStyle": {
                                                "fontFamily": "Segoe UI",
                                                "fontSize": "20px",
                                                "color": "#17324D",
                                            },
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                ]
            }
        if kind == "card":
            config["objects"] = {
                "labels": [{"properties": {"displayUnits": literal(1), "fontSize": literal(32)}}]
            }
        write_json(target / "pages" / p["name"] / "visuals" / name / "visual.json", v)
        p["visuals"].append(
            dict(
                name=name,
                type=kind,
                title=title,
                position=v["position"],
                roles=roles or {},
                text=text,
            )
        )

    def metric(p, title, index, measure):
        visual(
            p,
            "card",
            title,
            48 + index * 460,
            170,
            440,
            140,
            {"Values": [field("Metrics", measure, True)]},
        )

    def table(p, title, x, y, w, h, columns, measures=()):
        visual(
            p,
            "tableEx",
            title,
            x,
            y,
            w,
            h,
            {
                "Values": [field(t, c) for t, c in columns]
                + [field("Metrics", m, True) for m in measures]
            },
        )

    def chart(p, title, x, y, w, h, category, measures, kind="clusteredColumnChart"):
        visual(
            p,
            kind,
            title,
            x,
            y,
            w,
            h,
            {"Category": [field(*category)], "Y": [field("Metrics", m, True) for m in measures]},
        )

    def slicer(p, title, x, y, w, table, column):
        visual(p, "slicer", title, x, y, w, 100, {"Values": [field(table, column)]})

    p = page(
        "aae74f90d08cb53226af",
        "01  Executive Operations",
        "Synthetic management view | Current stock, selected forecast and proposed production",
    )
    for i, (title, m) in enumerate(
        [
            ("Orders | all-time", "Orders"),
            ("Materials at risk", "Materials At Risk"),
            ("Batch QC pass | all-time", "Batch QC Pass Rate %"),
            ("Forecast demand | kg", "Forecast Demand kg"),
        ]
    ):
        metric(p, title, i, m)
    chart(
        p,
        "Material position | kg",
        48,
        340,
        890,
        300,
        ("Material", "code"),
        ["Material On Hand kg", "Projected Material kg"],
    )
    chart(
        p,
        "Required vs available capacity | hours",
        962,
        340,
        890,
        300,
        ("Calendar", "Month"),
        ["Capacity Required Hours", "Capacity Available Hours"],
    )
    table(
        p,
        "Management exceptions | proposed plan",
        48,
        668,
        1350,
        270,
        [
            ("Production Plan", "product_id"),
            ("Production Plan", "period_start"),
            ("Production Plan", "status"),
        ],
        ["Constrained Production kg"],
    )
    visual(
        p,
        "textbox",
        "Read first",
        1420,
        668,
        432,
        270,
        text=(
            "December mixing needs 11.76 hours against 10 available. FG-002 has 844 "
            "kg unmet. These are synthetic proposed plans; no orders are released. "
            "Filters and future refreshes may change results."
        ),
    )
    p = page(
        "inventory_procurement",
        "02  Inventory & Procurement",
        "Pooled raw materials | Reorder proposals are not open purchase supply",
    )
    for i, (title, m) in enumerate(
        [
            ("On hand | kg", "Material On Hand kg"),
            ("Projected | kg", "Projected Material kg"),
            ("Materials at risk", "Materials At Risk"),
            ("Proposed reorder | kg", "Recommended Reorder kg"),
        ]
    ):
        metric(p, title, i, m)
    slicer(p, "Material", 48, 335, 420, "Material", "code")
    slicer(p, "Supplier | procurement only", 490, 335, 448, "Supplier", "code")
    chart(
        p,
        "Current stock and projected balance | kg",
        48,
        455,
        890,
        465,
        ("Material", "code"),
        ["Material On Hand kg", "Projected Material kg"],
    )
    table(
        p,
        "Reorder proposals | selected run",
        962,
        335,
        890,
        280,
        [("Material", "code"), ("Reorders", "status"), ("Reorders", "reason")],
        ["Recommended Reorder kg"],
    )
    table(
        p,
        "Supplier material flow | orders, not receipts",
        962,
        645,
        890,
        275,
        [("Supplier", "code"), ("Material", "code")],
        ["Procurement Ordered kg"],
    )
    p = page(
        "demand_forecasting",
        "03  Demand & Forecasting",
        "Archived actual demand and future forecasts are separate from operational sales",
    )
    for i, (title, m) in enumerate(
        [
            ("Forecast | kg", "Forecast Demand kg"),
            ("Selected-policy holdout MAE | kg", "Selected Policy MAE kg"),
            ("Selected-policy holdout RMSE | kg", "Selected Policy RMSE kg"),
            ("Selected model", "Selected Model"),
        ]
    ):
        metric(p, title, i, m)
    slicer(p, "Product", 48, 335, 420, "Product", "code")
    chart(
        p,
        "Archived demand and forward forecast | kg",
        48,
        455,
        1120,
        465,
        ("Calendar", "Month"),
        ["Archived Demand kg", "Forecast Demand kg"],
        "lineChart",
    )
    chart(
        p,
        "Holdout actual vs predicted | kg",
        1190,
        335,
        662,
        280,
        ("Calendar", "Month"),
        ["Holdout Actual kg", "Holdout Prediction kg"],
        "lineChart",
    )
    table(
        p,
        "October-December forecast | kg per product/month",
        1190,
        645,
        662,
        275,
        [("Product", "code"), ("Forecast", "period_start"), ("Forecast", "selected_model")],
        ["Forecast Demand kg"],
    )
    p = page(
        "production_capacity",
        "04  Production & Capacity",
        "Proposed plan | Whole batches compete for finite materials and residual hours. "
        "Separate verified what-if: FG-001 +5,000 kg -> 3,000 kg net; "
        "30h needed vs 10h available; 2,000 kg unmet.",
    )
    for i, (title, m) in enumerate(
        [
            ("Net production | kg", "Production Requirement kg"),
            ("Unmet production | kg", "Constrained Production kg"),
            ("December mixing required | h", "December Mixing Required Hours"),
            ("December mixing available | h", "December Mixing Available Hours"),
        ]
    ):
        metric(p, title, i, m)
    slicer(p, "Month", 48, 335, 400, "Calendar", "Month")
    slicer(p, "Resource", 470, 335, 468, "Resource", "code")
    chart(
        p,
        "Resource capacity | hours",
        48,
        455,
        890,
        220,
        ("Resource", "code"),
        ["Capacity Required Hours", "Capacity Available Hours"],
    )
    table(
        p,
        "Capacity detail | one resource/month",
        48,
        700,
        890,
        220,
        [("Resource", "code"), ("Calendar", "Month")],
        [
            "Capacity Required Hours",
            "Capacity Available Hours",
            "Capacity Utilisation %",
            "Capacity Shortfall Hours",
        ],
    )
    table(
        p,
        "Forecast to production | product/month",
        962,
        335,
        890,
        280,
        [("Product", "code"), ("Production Plan", "period_start"), ("Production Plan", "status")],
        ["Production Requirement kg", "Allocated Production kg", "Constrained Production kg"],
    )
    table(
        p,
        "All-resource material turns | kg, availability is not additive",
        962,
        645,
        890,
        275,
        [
            ("Planning Materials", "product_id"),
            ("Planning Materials", "period_start"),
            ("Material", "code"),
            ("Planning Materials", "available_quantity"),
            ("Planning Materials", "remaining_quantity"),
        ],
        ["Material Requirement kg", "Material Shortage kg"],
    )
    p = page(
        "quality_trust",
        "05  Quality & Data Trust",
        "Audited records | ETL replay counts execution events, not unique business records",
    )
    for i, (title, m) in enumerate(
        [
            ("Batch QC pass | all-time", "Batch QC Pass Rate %"),
            ("ETL acceptance", "ETL Acceptance Rate %"),
            ("ETL rejection", "ETL Rejection Rate %"),
            ("Data quality issues", "Data Quality Issues"),
        ]
    ):
        metric(p, title, i, m)
    chart(
        p,
        "QC results | inspection counts",
        48,
        340,
        890,
        280,
        ("Quality", "result"),
        ["QC Inspections"],
    )
    chart(
        p,
        "Issues by source | observations",
        962,
        340,
        890,
        280,
        ("Data Quality", "source_system"),
        ["Data Quality Issues"],
    )
    table(
        p,
        "Validation rules and lineage",
        48,
        650,
        1350,
        270,
        [
            ("Data Quality", "run_code"),
            ("Data Quality", "source_system"),
            ("Data Quality", "rule_code"),
            ("Data Quality", "severity"),
        ],
        ["Data Quality Issues"],
    )
    visual(
        p,
        "textbox",
        "Trust boundary",
        1420,
        650,
        432,
        270,
        text=(
            "Known synthetic fixture: 416 accepted and 48 rejected source rows per "
            "run. Two audited executions retain 96 issue observations. "
            "Customer-to-supplier traceability is available through the operational "
            "API. QC pass is not a production-release approval."
        ),
    )
    p = page(
        "transformation",
        "06  Transformation & Value",
        "From fragmented records to explainable management decisions | Fictional case study",
    )
    journey = [
        (
            "01  Fragmented sources",
            "SQLite sales, CSV stock and production, Excel purchasing and quality. "
            "Synthetic data with reproducible defects.",
        ),
        (
            "02  Trusted ingestion",
            "Python validation, explicit quarantine, source keys and ETL run lineage."
            " Reconciliation protects quantities.",
        ),
        (
            "03  Integrated operations",
            "PostgreSQL shared records and stable reporting views. FastAPI connects "
            "orders, batches, inspections and suppliers.",
        ),
        (
            "04  Explainable decisions",
            "Inventory rules, chronological forecast evaluation and finite-capacity "
            "production proposals. Reasons remain visible.",
        ),
        (
            "05  Management intelligence",
            "Compare demand with supply, inspect material risk, identify the December"
            " capacity bottleneck and review data trust.",
        ),
        (
            "06  Honest value proposition",
            "Improved visibility is demonstrated by connected evidence. No financial "
            "ROI, time saving or operational improvement is claimed without "
            "measurement.",
        ),
    ]
    for i, (title, body) in enumerate(journey):
        visual(p, "textbox", title, 48 + (i % 3) * 615, 175 + (i // 3) * 280, 585, 245, text=body)
    visual(
        p,
        "textbox",
        "Demonstration route",
        48,
        760,
        1800,
        165,
        text=(
            "Start with executive exceptions. Inspect RM-002 / RM-003 reorder "
            "proposals. Review selected-policy holdout MAE. Show December mixing: "
            "11.76 hours vs 10, with 844 kg FG-002 unmet. Finish with audited ETL and"
            " traceability. This is decision support, not autonomous execution."
        ),
    )
    for p in pages:
        visual(p, "textbox", "", 48, 25, 1800, 115, text=p["title"] + "\n" + p["subtitle"])
        visual(p, "pageNavigator", "", 48, 975, 1804, 58)
        page_data = {
            "$schema": SCHEMA + "page/2.1.0/schema.json",
            "name": p["name"],
            "displayName": p["title"],
            "displayOption": "FitToPage",
            "height": 1080,
            "width": 1920,
        }
        write_json(target / "pages" / p["name"] / "page.json", page_data)
    write_json(
        target / "pages/pages.json",
        {
            "$schema": SCHEMA + "pagesMetadata/1.1.0/schema.json",
            "pageOrder": [p["name"] for p in pages],
            "activePageName": pages[0]["name"],
        },
    )
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args()
    spec = json.loads((ROOT / "model-spec.json").read_text())
    model_files(spec, args.output / MODEL / "definition")
    pages = generate_pages(args.output / REPORT / "definition")
    write_json(args.output / "page-spec.json", {"pages": pages, "desktop_validation": "required"})
    print(
        f"Generated {len(spec['tables']) + 2} model tables, {len(spec['measures'])} measures, "
        f"{len(pages)} pages. Desktop refresh/render validation is still required."
    )


if __name__ == "__main__":
    main()

"""Read-only PostgreSQL reconciliation for the Power BI import contract, not DAX execution."""

import hashlib
import json
from decimal import Decimal as D
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database import models as m
from database.session import get_engine
from etl.load import scalar
from scripts.validate_powerbi import validate

ROOT = Path("powerbi")


def snapshot(session: Session) -> dict:
    rows = {
        name: [
            {k: scalar(v) for k, v in r.items()}
            for r in session.execute(select(table).order_by(table.c.id)).mappings()
        ]
        for name, table in m.Base.metadata.tables.items()
    }
    return dict(
        counts={k: len(v) for k, v in rows.items()},
        sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
    )


def import_rows(session: Session, parameters: dict | None = None) -> dict:
    spec = json.loads((ROOT / "model-spec.json").read_text())
    parameters = parameters or spec["parameters"]
    imported = {}
    for table in spec["tables"]:
        columns = ", ".join('"' + c["name"] + '"' for c in table["columns"])
        sql = "SELECT " + columns + ' FROM "' + table["source"] + '"'
        predicates = []
        binds = {}
        for index, (column, kind, value) in enumerate(table["filters"]):
            key = "v" + str(index)
            predicates.append('"' + column + '" = :' + key)
            binds[key] = parameters[value] if kind == "parameter" else value
        if predicates:
            sql += " WHERE " + " AND ".join(predicates)
        imported[table["name"]] = [
            dict(row) for row in session.execute(text(sql), binds).mappings()
        ]
    # Same unique product/selected-model inner join as the Power Query contract.
    chosen = {(row["product_id"], row["selected_model"]) for row in imported["Forecast"]}
    imported["Backtest"] = [
        row for row in imported["Backtest"] if (row["product_id"], row["model_name"]) in chosen
    ]
    for table in (
        "Forecast",
        "Production Plan",
        "Capacity",
        "Reorders",
        "Demand History",
        "Backtest",
    ):
        if not imported[table]:
            raise ValueError("Selected reporting input is empty: " + table)
    plans = {r["forecast_run_code"] for r in imported["Production Plan"]}
    assert plans == {parameters["ForecastRunCode"]}, "Plan/forecast vintage mismatch"
    for table, keys in {
        "Product": ("id",),
        "Material": ("id",),
        "Supplier": ("id",),
        "Customer": ("id",),
        "Resource": ("id",),
        "Inventory": ("item_id",),
        "Forecast": ("product_id", "period_start"),
        "Backtest": ("product_id", "period_start"),
        "Production Plan": ("product_id", "period_start"),
        "Capacity": ("resource_id", "period_start"),
        "Planning Materials": ("product_id", "period_start", "raw_material_id"),
    }.items():
        assert len(imported[table]) == len(
            {tuple(row[key] for key in keys) for row in imported[table]}
        ), table
    for relationship in spec["relationships"]:
        if relationship["dimension"] == "Calendar":
            continue
        ids = {r[relationship["key"]] for r in imported[relationship["dimension"]]}
        assert all(r[relationship["column"]] in ids for r in imported[relationship["fact"]]), (
            relationship
        )
    return imported


def decimal(value) -> D:
    return D(str(value))


def reconcile(rows: dict) -> dict:
    codes = {r["id"]: r["code"] for r in rows["Product"]}
    materials = {r["id"]: r["code"] for r in rows["Material"]}
    reorders = {
        materials[r["raw_material_id"]]: str(decimal(r["quantity"]).quantize(D(".000001")))
        for r in rows["Reorders"]
    }
    forecasts = {
        codes[pid]: [
            str(decimal(r["quantity"]).quantize(D(".000001")))
            for r in sorted(rows["Forecast"], key=lambda r: r["period_start"])
            if r["product_id"] == pid
        ]
        for pid in codes
    }
    errors = [
        decimal(r["predicted_quantity"]) - decimal(r["actual_quantity"]) for r in rows["Backtest"]
    ]
    mae = (sum(map(abs, errors), D(0)) / len(errors)).quantize(D(".000001"))
    rmse = (sum((e * e for e in errors), D(0)) / len(errors)).sqrt().quantize(D(".000001"))
    net = sum((decimal(r["net_requirement"]) for r in rows["Production Plan"]), D(0))
    december = [
        r
        for r in rows["Capacity"]
        if str(r["period_start"])[:10] == "2026-12-01" and r["resource_code"] == "SYN-MIX"
    ]
    assert len(december) == 1
    cap = december[0]
    constrained = sum(
        (
            decimal(r["unmet_quantity"])
            for r in rows["Production Plan"]
            if codes[r["product_id"]] == "SYN-FG-002" and r["status"] != "FEASIBLE"
        ),
        D(0),
    )
    assert reorders == {"SYN-RM-002": "1000.000000", "SYN-RM-003": "1500.000000"}
    assert forecasts == {
        f"SYN-FG-{i:03}": [value] * 3
        for i, value in enumerate(("777.333333", "948.000000", "466.000000", "653.666667"), 1)
    }
    assert mae == D("18.416667") and rmse == D("23.973944")
    assert net == D("1175.999999") and constrained == D(844)
    assert decimal(cap["required_hours"]) == D("11.76") and decimal(cap["available_hours"]) == D(10)
    return dict(
        reorders=reorders,
        forecasts=forecasts,
        selected_holdout_mae_kg=str(mae),
        selected_holdout_rmse_kg=str(rmse),
        holdout_observations=len(errors),
        net_production_kg=str(net),
        december_mixing_required_hours=str(cap["required_hours"]),
        december_mixing_available_hours=str(cap["available_hours"]),
        constrained_fg002_kg=str(constrained),
        december_mixing_utilisation_pct="117.60",
        operations=rows["Operations"],
        imported_row_counts={k: len(v) for k, v in rows.items()},
    )


def main() -> None:
    baseline = json.loads(Path("docs/evidence/phase7-before.json").read_text())
    with get_engine().connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        with Session(connection, autoflush=False) as session:
            before = snapshot(session)
            assert before == baseline
            rows = import_rows(session)
            results = reconcile(rows)
            after = snapshot(session)
            assert after == before
            revision = session.scalar(text("SELECT version_num FROM alembic_version"))
            assert revision == "0006_production"
    original = json.loads(Path("docs/evidence/phase7-powerbi-baseline.json").read_text())
    binary = ROOT / "RivalineOperations.pbix"
    assert (
        hashlib.sha256(binary.read_bytes()).hexdigest()
        == original["RivalineOperations.pbix"]["sha256"]
    )
    evidence = dict(
        before=before,
        after=after,
        revision=revision,
        postgresql_results=results,
        static_checks=validate(),
        original_pbix_unchanged=True,
        dax_engine="not executed",
        desktop_refresh_render="not executed by this verifier; see docs/29-phase-7-validation.md",
    )
    Path("docs/evidence/phase7-live.json").write_text(
        json.dumps(evidence, default=str, indent=2) + "\n"
    )
    print(
        json.dumps(
            dict(
                preserved_rows=sum(before["counts"].values()),
                sha256=before["sha256"],
                tables_imported=len(rows),
                selected_holdout_mae_kg=results["selected_holdout_mae_kg"],
                december_mixing_required_hours=results["december_mixing_required_hours"],
                desktop_validation="user confirmation recorded in docs/29-phase-7-validation.md",
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

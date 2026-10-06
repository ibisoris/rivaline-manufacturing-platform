"""Power BI artifact integrity plus separate native PostgreSQL reconciliation."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.session import get_engine
from scripts.validate_powerbi import validate
from scripts.verify_phase7 import import_rows, reconcile, snapshot


def test_powerbi_schemas_bindings_and_grains():
    result = validate()
    assert result["tables"] == 21 and result["relationships"] == 25
    assert result["pages"] == 6 and result["visuals"] == 62 and result["measures"] == 39
    assert result["desktop_refresh_render"] == "not validated"


def test_powerbi_generation_deterministic(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    for target in (first, second):
        subprocess.run(
            [sys.executable, "-m", "scripts.build_powerbi", "--output", str(target)], check=True
        )
    for file in first.rglob("*"):
        if file.is_file():
            relative = file.relative_to(first)
            assert file.read_bytes() == (second / relative).read_bytes(), str(relative)
    # Desktop reserializes TMDL, adds lineage tags and saves visual formatting.
    # Preserve that validated representation while checking generated business bindings.
    for file in first.rglob("visual.json"):
        saved = json.loads((Path("powerbi") / file.relative_to(first)).read_text())
        generated = json.loads(file.read_text())
        assert saved["name"] == generated["name"]
        assert saved["position"] == generated["position"]
        assert saved["visual"]["visualType"] == generated["visual"]["visualType"]
        for value in (saved, generated):
            for role in value["visual"].get("query", {}).get("queryState", {}).values():
                for projection in role["projections"]:
                    projection.pop("active", None)  # Desktop selection metadata.
        assert saved["visual"].get("query") == generated["visual"].get("query")
    for file in first.glob("RivalineOperations.SemanticModel/definition/tables/*.tmdl"):
        saved = (Path("powerbi") / file.relative_to(first)).read_text()
        generated = file.read_text()
        # Compare complete M source blocks with indentation normalized.
        if "\t\tsource =\n" in generated:
            source = generated.split("\t\tsource =\n", 1)[1]
            source_saved = saved.split("\t\tsource =\n", 1)[1]
            assert [line.strip() for line in source.splitlines() if line.strip()] == [
                line.strip()
                for line in source_saved.splitlines()
                if line.strip() and line.strip() != "annotation PBI_ResultType = Table"
            ], file.name


def test_reporting_vintages_and_capacity_measure_contract():
    spec = json.loads(Path("powerbi/model-spec.json").read_text())
    tables = {t["name"]: t for t in spec["tables"]}
    measures = {m["name"]: m["expression"] for m in spec["measures"]}
    assert tables["Forecast"]["filters"] == [["run_code", "parameter", "ForecastRunCode"]]
    assert ["forecast_run_code", "parameter", "ForecastRunCode"] in tables["Production Plan"][
        "filters"
    ]
    assert measures["Capacity Available Hours"] == "SUM(Capacity[available_hours])"
    assert (
        measures["Capacity Utilisation %"]
        == "DIVIDE([Capacity Required Hours], [Capacity Available Hours])"
    )
    assert "AVERAGEX(Backtest" in measures["Selected Policy MAE kg"]
    backtest = Path(
        "powerbi/RivalineOperations.SemanticModel/definition/tables/Backtest.tmdl"
    ).read_text()
    assert "Table.Distinct" in backtest and "JoinKind.Inner" in backtest
    assert 'evaluation_split] = "test"' in backtest
    for table in spec["tables"]:
        assert "password" not in table and "credentials" not in table


def test_powerbi_postgresql_reconciliation(request):
    if not request.config.getoption("--postgres"):
        pytest.skip("Use --postgres for read-only BI reconciliation of verified public data")
    with get_engine().connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        with Session(connection, autoflush=False) as session:
            before = snapshot(session)
            results = reconcile(import_rows(session))
            assert results["holdout_observations"] == 12
            assert results["selected_holdout_mae_kg"] == "18.416667"
            assert snapshot(session) == before
            with pytest.raises(ValueError, match="empty"):
                spec = json.loads(Path("powerbi/model-spec.json").read_text())
                spec["parameters"]["ForecastRunCode"] = "0" * 64
                import_rows(session, spec["parameters"])


def test_duplicate_native_reference_regression(tmp_path):
    report = Path("powerbi/RivalineOperations.Report/definition/pages")
    relative = Path("inventory_procurement/visuals/0607f9894098bb09f1b4/visual.json")
    visual = json.loads((report / relative).read_text())
    projections = [
        projection
        for role in visual["visual"]["query"]["queryState"].values()
        for projection in role["projections"]
    ]
    assert [p["nativeQueryRef"] for p in projections] == [
        "Supplier.code",
        "Material.code",
        "Procurement Ordered kg",
    ]
    assert [p["queryRef"] for p in projections[:2]] == ["Supplier.code", "Material.code"]
    # Reproduce the Desktop failure in an isolated copy; structural JSON schemas
    # alone permit it, but the query binding validator must reject it.
    shutil.copytree(
        "powerbi",
        tmp_path / "powerbi",
        ignore=shutil.ignore_patterns(".pbi", ".phase7-backup", "*.pbix"),
    )
    for projection in projections[:2]:
        projection["nativeQueryRef"] = "code"
    target = tmp_path / "powerbi/RivalineOperations.Report/definition/pages" / relative
    target.write_text(json.dumps(visual))
    with pytest.raises(AssertionError, match="duplicate native reference names"):
        validate(tmp_path / "powerbi")

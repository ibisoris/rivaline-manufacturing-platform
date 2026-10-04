"""Source contracts, audit, replay and traceability on SQLite and opt-in PostgreSQL."""

import json
import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from database import models as m
from database.seed import seed_master_data
from etl.contracts import SOURCES
from etl.extract import extract
from etl.fixtures import generate
from etl.pipeline import export_quarantine, run_pipeline
from etl.reconcile import business_snapshot, reconcile, trace
from etl.transform import Rejected, day, identifier, number


@pytest.fixture
def legacy(tmp_path):
    root = tmp_path / "legacy"
    generate(root)
    return root


def test_fixture_bytes_are_deterministic(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    a, b = generate(first), generate(second)
    assert a == b
    assert a["valid_rows"] == 416 and a["rejected_rows"] == 48
    for spec in SOURCES.values():
        assert (first / spec.filename).read_bytes() == (second / spec.filename).read_bytes()
    before = (first / "manifest.json").read_bytes()
    generate(first)
    assert before == (first / "manifest.json").read_bytes()


@pytest.mark.parametrize(
    "source,expected",
    [
        ("sales", 56),
        ("purchasing", 200),
        ("inventory", 40),
        ("production", 56),
        ("quality", 56),
        ("dispatch", 56),
    ],
)
def test_extractors(legacy, source, expected):
    rows = extract(legacy, source)
    assert len(rows) == expected
    assert tuple(rows[0]) == SOURCES[source].columns
    assert all(isinstance(value, str) for row in rows for value in row.values())


@pytest.mark.parametrize("value", ["RM-001", "rm001", "RM_001", " SYN-RM-001 "])
def test_identifier_standardisation(value):
    assert identifier(value) == "SYN-RM-001"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "abc", "1.0000001"])
def test_bad_quantities(value):
    with pytest.raises(Rejected, match="quantity"):
        number(value, "quantity")


def test_dates_are_strict():
    with pytest.raises(Rejected):
        day("2026-02-30", "order_date")
    with pytest.raises(Rejected):
        day("01/02/2026", "order_date")


def test_full_pipeline_audit_replay_reconcile_and_trace(session, legacy, tmp_path):
    seed_master_data(session)
    session.commit()
    quarantine = tmp_path / "quarantine"
    first = run_pipeline(session, legacy, quarantine)
    assert (first["extracted"], first["accepted"], first["rejected"]) == (464, 416, 48)
    assert first["inserted_targets"] == 944
    manifest = json.loads((legacy / "manifest.json").read_text())
    rejected = json.loads((quarantine / first["run"] / "rejected.json").read_text())
    assert {(r["source"], r["position"], r["rule"]) for r in rejected} == {
        (r["source"], r["position"], r["rule"]) for r in manifest["defects"]
    }
    assert all(r["detected_at"] and r["file"] and r["raw"] for r in rejected)
    run = session.scalar(select(m.EtlRun).where(m.EtlRun.code == first["run"]))
    assert run.status == "succeeded" and run.finished_at >= run.started_at
    assert session.scalar(select(func.count()).select_from(m.DataQualityIssue)) == 48
    summary = quarantine / first["run"] / "summary.json"
    check = reconcile(session, summary, legacy)
    assert check["ok"], check
    assert check["actual_totals_kg"] == check["expected_totals_kg"] == check["source_totals_kg"]
    before = business_snapshot(session)
    second = run_pipeline(session, legacy, quarantine)
    assert second["inserted_targets"] == 0
    assert second["accepted"] == 416 and second["rejected"] == 48
    assert business_snapshot(session) == before
    assert reconcile(session, quarantine / second["run"] / "summary.json")["ok"]
    lineage = trace(session)
    assert lineage["customer"] == "SYN-CUS-001"
    assert len(lineage["batches"]) == 1
    batch = lineage["batches"][0]
    assert batch["product"] == "SYN-FG-001" and batch["quality"] == ["pass"]
    assert len(batch["materials"]) == 4
    assert {r["supplier"] for r in batch["materials"]} == {
        "SYN-SUP-001",
        "SYN-SUP-002",
        "SYN-SUP-003",
    }
    stock = session.scalar(select(m.Inventory))
    assert stock.quantity == Decimal("500")
    stock.quantity += 1
    session.flush()
    assert not reconcile(session, summary)["ok"]
    session.rollback()
    assert export_quarantine(session, run, quarantine)


def test_corrected_reject_can_replay_but_accepted_edit_cannot(session, legacy, tmp_path):
    seed_master_data(session)
    session.commit()
    directory = tmp_path / "q"
    initial = run_pipeline(session, legacy, directory, ["sales"])
    assert initial["accepted"] == 48
    with sqlite3.connect(legacy / "legacy_sales.db") as connection:
        connection.execute("UPDATE records SET quantity='100' WHERE record_id='BAD-SALES-7'")
    corrected = run_pipeline(session, legacy, directory, ["sales"])
    assert corrected["accepted"] == 49 and corrected["rejected"] == 7
    assert corrected["inserted_targets"] == 2
    before = business_snapshot(session)
    with sqlite3.connect(legacy / "legacy_sales.db") as connection:
        connection.execute("UPDATE records SET quantity='999' WHERE record_id='SALE-0001'")
    conflict = run_pipeline(session, legacy, directory, ["sales"])
    assert conflict["inserted_targets"] == 0
    assert business_snapshot(session) == before
    rejected = json.loads((directory / conflict["run"] / "rejected.json").read_text())
    assert any(r["rule"] == "REPLAY_CONFLICT" for r in rejected)


def test_fatal_extraction_rolls_back_targets_and_audits_failure(
    session, legacy, tmp_path, monkeypatch
):
    from etl import pipeline

    seed_master_data(session)
    session.commit()
    before = business_snapshot(session)
    original = pipeline.extract

    def broken(root, source):
        if source == "purchasing":
            raise ValueError("Do not leak arbitrary exception text")
        return original(root, source)

    monkeypatch.setattr(pipeline, "extract", broken)
    with pytest.raises(RuntimeError, match="inspect audit"):
        run_pipeline(session, legacy, tmp_path / "q")
    assert business_snapshot(session) == before
    run = session.scalar(select(m.EtlRun))
    assert run.status == "failed" and run.rows_loaded == 0
    issue = session.scalar(select(m.DataQualityIssue))
    assert issue.rule_code == "PIPELINE_FAILURE" and "leak" not in issue.message


def test_quarantine_failure_is_visible_and_recoverable(session, legacy, tmp_path, monkeypatch):
    from etl import pipeline

    seed_master_data(session)
    session.commit()
    original = pipeline.write_json

    def broken(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(pipeline, "write_json", broken)
    with pytest.raises(RuntimeError, match="export failed"):
        run_pipeline(session, legacy, tmp_path / "q", ["sales"])
    run = session.scalar(select(m.EtlRun))
    assert run.status == "failed" and run.rows_loaded == 48
    assert session.scalar(select(func.count()).select_from(m.SalesOrder)) == 48
    monkeypatch.setattr(pipeline, "write_json", original)
    export = export_quarantine(session, run, tmp_path / "q")
    assert any(r["rule"] == "EXPORT_FAILURE" for r in export)
    repeated = run_pipeline(session, legacy, tmp_path / "q", ["sales"])
    assert repeated["inserted_targets"] == 0 and repeated["status"] == "succeeded"


def test_missing_file_still_creates_run(session, tmp_path):
    with pytest.raises(RuntimeError):
        run_pipeline(session, tmp_path / "missing", tmp_path / "q")
    assert session.scalar(select(m.EtlRun)).status == "failed"


def test_extractor_rejects_wrong_headers(legacy):
    (legacy / "inventory_export.csv").write_text("unexpected\nvalue\n", encoding="utf-8")
    with pytest.raises(ValueError, match="columns"):
        extract(legacy, "inventory")

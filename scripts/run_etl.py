import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import EtlRun
from database.session import get_engine
from etl.contracts import ORDER
from etl.pipeline import export_quarantine, run_pipeline
from etl.reconcile import business_snapshot, reconcile, trace


def main():
    parser = argparse.ArgumentParser(description="Synthetic legacy ETL and audit inspection")
    parser.add_argument(
        "action", choices=["run", "summary", "reconcile", "trace", "snapshot", "export"]
    )
    parser.add_argument("--source", choices=ORDER)
    parser.add_argument("--root", type=Path, default=Path("data/legacy"))
    parser.add_argument("--quarantine", type=Path, default=Path("data/quarantine"))
    parser.add_argument("--run")
    parser.add_argument("--order", default="SO-0001")
    args = parser.parse_args()
    with Session(get_engine()) as session:
        if args.action == "run":
            result = run_pipeline(
                session, args.root, args.quarantine, [args.source] if args.source else None
            )
            result = {k: v for k, v in result.items() if k != "receipts"}
        elif args.action == "trace":
            result = trace(session, args.order)
        elif args.action == "snapshot":
            result = business_snapshot(session)
        else:
            query = select(EtlRun)
            if args.run:
                query = query.where(EtlRun.code == args.run)
            run = session.scalar(query.order_by(EtlRun.id.desc()).limit(1))
            if run is None:
                parser.error("No matching run")
            path = args.quarantine / run.code / "summary.json"
            if args.action == "reconcile":
                result = reconcile(session, path, args.root)
            elif args.action == "export":
                result = {
                    "run": run.code,
                    "exported": len(export_quarantine(session, run, args.quarantine)),
                }
            else:
                result = {
                    "run": run.code,
                    "status": run.status,
                    "extracted": run.rows_read,
                    "accepted": run.rows_loaded,
                    "rejected": run.rows_rejected,
                    "sources": run.source_record_id.split(":", 1)[-1],
                }
        print(json.dumps(result, indent=2))
        if result.get("ok") is False:
            raise SystemExit(1)


if __name__ == "__main__":
    main()

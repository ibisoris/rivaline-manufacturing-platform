"""Explicit synthetic forecast workflow. HTTP consumers remain read-only."""

import argparse
import json
from datetime import UTC, date
from pathlib import Path

from sqlalchemy.orm import Session

from database.config import get_settings
from database.session import get_engine
from etl.demand_history import generate_history, ingest_history
from planning.forecasting import forecast_to_bom, generate_forecasts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("generate-history", "ingest-history", "forecast", "demo-bom")
    )
    parser.add_argument("--root", type=Path, default=get_settings().forecast_history_dir)
    parser.add_argument("--cutoff", type=date.fromisoformat, default=date(2026, 9, 30))
    parser.add_argument("--run-code")
    parser.add_argument("--product-id", type=int, default=1)
    args = parser.parse_args()
    if args.command == "generate-history":
        result = generate_history(args.root)
    else:
        with (
            get_engine()
            .connect()
            .execution_options(isolation_level="REPEATABLE READ") as connection
        ):
            with connection.begin(), Session(connection) as session:
                if args.command == "ingest-history":
                    result = {"inserted_observations": ingest_history(session, args.root)}
                elif args.command == "forecast":
                    run, created = generate_forecasts(session, args.cutoff)
                    result = dict(
                        run_code=run.code,
                        created=created,
                        training_cutoff=str(run.training_cutoff),
                        generated_at=run.generated_at.astimezone(UTC).isoformat(),
                        **run.report,
                    )
                else:
                    if not args.run_code:
                        parser.error("--run-code is required for demo-bom")
                    result = forecast_to_bom(session, args.run_code, args.product_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

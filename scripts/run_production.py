"""Explicit CLI for synthetic policy seed, computational plans and BI snapshots."""

import argparse
import json
from datetime import UTC

from sqlalchemy.orm import Session

from database.session import get_engine
from planning.production import calculate, save_forecast_plan, seed_production_policies
from planning.production_contracts import WhatIf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("seed-policies", "forecast", "save-forecast", "what-if")
    )
    parser.add_argument("--forecast-run-code")
    parser.add_argument("--product-id", type=int, default=1)
    parser.add_argument("--period", default="2026-11-01")
    parser.add_argument("--quantity", default="5000")
    parser.add_argument("--unit", default="kg")
    args = parser.parse_args()
    if args.command in ("forecast", "save-forecast") and not args.forecast_run_code:
        parser.error("--forecast-run-code is required")
    with get_engine().connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(connection) as session, session.begin():
            if args.command == "seed-policies":
                output = {"inserted": seed_production_policies(session)}
            elif args.command == "save-forecast":
                run, created = save_forecast_plan(session, args.forecast_run_code)
                output = dict(
                    plan_run_code=run.code,
                    created=created,
                    generated_at=run.generated_at.astimezone(UTC).isoformat(),
                    report=run.report,
                )
            else:
                request = (
                    WhatIf(
                        demands=[
                            dict(
                                product_id=args.product_id,
                                period_start=args.period,
                                quantity=args.quantity,
                                unit_of_measure=args.unit,
                            )
                        ]
                    )
                    if args.command == "what-if"
                    else None
                )
                output = calculate(
                    session,
                    request=request,
                    forecast_run_code=args.forecast_run_code if request is None else None,
                )[0].model_dump(mode="json")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()

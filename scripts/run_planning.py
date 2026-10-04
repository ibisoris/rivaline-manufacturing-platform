"""Explicit local policy setup and atomic recommendation generation; no purchasing writes."""

import argparse
import json
from datetime import UTC

from sqlalchemy.orm import Session

from database.session import get_engine
from planning.inventory import generate, positions, requirements
from planning.policies import seed_policies


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("seed-policies", "calculate", "positions", "requirements")
    )
    args = parser.parse_args()
    with get_engine().connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin(), Session(connection) as session:
            if args.command == "seed-policies":
                result = {"inserted_policies": seed_policies(session)}
            elif args.command == "calculate":
                run, created = generate(session)
                result = {
                    "run_code": run.code,
                    "created": created,
                    "generated_at": run.generated_at.astimezone(UTC).isoformat(),
                }
            else:
                values = (
                    positions(session) if args.command == "positions" else requirements(session)
                )
                result = [value.model_dump(mode="json") for value in values]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

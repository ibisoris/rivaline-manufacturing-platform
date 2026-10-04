from sqlalchemy.orm import Session

from database.seed import seed_master_data
from database.session import get_engine


def main() -> None:
    with Session(get_engine()) as session, session.begin():
        counts = seed_master_data(session)
    print(f"Synthetic master rows inserted: {sum(counts.values())}; by table: {counts}")


if __name__ == "__main__":
    main()

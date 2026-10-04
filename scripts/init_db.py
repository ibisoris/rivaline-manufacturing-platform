from database.models import Base
from database.session import get_engine


def main() -> None:
    Base.metadata.create_all(get_engine())
    print("Phase 1 tables created (existing tables are not migrated).")


if __name__ == "__main__":
    main()

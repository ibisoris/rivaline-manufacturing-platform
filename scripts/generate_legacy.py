import argparse
import json
from pathlib import Path

from etl.fixtures import generate


def main():
    parser = argparse.ArgumentParser(description="Regenerate only owned synthetic fixture files")
    parser.add_argument("--output", type=Path, default=Path("data/legacy"))
    args = parser.parse_args()
    manifest = generate(args.output)
    print(json.dumps({k: v for k, v in manifest.items() if k != "defects"}, indent=2))


if __name__ == "__main__":
    main()

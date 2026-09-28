"""Inject local credentials into QueryFlux configuration without printing them."""

import argparse
import json
import os
from pathlib import Path


def generate(template: Path, output: Path, *, compose: bool, api_key: str):
    if not api_key:
        raise SystemExit("API_KEY is required; run make setup")
    text = template.read_text()
    if compose:
        text = text.replace("http://localhost:18080", "http://queryflux:18080")
        text = text.replace("http://localhost:8123", "http://clickhouse:8123")
    else:
        data = Path(os.getenv("DUCKDB_DATA_DIR", "artifacts/duckdb")).resolve()
        text = text.replace("/data/recent.duckdb", str(data / "recent.duckdb"))
    text += (
        "\nauth:\n  provider: static\n  required: true\n  staticUsers:\n"
        "    users:\n      valeosense:\n        password: " + json.dumps(api_key) + "\n"
    )
    output.parent.mkdir(exist_ok=True, parents=True)
    output.touch(mode=0o600, exist_ok=True)
    output.write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose", action="store_true")
    parser.add_argument("--template", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not os.getenv("API_KEY"):
        # Host setup uses the project's dotenv dependency; the image receives env directly.
        from dotenv import load_dotenv

        load_dotenv()
    output = args.output or Path(
        "artifacts/queryflux.compose.yaml" if args.compose else "artifacts/queryflux.local.yaml"
    )
    template = args.template or Path(
        "infra/queryflux.yaml" if args.compose else "infra/queryflux-native.yaml"
    )
    generate(template, output, compose=args.compose, api_key=os.getenv("API_KEY", ""))


if __name__ == "__main__":
    main()

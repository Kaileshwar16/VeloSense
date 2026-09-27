"""Inject a generated local secret without committing or printing it."""

import argparse
import json
from pathlib import Path

from shared.config import Settings

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if not settings.api_key:
        raise SystemExit("API_KEY is required; run make setup")
    text = Path("infra/queryflux.yaml").read_text()
    if args.compose:
        text = text.replace("http://localhost:18080", "http://queryflux:18080")
        text = text.replace("http://localhost:8123", "http://clickhouse:8123")
    text += (
        "\nauth:\n  provider: static\n  required: true\n  staticUsers:\n"
        "    users:\n      valeosense:\n        password: " + json.dumps(settings.api_key) + "\n"
    )
    path = Path(
        "artifacts/queryflux.compose.yaml" if args.compose else "artifacts/queryflux.local.yaml"
    )
    path.parent.mkdir(exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.write_text(text)

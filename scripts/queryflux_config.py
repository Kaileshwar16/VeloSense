"""Inject a generated local secret without committing or printing it."""

import json
from pathlib import Path

from shared.config import Settings

if __name__ == "__main__":
    settings = Settings()
    if not settings.api_key:
        raise SystemExit("API_KEY is required; run make setup")
    text = Path("infra/queryflux.yaml").read_text()
    text += (
        "\nauth:\n  provider: static\n  required: true\n  staticUsers:\n"
        "    users:\n      valeosense:\n        password: "
        + json.dumps(settings.api_key)
        + "\n"
    )
    path = Path("artifacts/queryflux.local.yaml")
    path.parent.mkdir(exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.write_text(text)

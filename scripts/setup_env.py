"""Create local credentials once; never print them or replace an existing .env."""

import secrets
from pathlib import Path

path = Path(".env")
if not path.exists():
    password = secrets.token_urlsafe(24)
    value = Path(".env.example").read_text().replace("replace-with-random-local-password", password)
    value = value.replace("replace-with-random-local-api-key", secrets.token_urlsafe(32))
    path.touch(mode=0o600)
    path.write_text(value)
    print("Created .env with random local credentials (not displayed).")
else:
    print("Preserved existing .env.")

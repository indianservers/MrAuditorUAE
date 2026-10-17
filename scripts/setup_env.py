"""Create a fresh local .env without printing credentials. Never overwrites a file."""

import base64
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
values = {
    "replace-with-generated-connector-key": base64.urlsafe_b64encode(
        secrets.token_bytes(32)
    ).decode(),
    "replace-with-generated-signing-secret-at-least-48-characters": secrets.token_urlsafe(48),
    "replace-with-generated-one-time-setup-secret": secrets.token_urlsafe(48),
    "replace-with-generated-database-password": secrets.token_urlsafe(32),
    "replace-with-independent-admin-password": secrets.token_urlsafe(32),
}
content = (root / ".env.example").read_text()
for old, new in values.items():
    content = content.replace(old, new)
with (root / ".env").open("x", encoding="utf-8") as stream:
    stream.write(content)
print("Created .env with independent random secrets. Protect this file.")

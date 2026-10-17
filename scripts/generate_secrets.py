"""Print proposed local environment secrets; redirect securely into .env if desired."""

import secrets

for key in ["JWT_SECRET", "BOOTSTRAP_SECRET", "POSTGRES_PASSWORD", "POSTGRES_ADMIN_PASSWORD"]:
    print(f"{key}={secrets.token_urlsafe(48)}")

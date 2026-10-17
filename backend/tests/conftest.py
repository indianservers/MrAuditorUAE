import os

os.environ.setdefault("JWT_SECRET", "test-only-signing-key-at-least-48-characters-long")
os.environ.setdefault("BOOTSTRAP_SECRET", "test-bootstrap-secret")

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://auditos@localhost:5432/auditos")

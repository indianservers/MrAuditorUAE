"""Read-only UTF-8 preflight for application sources; never rewrites content."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = (
    "backend/app",
    "backend/tests",
    "frontend/src",
    "frontend/tests",
    "frontend/e2e",
    "scripts",
)
EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".mjs", ".css", ".json"}


def ensure_utf8():
    failures = []
    for folder in FOLDERS:
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.suffix in EXTENSIONS:
                try:
                    path.read_bytes().decode("utf-8")
                except UnicodeDecodeError as exc:
                    failures.append(
                        f"{path.relative_to(ROOT)}: invalid UTF-8 at byte {exc.start}"
                    )
    if failures:
        raise ValueError("Source encoding preflight failed:\n" + "\n".join(failures))


if __name__ == "__main__":
    ensure_utf8()
    print("Application source UTF-8 preflight passed")

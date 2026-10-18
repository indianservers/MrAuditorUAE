import json
import logging
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Allowlist fields: never serialize bodies, headers, credentials or exception text.
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "event": getattr(record, "event", "application"),
                "request_id": getattr(record, "request_id", None),
                "status": getattr(record, "status", None),
                "duration_ms": getattr(record, "duration_ms", None),
                "method": getattr(record, "method", None),
                "route": getattr(record, "route", None),
                "release": getattr(record, "release", None),
            }
        )


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.getLogger("auditos").handlers = [handler]
    logging.getLogger("auditos").setLevel(logging.INFO)

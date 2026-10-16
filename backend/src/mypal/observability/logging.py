"""Structured logging using only the standard library.

Each log line is one JSON object (or readable text in local development) that always carries the
current request ID. Extra fields passed via `logger.info(..., extra={...})` are included as keys.
"""

import json
import logging
from datetime import UTC, datetime

from mypal.config import Settings
from mypal.observability.request_id import get_request_id

# Attributes every LogRecord has; anything else on a record came from `extra=` and is logged.
# uvicorn adds "color_message" (the same text with terminal colour codes), which is noise in JSON.
_STANDARD_RECORD_ATTRS = set(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "color_message",
}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_RECORD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Route all logs (ours and uvicorn's) through one root handler. Safe to call repeatedly."""
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    # RequestIdMiddleware already logs every request with its ID and timing.
    logging.getLogger("uvicorn.access").disabled = True

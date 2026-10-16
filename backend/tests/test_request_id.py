import json
import logging

from fastapi.testclient import TestClient

from mypal.observability.logging import JsonFormatter, RequestIdFilter


def test_well_formed_incoming_request_id_is_reused(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "gateway-abc-12345"})

    assert response.headers["X-Request-ID"] == "gateway-abc-12345"


def test_malformed_incoming_request_id_is_replaced(client: TestClient) -> None:
    # Spaces and quotes are outside the allowed character set (an attempt to forge log fields).
    forged = 'abc {"level":"CRITICAL"}'
    response = client.get("/api/health", headers={"X-Request-ID": forged})

    assert response.headers["X-Request-ID"] != forged
    assert len(response.headers["X-Request-ID"]) == 32


def test_json_log_line_includes_extra_fields() -> None:
    record = logging.makeLogRecord(
        {"name": "mypal.test", "levelno": logging.INFO, "levelname": "INFO", "msg": "hello"}
    )
    record.path = "/api/health"
    RequestIdFilter().filter(record)

    line = json.loads(JsonFormatter().format(record))

    assert line["message"] == "hello"
    assert line["path"] == "/api/health"
    assert "request_id" in line

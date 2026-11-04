"""A development users file replaces the built-in users; /api/info shows the data notice."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mypal.auth.dev import load_dev_users
from mypal.config import Settings
from mypal.main import create_app

USERS = [
    {"subject": "dev-acme-employee", "company_code": "ACME", "category_code": "STAFF"},
    {"subject": "dev-acme-hr", "company_code": "ACME", "roles": ["hr_admin"]},
]


def _write(tmp_path: Path, users: object) -> Path:
    path = tmp_path / "dev-users.json"
    path.write_text(json.dumps(users), encoding="utf-8")
    return path


@pytest.fixture
def file_client(settings: Settings, tmp_path: Path) -> TestClient:
    path = _write(tmp_path, USERS)
    return TestClient(create_app(settings.model_copy(update={"dev_users_file": path})))


def test_loads_users_with_their_scope_and_roles(tmp_path: Path) -> None:
    users = load_dev_users(_write(tmp_path, USERS))

    assert users["dev-acme-employee"].company_code == "ACME"
    assert users["dev-acme-employee"].location_code is None
    assert users["dev-acme-employee"].category_code == "STAFF"
    assert users["dev-acme-hr"].roles == frozenset({"hr_admin"})


@pytest.mark.parametrize(
    "users",
    [
        [],
        [{"subject": "alice", "company_code": "ACME"}],  # not marked as a development user
        [{"subject": "dev-x", "company_code": "acme"}],  # scope codes are upper case
        [{"subject": "dev-x", "company_code": "ACME", "roles": ["superuser"]}],
        [{"subject": "dev-x", "company_code": "ACME", "password": "x"}],  # unknown field
        [{"subject": "dev-x", "company_code": "ACME"}, {"subject": "dev-x", "company_code": "B"}],
    ],
)
def test_invalid_files_are_refused(tmp_path: Path, users: object) -> None:
    with pytest.raises(ValueError, match="users file"):
        load_dev_users(_write(tmp_path, users))


def test_unreadable_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "dev-users.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="users file"):
        load_dev_users(path)


def test_file_users_replace_the_built_in_ones(file_client: TestClient) -> None:
    subjects = [u["subject"] for u in file_client.get("/api/dev/users").json()]

    assert subjects == ["dev-acme-employee", "dev-acme-hr"]


def test_login_uses_the_file_users_attributes(file_client: TestClient) -> None:
    body = file_client.get("/api/me", headers={"X-Dev-User": "dev-acme-employee"}).json()

    assert body["company_code"] == "ACME"
    assert body["category_code"] == "STAFF"


def test_built_in_users_cannot_log_in_while_a_file_is_used(file_client: TestClient) -> None:
    response = file_client.get("/api/me", headers={"X-Dev-User": "dev-employee-north"})

    assert response.status_code == 401


def test_info_shows_the_default_data_notice(client: TestClient) -> None:
    assert client.get("/api/info").json() == {
        "app": "My Pal",
        "data_notice": "fictional sample policies",
    }


def test_info_shows_a_configured_data_notice(settings: Settings) -> None:
    client = TestClient(
        create_app(settings.model_copy(update={"data_notice": "the ACME policies"}))
    )

    assert client.get("/api/info").json()["data_notice"] == "the ACME policies"

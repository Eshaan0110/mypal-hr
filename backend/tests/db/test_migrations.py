from alembic import command
from sqlalchemy import Engine, inspect

from tests.conftest import alembic_config

EXPECTED_TABLES = {
    "alembic_version",
    "audit_events",
    "chunks",
    "companies",
    "employee_categories",
    "faq_sources",
    "faqs",
    "feedback",
    "hr_contacts",
    "locations",
    "policies",
    "policy_version_scopes",
    "policy_versions",
    "query_metrics",
}


def test_models_and_migrations_agree(db_engine: Engine, db_url: str) -> None:
    # Fails if someone changes a model without generating a migration (or vice versa).
    command.check(alembic_config(db_url))


def test_downgrade_removes_schema_and_upgrade_restores_it(db_engine: Engine, db_url: str) -> None:
    config = alembic_config(db_url)

    command.downgrade(config, "base")
    assert set(inspect(db_engine).get_table_names()) <= {"alembic_version"}

    command.upgrade(config, "head")
    assert set(inspect(db_engine).get_table_names()) == EXPECTED_TABLES

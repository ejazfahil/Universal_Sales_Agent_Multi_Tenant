"""Integration fixtures. These require a live PostgreSQL with pgvector.

Skipped when no database is reachable so the unit suite still runs on a laptop;
CI provides a pgvector service container, so the isolation acceptance criterion
is genuinely executed on every push rather than quietly skipped everywhere.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/usa_test",
)


def _database_reachable(url: str) -> bool:
    try:
        engine = sa.create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        engine.dispose()
    except Exception:  # noqa: BLE001 — any failure means "not reachable"
        return False
    return True


requires_db = pytest.mark.skipif(
    not _database_reachable(DB_URL),
    reason=f"no PostgreSQL reachable at {DB_URL}",
)


APP_ROLE = "usa_app"


def scope_to_tenant(conn: sa.Connection, tenant_id: uuid.UUID | None) -> None:
    """Drop to the non-superuser app role and set the tenant GUC.

    The SET LOCAL ROLE is not optional. Tests connect as ``postgres``, a
    superuser, and superusers bypass RLS unconditionally — FORCE does not apply
    to them. Without this the policies are never exercised and every isolation
    test passes for the wrong reason.
    """
    conn.execute(sa.text(f"SET LOCAL ROLE {APP_ROLE}"))
    conn.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id) if tenant_id is not None else None},
    )


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = sa.create_engine(DB_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def migrated(engine: Engine) -> Iterator[Engine]:
    """Run migrations to head once for the session."""
    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", DB_URL)
    command.upgrade(cfg, "head")
    yield engine


@pytest.fixture
def two_tenants(migrated: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """Create tenant A and tenant B, each with one customer. Clean up after."""
    a, b = uuid.uuid4(), uuid.uuid4()
    with migrated.begin() as conn:
        for tid, name in ((a, "Tenant A"), (b, "Tenant B")):
            conn.execute(
                sa.text("INSERT INTO tenants (id, name) VALUES (:id, :name)"),
                {"id": tid, "name": name},
            )
            # RLS is active on customers, so scope before inserting.
            scope_to_tenant(conn, tid)
            conn.execute(
                sa.text(
                    "INSERT INTO customers (id, tenant_id, name, email) "
                    "VALUES (:id, :tid, :name, :email)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tid,
                    "name": f"Customer of {name}",
                    "email": f"{name.replace(' ', '').lower()}@example.test",
                },
            )
    yield a, b
    with migrated.begin() as conn:
        # Cleanup runs as superuser: tenants has no RLS policy, and cascades
        # must reach rows the app role can no longer see.
        #
        # audit_logs is append-only (migration 0004) and references tenants with
        # ON DELETE RESTRICT, so the trigger has to be suspended to reclaim test
        # data. session_replication_role is superuser-only and transaction-local.
        # This is a test-teardown escape hatch and must never appear in app code.
        conn.execute(sa.text("SET LOCAL session_replication_role = replica"))
        conn.execute(sa.text("DELETE FROM audit_logs WHERE tenant_id = ANY(:ids)"), {"ids": [a, b]})
        conn.execute(sa.text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": [a, b]})

"""Row-level security: invariant I2.

Tenant isolation is enforced by Postgres, not by application ``WHERE`` clauses.
Each tenant-scoped table gets a policy comparing ``tenant_id`` against the
``app.tenant_id`` GUC that :func:`app.db.base.tenant_session` sets per
transaction.

Two details that are easy to get wrong and fatal if missed:

* ``FORCE ROW LEVEL SECURITY`` — without it the *table owner* bypasses every
  policy. Since migrations usually run as the owner, a test that passes as a
  plain user can still leak in production. FORCE closes that.
* ``NULLIF(current_setting('app.tenant_id', true), '')::uuid`` — the ``true``
  makes a *missing* GUC return NULL rather than raise, and the NULLIF handles
  the case where it was explicitly set to the empty string. Without NULLIF,
  ``''::uuid`` raises ``invalid input syntax for type uuid``, which is an error
  someone may be tempted to except-and-continue past. With it, the comparison
  is NULL, the row is filtered, and a request that forgot to set the tenant
  sees **nothing**. Fail closed, quietly.

Superusers still bypass RLS by design. The application must never connect as
one; see ``docs/02-eu-platform-plan.md``.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SCOPED_TABLES: tuple[str, ...] = (
    "users",
    "customers",
    "orders",
    "conversations",
    "messages",
    "agent_runs",
    "approvals",
    "actions",
    "audit_logs",
)

POLICY = "tenant_isolation"


def upgrade() -> None:
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {POLICY} ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            """
        )


def downgrade() -> None:
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

"""Make ``audit_logs`` genuinely append-only. Invariant I4, Article 12.

Two layers, because they fail differently:

* **Grants** — ``usa_app`` loses UPDATE and DELETE. Cheap, and it stops the
  application from ever issuing one by accident.
* **Trigger** — raises on UPDATE or DELETE *whoever* attempts it, superuser
  included. Grants do not constrain a superuser; a trigger does. This is the
  layer that makes the log survive an operator with production credentials.

An EU AI Act Article 12 record that can be edited is not a record. The
distinction only means anything if the database refuses.

Deleting a tenant would cascade into audit rows and hit the trigger, so the FK
is switched to ON DELETE RESTRICT: audit history outlives the tenant row by
design. GDPR erasure redacts the ``output`` column rather than removing rows —
the retention obligation and the erasure right are reconciled by
pseudonymisation, not deletion. See ``docs/reference/eu-ai-act-obligations.md``.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "usa_app"


def upgrade() -> None:
    op.execute(f"REVOKE UPDATE, DELETE ON audit_logs FROM {APP_ROLE}")

    op.execute("""
        CREATE OR REPLACE FUNCTION audit_logs_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_logs is append-only (EU AI Act Art. 12): % denied on row %',
                TG_OP, COALESCE(OLD.id::text, '?')
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only();
    """)

    # Audit history outlives the tenant. Without this, DROP-ing a tenant would
    # cascade into the trigger and fail confusingly.
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT audit_logs_tenant_id_fkey")
    op.execute(
        "ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_tenant_id_fkey "
        "FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT audit_logs_tenant_id_fkey")
    op.execute(
        "ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_tenant_id_fkey "
        "FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_append_only()")
    op.execute(f"GRANT UPDATE, DELETE ON audit_logs TO {APP_ROLE}")

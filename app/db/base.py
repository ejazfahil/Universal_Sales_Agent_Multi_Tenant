"""Declarative base, engine and the tenant-scoped session.

Tenant isolation (invariant I2) is enforced by Postgres row-level security, not
by application ``WHERE`` clauses. RLS policies read ``app.tenant_id`` from the
session, so every request must set that GUC before touching tenant data —
:func:`tenant_session` is the only sanctioned way to do it.

A forgotten ``WHERE tenant_id`` is then a non-event: the database returns
nothing. That is the whole point of putting the boundary here.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import DateTime, String, create_engine, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base with project-wide type mappings."""

    type_annotation_map = {  # noqa: RUF012
        str: String,
        datetime: DateTime(timezone=True),
        uuid.UUID: PG_UUID(as_uuid=True),
    }


_engine: Engine | None = None


def get_engine() -> Engine:
    """Process-wide engine, created lazily so settings can be patched in tests."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine. Tests use this after changing the database URL."""
    global _engine  # noqa: PLW0603
    if _engine is not None:
        _engine.dispose()
    _engine = None


@contextmanager
def tenant_session(tenant_id: uuid.UUID | str) -> Iterator[Session]:
    """Yield a Session with ``app.tenant_id`` set for the life of the transaction.

    ``set_config(..., true)`` scopes the GUC to the transaction, so it cannot
    leak to the next checkout of a pooled connection — a leaked tenant id would
    be a cross-tenant read.
    """
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    session = factory()
    try:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

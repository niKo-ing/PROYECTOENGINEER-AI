"""RLS de las tablas del agente. Con Postgres real: ``TEST_POSTGRES_URL=postgresql://... pytest tests/agent/test_rls.py``."""

import os

import pytest
from sqlalchemy import create_engine, text

from app import models  # noqa: F401
from app.agent.security import AGENT_TABLES, enable_agent_rls
from app.db import Base


def test_it_is_a_noop_on_sqlite():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    assert enable_agent_rls(engine) is False


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="requiere TEST_POSTGRES_URL")
def test_agent_tables_get_rls_and_other_tables_are_left_alone():
    url = os.environ["TEST_POSTGRES_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    assert enable_agent_rls(engine) is True
    assert enable_agent_rls(engine) is True  # idempotente
    with engine.connect() as c:
        flags = dict(c.execute(text("select relname, relrowsecurity from pg_class where relnamespace = 'public'::regnamespace and relkind = 'r'")).all())
    assert all(flags[t] for t in AGENT_TABLES)
    assert not flags["products"] and not flags["user_profiles"]
    Base.metadata.drop_all(engine)

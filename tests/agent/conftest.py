"""Fixtures del agente: base SQLite en memoria con un catálogo chico pero realista."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from catalogo import seed_catalog
from app.db import Base


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture()
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture()
def catalog(db):
    """Catálogo de prueba (ver ``catalogo.py``): cada producto fija un escenario."""
    return seed_catalog(db)

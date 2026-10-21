from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import create_app
from app.models import Base, Activity


# AC-01 / AC-11: no test may read the real keychain or call a real model.
@pytest.fixture(autouse=True)
def no_keychain_no_network(monkeypatch):
    from app.coach import keystore, providers

    memory = keystore.MemoryKeystore()
    monkeypatch.setattr(keystore, "default_keystore", lambda: memory)

    def refuse(*_args, **_kwargs):
        raise AssertionError("network call attempted in a test")

    monkeypatch.setattr(providers, "_urlopen", refuse)


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(engine):
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def app(engine):
    app = create_app({"TESTING": True, "ENGINE": engine})
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_activity(db_session):
    def _make_activity(**overrides):
        defaults = dict(
            activity_type="Run",
            start_time=datetime(2026, 7, 1, 8, 0, 0),
            end_time=datetime(2026, 7, 1, 8, 30, 0),
            duration_seconds=1800,
            distance_meters=5000.0,
            avg_hr=148.0,
            max_hr=165.0,
            elevation_gain_meters=42.0,
            source="apple_health",
            source_id="test-uuid-1",
            dedup_key="Run|2026-07-01T08:00:00|1800",
        )
        defaults.update(overrides)
        activity = Activity(**defaults)
        db_session.add(activity)
        db_session.commit()
        return activity

    return _make_activity


@pytest.fixture()
def fixtures_dir():
    from pathlib import Path

    return Path(__file__).parent / "fixtures"

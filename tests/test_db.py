from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from board.db import get_session, init_db, make_engine
from board.models import Agent, Event, Request

FIXED = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    engine = make_engine(str(tmp_path / "board.db"))
    init_db(engine)
    return engine


def make_agent(session: Session) -> Agent:
    agent = Agent(name="worker-1", harness="claude-code", api_key_hash="hash")
    session.add(agent)
    session.flush()
    return agent


def test_init_db_creates_the_three_tables(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert {"agents", "requests", "events"} <= tables


def test_make_engine_creates_missing_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "data" / "board.db"
    make_engine(str(target))
    assert target.parent.is_dir()


def test_event_with_unknown_request_id_raises_integrity_error(engine: Engine) -> None:
    with Session(engine) as session:
        agent = make_agent(session)
        session.add(
            Request(
                agent_id=agent.id,
                request_type="approval",
                title="Deploy to prod",
                detail="Ready to ship",
            )
        )
        session.commit()

    with Session(engine) as session:
        session.add(Event(request_id="no-such-request", kind="created"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_created_at_round_trips_as_timezone_aware_utc(engine: Engine) -> None:
    with Session(engine) as session:
        agent = make_agent(session)
        agent.created_at = FIXED
        session.commit()
        agent_id = agent.id

    with Session(engine) as session:
        loaded = session.scalar(select(Agent).where(Agent.id == agent_id))
        assert loaded is not None
        assert loaded.created_at.tzinfo is not None
        assert loaded.created_at.utcoffset() == timedelta(0)
        assert loaded.created_at == FIXED


def test_nullable_last_seen_round_trips_as_none(engine: Engine) -> None:
    with Session(engine) as session:
        agent = make_agent(session)
        session.commit()
        agent_id = agent.id

    with Session(engine) as session:
        loaded = session.scalar(select(Agent).where(Agent.id == agent_id))
        assert loaded is not None
        assert loaded.last_seen is None


def test_get_session_yields_a_usable_session_and_closes_it(engine: Engine) -> None:
    generator = get_session(engine)
    session = next(generator)
    make_agent(session)
    session.commit()
    with pytest.raises(StopIteration):
        next(generator)
    assert not session.in_transaction()

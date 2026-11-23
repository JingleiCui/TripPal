"""Prepare the isolated schema once; integration tests must not depend on module order."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_schema():
    from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
    from travel_agent.config import settings
    from travel_agent.db import Base, engine

    assert engine.url.database == "travel_agent_test", "Refusing to initialize a non-test database"
    Base.metadata.create_all(engine)
    with PyMySQLSaver.from_conn_string(settings.checkpoint_url) as saver:
        saver.setup()

"""
Thin wrapper around the official neo4j driver. One driver instance per
process, reused across requests (the driver itself pools connections, so
there's no need to open/close per-call).
"""
from __future__ import annotations

import logging
from typing import Any

from neo4j import Driver, GraphDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


def verify_connectivity() -> bool:
    try:
        get_driver().verify_connectivity()
        return True
    except Exception as e:
        logger.error("Neo4j connectivity check failed: %s", e)
        return False


def run_write(query: str, **params: Any) -> list[dict]:
    driver = get_driver()
    with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = session.execute_write(lambda tx: list(tx.run(query, **params)))
        return [dict(r) for r in result]


def run_read(query: str, **params: Any) -> list[dict]:
    driver = get_driver()
    with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = session.execute_read(lambda tx: list(tx.run(query, **params)))
        return [dict(r) for r in result]


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None

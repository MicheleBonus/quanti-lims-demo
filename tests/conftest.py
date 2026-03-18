"""Shared pytest fixtures for quanti-lims tests."""

import sys
import os
import pytest

# Add project root to sys.path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from models import db as _db


TEST_CONFIG = {
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "WTF_CSRF_ENABLED": False,
    "SECRET_KEY": "test-secret",
}


@pytest.fixture(scope="session")
def app():
    """Flask app using in-memory SQLite — shared across all tests.

    test_config is passed to create_app() so the URI is set before
    db.create_all() and migrate_schema() run inside create_app().
    """
    test_app = create_app(test_config=TEST_CONFIG)
    return test_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    """Yields db inside app context. Note: integration tests that commit
    via the route will not be rolled back by this fixture — test ordering
    may matter for integration tests that modify shared session state."""
    with app.app_context():
        yield _db
        _db.session.rollback()

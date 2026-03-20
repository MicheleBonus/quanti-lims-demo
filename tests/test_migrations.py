def test_flask_migrate_importable():
    import flask_migrate
    assert flask_migrate.__alembic_version__

def test_psycopg2_importable():
    import psycopg2
    assert psycopg2.__version__


def test_initial_migration_exists():
    import os
    migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')
    files = [f for f in os.listdir(migrations_dir) if f.endswith('.py') and not f.startswith('__')]
    assert len(files) >= 1, "Expected at least one migration file"


def test_migrate_schema_removed():
    import models
    assert not hasattr(models, 'migrate_schema'), \
        "migrate_schema() should have been removed — use Alembic migrations instead"


def test_legacy_migration_columns_exist(app):
    """Verify that legacy SQL migrations added the expected columns."""
    from sqlalchemy import inspect as sa_inspect
    with app.app_context():
        from models import db
        inspector = sa_inspect(db.engine)
        analysis_cols = [c["name"] for c in inspector.get_columns("analysis")]
        assert "m_einwaage_min_mg" in analysis_cols
        assert "m_einwaage_max_mg" in analysis_cols
        batch_cols = [c["name"] for c in inspector.get_columns("sample_batch")]
        assert "safety_factor" in batch_cols

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

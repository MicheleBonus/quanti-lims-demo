def test_flask_migrate_importable():
    import flask_migrate
    assert flask_migrate.__alembic_version__

def test_psycopg2_importable():
    import psycopg2
    assert psycopg2.__version__

"""add practical_amount_per_determination to method_reagent

Revision ID: e5f6a7b8c9d0
Revises: 9c64dbf20d9e
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = '9c64dbf20d9e'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('method_reagent')}
    if 'practical_amount_per_determination' not in existing_cols:
        with op.batch_alter_table('method_reagent', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('practical_amount_per_determination', sa.Float(), nullable=True)
            )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('method_reagent')}
    if 'practical_amount_per_determination' in existing_cols:
        with op.batch_alter_table('method_reagent', schema=None) as batch_op:
            batch_op.drop_column('practical_amount_per_determination')

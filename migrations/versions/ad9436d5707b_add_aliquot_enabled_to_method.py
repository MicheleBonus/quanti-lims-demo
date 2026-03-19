"""add_aliquot_enabled_to_method

Revision ID: ad9436d5707b
Revises: c3d4e5f6a7b8
Create Date: 2026-03-19 18:13:51.903720

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ad9436d5707b'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('method')}
    if 'aliquot_enabled' in existing_cols:
        return
    with op.batch_alter_table('method', schema=None) as batch_op:
        batch_op.add_column(sa.Column('aliquot_enabled', sa.Boolean(), nullable=True))
    # Backfill: existing methods with both volumes set → aliquot_enabled = True
    conn.execute(sa.text(
        "UPDATE method SET aliquot_enabled = 1 "
        "WHERE v_solution_ml IS NOT NULL AND v_aliquot_ml IS NOT NULL"
    ))


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('method')}
    if 'aliquot_enabled' not in existing_cols:
        return
    with op.batch_alter_table('method', schema=None) as batch_op:
        batch_op.drop_column('aliquot_enabled')

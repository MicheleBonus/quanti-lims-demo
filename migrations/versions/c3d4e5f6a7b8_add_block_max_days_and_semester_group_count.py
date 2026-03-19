"""add_block_max_days_and_semester_group_count

Revision ID: c3d4e5f6a7b8
Revises: 6ca003974b18
Create Date: 2026-03-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = '6ca003974b18'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    semester_cols = {c['name'] for c in inspector.get_columns('semester')}
    block_cols = {c['name'] for c in inspector.get_columns('block')}

    if 'active_group_count' not in semester_cols:
        with op.batch_alter_table('semester', schema=None) as batch_op:
            batch_op.add_column(sa.Column('active_group_count', sa.Integer(), nullable=False, server_default='4'))

    if 'max_days' not in block_cols:
        with op.batch_alter_table('block', schema=None) as batch_op:
            batch_op.add_column(sa.Column('max_days', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('semester', schema=None) as batch_op:
        batch_op.drop_column('active_group_count')

    with op.batch_alter_table('block', schema=None) as batch_op:
        batch_op.drop_column('max_days')

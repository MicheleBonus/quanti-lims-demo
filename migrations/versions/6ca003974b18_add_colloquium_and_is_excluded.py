"""add_colloquium_and_is_excluded

Revision ID: 6ca003974b18
Revises: 0b57251967a8
Create Date: 2026-03-19 17:56:27.800718

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6ca003974b18'
down_revision = '0b57251967a8'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    existing_student_cols = {col['name'] for col in inspector.get_columns('student')}

    if 'colloquium' not in existing_tables:
        op.create_table('colloquium',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('student_id', sa.Integer(), nullable=False),
            sa.Column('block_id', sa.Integer(), nullable=False),
            sa.Column('attempt_number', sa.Integer(), nullable=False),
            sa.Column('scheduled_date', sa.String(20), nullable=True),
            sa.Column('conducted_date', sa.String(20), nullable=True),
            sa.Column('examiner', sa.String(200), nullable=True),
            sa.Column('passed', sa.Boolean(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['student_id'], ['student.id']),
            sa.ForeignKeyConstraint(['block_id'], ['block.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('student_id', 'block_id', 'attempt_number'),
        )

    if 'is_excluded' not in existing_student_cols:
        with op.batch_alter_table('student', schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_excluded', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    existing_student_cols = {col['name'] for col in inspector.get_columns('student')}

    if 'is_excluded' in existing_student_cols:
        with op.batch_alter_table('student', schema=None) as batch_op:
            batch_op.drop_column('is_excluded')

    if 'colloquium' in existing_tables:
        op.drop_table('colloquium')

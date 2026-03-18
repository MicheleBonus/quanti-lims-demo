"""add practical_day model

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-03-18 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a1'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'practical_day',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('semester_id', sa.Integer(), nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(length=20), nullable=False),
        sa.Column('day_type', sa.Enum('normal', 'nachkochtag', name='practical_day_type',
                                      native_enum=False, create_constraint=True,
                                      validate_strings=True), nullable=False),
        sa.Column('block_day_number', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['block_id'], ['block.id'], ),
        sa.ForeignKeyConstraint(['semester_id'], ['semester.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('semester_id', 'date'),
    )


def downgrade():
    op.drop_table('practical_day')

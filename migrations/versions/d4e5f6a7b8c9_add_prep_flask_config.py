"""add prep_flask_config table

Revision ID: d4e5f6a7b8c9
Revises: 9c64dbf20d9e
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = '9c64dbf20d9e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'prep_flask_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reagent_id', sa.Integer(), nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=True),
        sa.Column('flask_size_ml', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['reagent_id'], ['reagent.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('prep_flask_config')

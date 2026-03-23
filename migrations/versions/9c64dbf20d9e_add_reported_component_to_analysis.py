"""add_reported_component_to_analysis

Revision ID: 9c64dbf20d9e
Revises: ad9436d5707b
Create Date: 2026-03-20 22:15:20.383996

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c64dbf20d9e'
down_revision = 'ad9436d5707b'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('analysis')}
    if 'reported_molar_mass_gmol' in existing_cols:
        return  # already present (fresh install via db.create_all in initial migration)
    with op.batch_alter_table('analysis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reported_molar_mass_gmol', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('reported_stoichiometry', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('analysis', schema=None) as batch_op:
        batch_op.drop_column('reported_stoichiometry')
        batch_op.drop_column('reported_molar_mass_gmol')

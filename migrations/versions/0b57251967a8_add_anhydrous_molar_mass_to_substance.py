"""add_anhydrous_molar_mass_to_substance

Revision ID: 0b57251967a8
Revises: 75ce3436b714
Create Date: 2026-03-19 17:36:15.464768

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0b57251967a8'
down_revision = '75ce3436b714'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('substance')}
    if 'anhydrous_molar_mass_gmol' in existing_cols:
        return
    with op.batch_alter_table('substance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('anhydrous_molar_mass_gmol', sa.Float(), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {col['name'] for col in inspector.get_columns('substance')}
    if 'anhydrous_molar_mass_gmol' not in existing_cols:
        return
    with op.batch_alter_table('substance', schema=None) as batch_op:
        batch_op.drop_column('anhydrous_molar_mass_gmol')

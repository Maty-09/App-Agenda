"""add trial dates to tenant

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenants", sa.Column("trial_inicio", sa.DateTime(), nullable=True))
    op.add_column("tenants", sa.Column("trial_fin", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("tenants", "trial_fin")
    op.drop_column("tenants", "trial_inicio")

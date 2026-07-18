"""add booking status reason

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""
from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agendamientos", sa.Column("razon_estado", sa.String(), nullable=True))


def downgrade():
    op.drop_column("agendamientos", "razon_estado")

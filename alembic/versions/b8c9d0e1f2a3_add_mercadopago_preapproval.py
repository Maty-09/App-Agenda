"""add Mercado Pago preapproval reference to tenant

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa


revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(sa.Column("mercado_pago_preapproval_id", sa.String(), nullable=True))
        batch_op.create_unique_constraint("uq_tenants_mercadopago_preapproval_id", ["mercado_pago_preapproval_id"])


def downgrade() -> None:
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_constraint("uq_tenants_mercadopago_preapproval_id", type_="unique")
        batch_op.drop_column("mercado_pago_preapproval_id")

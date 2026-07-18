"""scope unique keys by tenant

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
"""
from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_clientes_rut", table_name="clientes")
    op.create_unique_constraint("uq_clientes_tenant_rut", "clientes", ["tenant_id", "rut"])
    op.drop_constraint("dias_bloqueados_fecha_key", "dias_bloqueados", type_="unique")
    op.create_unique_constraint("uq_dias_bloqueados_tenant_fecha", "dias_bloqueados", ["tenant_id", "fecha"])


def downgrade():
    op.drop_constraint("uq_dias_bloqueados_tenant_fecha", "dias_bloqueados", type_="unique")
    op.create_unique_constraint("dias_bloqueados_fecha_key", "dias_bloqueados", ["fecha"])
    op.drop_constraint("uq_clientes_tenant_rut", "clientes", type_="unique")
    op.create_index("ix_clientes_rut", "clientes", ["rut"], unique=True)

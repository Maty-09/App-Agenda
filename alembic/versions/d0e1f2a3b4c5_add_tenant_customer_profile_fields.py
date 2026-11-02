"""Add tenant-scoped custom fields to customer profiles."""
from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "campos_cliente",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("clave", sa.String(length=80), nullable=False),
        sa.Column("etiqueta", sa.String(length=120), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("opciones_json", sa.Text(), nullable=True),
        sa.Column("requerido", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "clave", name="uq_campos_cliente_tenant_clave"),
    )
    op.create_index("ix_campos_cliente_id", "campos_cliente", ["id"], unique=False)
    op.create_index("ix_campos_cliente_tenant_id", "campos_cliente", ["tenant_id"], unique=False)

    op.create_table(
        "valores_campos_cliente",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("campo_id", sa.Integer(), nullable=False),
        sa.Column("valor", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campo_id"], ["campos_cliente.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "cliente_id", "campo_id", name="uq_valores_campo_cliente_scope"),
    )
    op.create_index("ix_valores_campos_cliente_id", "valores_campos_cliente", ["id"], unique=False)
    op.create_index("ix_valores_campos_cliente_tenant_id", "valores_campos_cliente", ["tenant_id"], unique=False)
    op.create_index("ix_valores_campos_cliente_cliente_id", "valores_campos_cliente", ["cliente_id"], unique=False)
    op.create_index("ix_valores_campos_cliente_campo_id", "valores_campos_cliente", ["campo_id"], unique=False)


def downgrade():
    op.drop_index("ix_valores_campos_cliente_campo_id", table_name="valores_campos_cliente")
    op.drop_index("ix_valores_campos_cliente_cliente_id", table_name="valores_campos_cliente")
    op.drop_index("ix_valores_campos_cliente_tenant_id", table_name="valores_campos_cliente")
    op.drop_index("ix_valores_campos_cliente_id", table_name="valores_campos_cliente")
    op.drop_table("valores_campos_cliente")
    op.drop_index("ix_campos_cliente_tenant_id", table_name="campos_cliente")
    op.drop_index("ix_campos_cliente_id", table_name="campos_cliente")
    op.drop_table("campos_cliente")

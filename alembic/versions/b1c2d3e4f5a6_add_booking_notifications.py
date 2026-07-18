"""add booking notification audit

Revision ID: b1c2d3e4f5a6
Revises: a08cbc2267fe
"""
from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a08cbc2267fe"
branch_labels = None
depends_on = None


def upgrade():
    # El proyecto mantiene create_all() en startup; en instalaciones ya iniciadas
    # la tabla puede existir antes de que Alembic registre esta revisión.
    if sa.inspect(op.get_bind()).has_table("notificaciones_agendamiento"):
        return
    op.create_table(
        "notificaciones_agendamiento",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("agendamiento_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("canal", sa.String(), nullable=False),
        sa.Column("enviado_en", sa.DateTime(), nullable=False),
        sa.Column("detalle_error", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["agendamiento_id"], ["agendamientos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agendamiento_id", "tipo", "canal", name="uq_notificacion_agendamiento_tipo_canal"),
    )
    op.create_index("ix_notificaciones_agendamiento_tenant_id", "notificaciones_agendamiento", ["tenant_id"])
    op.create_index("ix_notificaciones_agendamiento_agendamiento_id", "notificaciones_agendamiento", ["agendamiento_id"])


def downgrade():
    op.drop_table("notificaciones_agendamiento")

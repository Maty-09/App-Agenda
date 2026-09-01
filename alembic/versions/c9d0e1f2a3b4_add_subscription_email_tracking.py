"""add SaaS email notification tracking

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(sa.Column("trial_vencimiento_notificado_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("suscripcion_notificada_at", sa.DateTime(), nullable=True))

def downgrade():
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_column("suscripcion_notificada_at")
        batch_op.drop_column("trial_vencimiento_notificado_at")

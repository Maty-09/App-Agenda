"""add password reset fields

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e1"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuarios", sa.Column("password_reset_token_hash", sa.String(length=64), nullable=True))
    op.add_column("usuarios", sa.Column("password_reset_expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_usuarios_password_reset_token_hash", "usuarios", ["password_reset_token_hash"])


def downgrade():
    op.drop_index("ix_usuarios_password_reset_token_hash", table_name="usuarios")
    op.drop_column("usuarios", "password_reset_expires_at")
    op.drop_column("usuarios", "password_reset_token_hash")

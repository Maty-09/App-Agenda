"""Add CRM models

Revision ID: 63b6c0ad9f08
Revises: ef887679465e
Create Date: 2026-07-01 20:56:18.881978

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63b6c0ad9f08'
down_revision: Union[str, None] = 'ef887679465e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La base inicial precede al módulo CRM; crear sus tablas antes de referenciarlas.
    op.create_table('clientes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('rut', sa.String(), nullable=False),
    sa.Column('nombre', sa.String(), nullable=False),
    sa.Column('apellido', sa.String(), nullable=False),
    sa.Column('telefono', sa.String(), nullable=False),
    sa.Column('correo', sa.String(), nullable=False),
    sa.Column('etiquetas', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clientes_id'), ['id'], unique=False)
        # La siguiente migración la transforma en una clave compuesta por tenant.
        batch_op.create_index(batch_op.f('ix_clientes_rut'), ['rut'], unique=True)

    op.create_table('timeline_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('cliente_id', sa.Integer(), nullable=False),
    sa.Column('tipo_evento', sa.String(), nullable=False),
    sa.Column('metadata_json', sa.String(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
    sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('timeline_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_timeline_events_id'), ['id'], unique=False)

    with op.batch_alter_table('agendamientos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cliente_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'clientes', ['cliente_id'], ['id'])

    # ### end Alembic commands ###


def downgrade() -> None:
    with op.batch_alter_table('agendamientos', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('cliente_id')

    with op.batch_alter_table('timeline_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_timeline_events_id'))
    op.drop_table('timeline_events')
    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clientes_rut'))
        batch_op.drop_index(batch_op.f('ix_clientes_id'))
    op.drop_table('clientes')

    # ### end Alembic commands ###

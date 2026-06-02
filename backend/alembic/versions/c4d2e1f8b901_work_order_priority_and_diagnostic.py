"""work_order_priority_and_diagnostic

Revision ID: c4d2e1f8b901
Revises: bd6564c8bd40
Create Date: 2026-06-02 13:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4d2e1f8b901'
down_revision: str | None = 'bd6564c8bd40'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


work_order_priority = sa.Enum(
    'low', 'normal', 'high', 'critical',
    name='work_order_priority',
)


def upgrade() -> None:
    work_order_priority.create(op.get_bind(), checkfirst=True)

    op.alter_column(
        'work_orders',
        'work_type_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    op.add_column(
        'work_orders',
        sa.Column('priority', work_order_priority, nullable=False, server_default='normal'),
    )
    op.create_index(
        'ix_work_orders_priority',
        'work_orders',
        ['priority'],
    )

    op.add_column(
        'work_orders',
        sa.Column('defect_ref', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'ix_work_orders_defect_ref',
        'work_orders',
        ['defect_ref'],
    )

    op.add_column(
        'work_orders',
        sa.Column('is_diagnostic', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('work_orders', 'is_diagnostic')
    op.drop_index('ix_work_orders_defect_ref', table_name='work_orders')
    op.drop_column('work_orders', 'defect_ref')
    op.drop_index('ix_work_orders_priority', table_name='work_orders')
    op.drop_column('work_orders', 'priority')
    op.alter_column(
        'work_orders',
        'work_type_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    work_order_priority.drop(op.get_bind(), checkfirst=True)

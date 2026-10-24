"""Initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-24 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. terminals
    op.create_table(
        'terminals',
        sa.Column('id', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE'),
        sa.Column('current_session_id', sa.String(length=36), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. reservations
    op.create_table(
        'reservations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('customer_name', sa.String(length=100), nullable=False),
        sa.Column('card_uid', sa.String(length=50), nullable=False),
        sa.Column('requested_services', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('assigned_terminal_id', sa.String(length=10), nullable=True),
        sa.Column('session_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['assigned_terminal_id'], ['terminals.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', name='uq_reservations_session_id')
    )

    # 3. sessions
    op.create_table(
        'sessions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('terminal_id', sa.String(length=10), nullable=False),
        sa.Column('reservation_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='STARTED'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['terminal_id'], ['terminals.id']),
        sa.ForeignKeyConstraint(['reservation_id'], ['reservations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reservation_id', name='uq_sessions_reservation_id')
    )

    # 4. meter_readings
    op.create_table(
        'meter_readings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('meter_type', sa.String(length=15), nullable=False),
        sa.Column('cumulative_value', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('unit', sa.String(length=10), nullable=False),
        sa.Column('is_final', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_meter_readings_session_final', 'meter_readings', ['session_id', 'is_final'])

    # 5. tariff_brackets
    op.create_table(
        'tariff_brackets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('meter_type', sa.String(length=15), nullable=False),
        sa.Column('tier_order', sa.Integer(), nullable=False),
        sa.Column('lower_bound', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('upper_bound', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('rate_per_unit', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('unit', sa.String(length=10), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='TND'),
        sa.Column('fixed_fee', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('effective_from', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 6. invoices
    op.create_table(
        'invoices',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='TND'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', name='uq_invoices_session_id')
    )

    # 7. invoice_lines
    op.create_table(
        'invoice_lines',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('invoice_id', sa.Uuid(), nullable=False),
        sa.Column('meter_type', sa.String(length=15), nullable=False),
        sa.Column('consumption', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('unit', sa.String(length=10), nullable=False),
        sa.Column('fixed_fee', sa.Numeric(precision=10, scale=3), nullable=False, server_default='0.000'),
        sa.Column('usage_amount', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('line_total', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('tier_breakdown', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 8. processed_messages
    op.create_table(
        'processed_messages',
        sa.Column('message_id', sa.String(length=36), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('message_id')
    )


def downgrade() -> None:
    op.drop_table('processed_messages')
    op.drop_table('invoice_lines')
    op.drop_table('invoices')
    op.drop_table('tariff_brackets')
    op.drop_index('ix_meter_readings_session_final', table_name='meter_readings')
    op.drop_table('meter_readings')
    op.drop_table('sessions')
    op.drop_table('reservations')
    op.drop_table('terminals')

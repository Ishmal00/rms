"""Add user notifications and employee shift assignments.

Revision ID: 6fe12a4c9b31
Revises: 18d468130381
Create Date: 2026-11-12

"""
from alembic import op
import sqlalchemy as sa


revision = '6fe12a4c9b31'
down_revision = '18d468130381'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shift_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_employees_shift_id', ['shift_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_employees_shift_id',
            'shifts',
            ['shift_id'],
            ['id'],
            ondelete='SET NULL'
        )

    op.create_table(
        'notifications',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('notification_type', sa.String(length=40), nullable=False),
        sa.Column('link', sa.String(length=255), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('deleted_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name='fk_notifications_created_by',
            ondelete='SET NULL',
            use_alter=True
        ),
        sa.ForeignKeyConstraint(
            ['deleted_by'], ['users.id'],
            name='fk_notifications_deleted_by',
            ondelete='SET NULL',
            use_alter=True
        ),
        sa.ForeignKeyConstraint(
            ['updated_by'], ['users.id'],
            name='fk_notifications_updated_by',
            ondelete='SET NULL',
            use_alter=True
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name='fk_notifications_user_id',
            ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index('ix_notifications_is_deleted', ['is_deleted'], unique=False)
        batch_op.create_index('ix_notifications_is_read', ['is_read'], unique=False)
        batch_op.create_index('ix_notifications_notification_type', ['notification_type'], unique=False)
        batch_op.create_index('ix_notifications_status', ['status'], unique=False)
        batch_op.create_index('ix_notifications_user_id', ['user_id'], unique=False)


def downgrade():
    op.drop_table('notifications')
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_constraint('fk_employees_shift_id', type_='foreignkey')
        batch_op.drop_index('ix_employees_shift_id')
        batch_op.drop_column('shift_id')

"""Persist encrypted AI connection settings shared by web and workers."""
from alembic import op
import sqlalchemy as sa

revision = 'b9d3f5a7c012'
down_revision = 'a8c2e4f6b901'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ai_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('encrypted_config', sa.Text(), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint('id = 1', name='ai_settings_singleton'),
    )


def downgrade():
    op.drop_table('ai_settings')

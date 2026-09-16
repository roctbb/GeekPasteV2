"""add_gpt_rate_limit_to_tasks

Revision ID: f3a5c7e9b1d4
Revises: 5613318ab013
Create Date: 2026-03-19 22:24:02.302372

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
# Keep the deployed head after removing the subsequent data-only migrations.
revision = 'f3a5c7e9b1d4'
down_revision = '5613318ab013'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tasks', sa.Column('gpt_rate_limit', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('tasks', 'gpt_rate_limit')
